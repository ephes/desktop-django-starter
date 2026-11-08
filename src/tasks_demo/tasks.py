from __future__ import annotations

import math
import random
import time
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from django.tasks import TaskResult, TaskResultStatus, task
from django.tasks.exceptions import TaskResultDoesNotExist, TaskResultMismatch
from django.utils import timezone
from django_tasks_db.models import DBTaskResult

from .models import SimulatedTask

DURATION_RANGE: tuple[int, int] = (3, 10)
FAILURE_RATE: float = 0.2
MISSING_BACKEND_RESULT = "Task result could not be found."
INVALID_BACKEND_PAYLOAD = "Task returned an invalid completion payload."
UNEXPECTED_BACKEND_RESULT = "Task exited before the demo row was finalized."
TERMINAL_HISTORY_LIMIT = 100

TASK_LABELS: list[str] = [
    "Restocking hay loft",
    "Brushing parade manes",
    "Polishing tack room brass",
    "Counting sugar-cube tins",
    "Refreshing paddock lanterns",
    "Folding ribbon blankets",
]

SUCCESS_RESULTS: list[str] = [
    "Routine complete: the stable is ready for visitors.",
    "Routine complete: supplies are counted and stowed.",
    "Routine complete: every stall passed inspection.",
    "Routine complete: tack is polished and hung.",
    "Routine complete: the paddocks are set for evening turnout.",
]

FAILURE_RESULTS: list[str] = [
    "Routine delayed: a loose latch needs attention.",
    "Routine failed: the hay cart lost a wheel.",
    "Routine delayed: the tack room key is missing.",
]


class SimulatedTaskFailure(RuntimeError):
    """Raised when the demo task intentionally fails."""


@task()
def run_simulated_task(task_id: int) -> dict[str, object]:
    claimed = SimulatedTask.objects.filter(pk=task_id, status=SimulatedTask.Status.PENDING).update(
        status=SimulatedTask.Status.RUNNING
    )
    task_row = SimulatedTask.objects.filter(pk=task_id).first()
    if task_row is None:
        return {}
    if not claimed:
        # A duplicate reports the current state without executing or finalizing it.
        return _serialized_terminal_payload(task_row)

    duration = round(random.uniform(*DURATION_RANGE), 1)
    time.sleep(duration)

    completed_at = timezone.now()
    failed = random.random() < FAILURE_RATE
    task_row.duration = duration
    task_row.completed_at = completed_at
    task_row.result = random.choice(FAILURE_RESULTS if failed else SUCCESS_RESULTS)
    task_row.status = SimulatedTask.Status.FAILED if failed else SimulatedTask.Status.DONE
    finalized = SimulatedTask.objects.filter(
        pk=task_id,
        status=SimulatedTask.Status.RUNNING,
        backend_task_id=task_row.backend_task_id,
    ).update(
        status=task_row.status,
        result=task_row.result,
        duration=duration,
        completed_at=completed_at,
    )
    if not finalized:
        current = SimulatedTask.objects.filter(pk=task_id).first()
        return _serialized_terminal_payload(current) if current else {}

    if failed:
        raise SimulatedTaskFailure(task_row.result)

    return _serialized_terminal_payload(task_row)


def visible_tasks() -> list[SimulatedTask]:
    active = list(
        SimulatedTask.objects.filter(
            status__in=[SimulatedTask.Status.PENDING, SimulatedTask.Status.RUNNING]
        )
    )
    result_ids = set()
    for row in active:
        try:
            result_ids.add(UUID(row.backend_task_id))
        except ValueError:
            pass  # Malformed IDs follow the same missing-result policy as get_result().
    # in_bulk() uses parameter-safe batches on each supported database.
    backend_rows = DBTaskResult.objects.in_bulk(result_ids)

    def load_result(result_id: str):
        try:
            backend_row = backend_rows[UUID(result_id)]
        except (KeyError, ValueError) as exc:
            raise TaskResultDoesNotExist(result_id) from exc
        result = backend_row.task_result
        if result.task.func != run_simulated_task.func:
            raise TaskResultMismatch("Task does not match")
        return result

    active = [reconcile_task_with_backend(row, result_loader=load_result) for row in active]
    # Query history after reconciliation so fresh completions are visible in
    # this response, even when the task was queued long ago.
    history = list(
        SimulatedTask.objects.filter(
            status__in=[SimulatedTask.Status.DONE, SimulatedTask.Status.FAILED]
        ).order_by("-completed_at", "-created_at", "-pk")[:TERMINAL_HISTORY_LIMIT]
    )
    history_ids = {row.pk for row in history}
    active = [
        row
        for row in active
        if row.status in {SimulatedTask.Status.PENDING, SimulatedTask.Status.RUNNING}
        and row.pk not in history_ids
    ]
    return sorted(active + history, key=lambda row: (row.created_at, row.pk), reverse=True)


