from __future__ import annotations

import random
import time
from datetime import datetime

from django.utils import timezone
from django_tasks import TaskResultStatus, task
from django_tasks.exceptions import TaskResultDoesNotExist, TaskResultMismatch

from .models import SimulatedTask

DURATION_RANGE: tuple[int, int] = (3, 10)
FAILURE_RATE: float = 0.2
MISSING_BACKEND_RESULT = "Task result could not be found."
UNEXPECTED_BACKEND_RESULT = "Task exited before the demo row was finalized."

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
    task_row = SimulatedTask.objects.get(pk=task_id)
    if task_row.status in {SimulatedTask.Status.DONE, SimulatedTask.Status.FAILED}:
        return _serialized_terminal_payload(task_row)

    task_row.status = SimulatedTask.Status.RUNNING
    task_row.save(update_fields=["status"])

    duration = round(random.uniform(*DURATION_RANGE), 1)
    time.sleep(duration)

    completed_at = timezone.now()
    failed = random.random() < FAILURE_RATE
    task_row.duration = duration
    task_row.completed_at = completed_at
    task_row.result = random.choice(FAILURE_RESULTS if failed else SUCCESS_RESULTS)
    task_row.status = SimulatedTask.Status.FAILED if failed else SimulatedTask.Status.DONE
    task_row.save(update_fields=["status", "result", "duration", "completed_at"])

    if failed:
        raise SimulatedTaskFailure(task_row.result)

    return _serialized_terminal_payload(task_row)


def reconcile_task_with_backend(task_row: SimulatedTask) -> SimulatedTask:
    if task_row.status in {SimulatedTask.Status.DONE, SimulatedTask.Status.FAILED}:
        return task_row

    if not task_row.backend_task_id:
        return task_row

    try:
        backend_result = run_simulated_task.get_result(task_row.backend_task_id)
    except (TaskResultDoesNotExist, TaskResultMismatch):
        _mark_task_failed(task_row, MISSING_BACKEND_RESULT)
        return task_row

    if backend_result.status == TaskResultStatus.READY:
        if task_row.status != SimulatedTask.Status.PENDING:
            task_row.status = SimulatedTask.Status.PENDING
            task_row.save(update_fields=["status"])
        return task_row

    if backend_result.status == TaskResultStatus.RUNNING:
        if task_row.status != SimulatedTask.Status.RUNNING:
            task_row.status = SimulatedTask.Status.RUNNING
            task_row.save(update_fields=["status"])
        return task_row

    if backend_result.status == TaskResultStatus.FAILED:
        if task_row.status != SimulatedTask.Status.FAILED:
            _mark_task_failed(task_row, _backend_failure_message(backend_result))
        return task_row

    if (
        backend_result.status == TaskResultStatus.SUCCESSFUL
        and task_row.status != SimulatedTask.Status.DONE
    ):
        payload = backend_result.return_value or {}
        task_row.status = payload.get("status", SimulatedTask.Status.DONE)  # type: ignore[assignment]
        task_row.result = payload.get("result") or task_row.result  # type: ignore[assignment]
        duration = payload.get("duration")
        task_row.duration = duration if duration is not None else task_row.duration  # type: ignore[assignment]
        completed_at = payload.get("completed_at")
        task_row.completed_at = (
            datetime.fromisoformat(completed_at)  # type: ignore[arg-type]
            if completed_at
            else (task_row.completed_at or backend_result.finished_at or timezone.now())
        )
        task_row.save(update_fields=["status", "result", "duration", "completed_at"])
        return task_row

    if backend_result.status != TaskResultStatus.SUCCESSFUL:
        _mark_task_failed(task_row, UNEXPECTED_BACKEND_RESULT)

    return task_row


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
    task_row.save(update_fields=["status", "result", "completed_at"])


def _backend_failure_message(backend_result) -> str:
    if backend_result.errors:
        lines = backend_result.errors[-1].traceback.strip().splitlines()
        return lines[-1] if lines else UNEXPECTED_BACKEND_RESULT
    return UNEXPECTED_BACKEND_RESULT