def reconcile_task_with_backend(
    task_row: SimulatedTask, *, result_loader: Callable[[str], TaskResult] | None = None
) -> SimulatedTask:
    if task_row.status in {SimulatedTask.Status.DONE, SimulatedTask.Status.FAILED}:
        return task_row

    if not task_row.backend_task_id:
        return task_row

    try:
        backend_result = (result_loader or run_simulated_task.get_result)(task_row.backend_task_id)
    except (TaskResultDoesNotExist, TaskResultMismatch):
        # Missing queue metadata cannot prove that a claimed worker has stopped.
        # Startup reconciliation retires abandoned claims after a restart.
        if task_row.status == SimulatedTask.Status.PENDING:
            _mark_task_failed(task_row, MISSING_BACKEND_RESULT)
        else:
            task_row.refresh_from_db()
        return task_row

    if backend_result.status in {TaskResultStatus.READY, TaskResultStatus.RUNNING}:
        # Only the worker may claim the demo row; polling cannot reset a claim.
        return task_row

    if backend_result.status == TaskResultStatus.FAILED:
        if task_row.status != SimulatedTask.Status.FAILED:
            _mark_task_failed(task_row, _backend_failure_message(backend_result))
        return task_row

    if (
        backend_result.status == TaskResultStatus.SUCCESSFUL
        and task_row.status != SimulatedTask.Status.DONE
    ):
        payload = backend_result.return_value
        # A duplicate execution may report the current active claim without work.
        if (
            isinstance(payload, dict)
            and isinstance(payload.get("status"), str)
            and payload.get("status") == task_row.status
            and payload.get("duration") is None
            and payload.get("completed_at") is None
        ):
            return task_row
        try:
            status, result, duration, completed_at = _validated_completion(payload)
        except (ValueError, TypeError, OverflowError):
            _mark_task_failed(task_row, INVALID_BACKEND_PAYLOAD)
            return task_row
        task_row.status = status
        task_row.result = result
        task_row.duration = duration
        task_row.completed_at = completed_at
        _save_reconciled_task(task_row, ["status", "result", "duration", "completed_at"])
        return task_row

    if backend_result.status != TaskResultStatus.SUCCESSFUL:
        _mark_task_failed(task_row, UNEXPECTED_BACKEND_RESULT)

    return task_row


def _validated_completion(payload: object) -> tuple[str, str, float, datetime]:
    if not isinstance(payload, dict):
        raise ValueError("Expected a completion object")
    status = payload.get("status")
    result = payload.get("result")
    duration = payload.get("duration")
    completed_at = payload.get("completed_at")
    if not isinstance(status, str) or status not in {
        SimulatedTask.Status.DONE,
        SimulatedTask.Status.FAILED,
    }:
        raise ValueError("Expected a terminal status")
    if not isinstance(result, str):
        raise ValueError("Expected a result string")
    if (
        not isinstance(duration, (int, float))
        or isinstance(duration, bool)
        or not math.isfinite(duration)
        or duration < 0
    ):
        raise ValueError("Expected a finite nonnegative duration")
    if not isinstance(completed_at, str):
        raise ValueError("Expected an ISO timestamp")
    timestamp = datetime.fromisoformat(completed_at)
    if timezone.is_naive(timestamp):
        raise ValueError("Expected a timezone-aware timestamp")
    return status, result, float(duration), timestamp


def _serialized_terminal_payload(task_row: SimulatedTask) -> dict[str, object]:
    return {
        "status": task_row.status,
        "result": task_row.result or "",
        "duration": task_row.duration,
        "completed_at": task_row.completed_at.isoformat() if task_row.completed_at else None,
    }


def _mark_task_failed(task_row: SimulatedTask, result: str) -> None:
    task_row.status = SimulatedTask.Status.FAILED
    task_row.result = result
    task_row.completed_at = task_row.completed_at or timezone.now()
    _save_reconciled_task(task_row, ["status", "result", "completed_at"])


def _save_reconciled_task(task_row: SimulatedTask, fields: list[str]) -> None:
    updated = SimulatedTask.objects.filter(
        pk=task_row.pk,
        status__in=[SimulatedTask.Status.PENDING, SimulatedTask.Status.RUNNING],
    ).update(**{field: getattr(task_row, field) for field in fields})
    if not updated:
        # The worker finalized the row after polling loaded it; keep its result.
        task_row.refresh_from_db()


def _backend_failure_message(backend_result) -> str:
    if backend_result.errors:
        lines = backend_result.errors[-1].traceback.strip().splitlines()
        return lines[-1] if lines else UNEXPECTED_BACKEND_RESULT
    return UNEXPECTED_BACKEND_RESULT
