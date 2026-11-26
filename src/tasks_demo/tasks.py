from __future__ import annotations

import math
import random
import time
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from django.db import transaction
from django.db.models import Count, F, Func, Q, Value
from django.db.models.functions import Lower, Replace, Right
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
CLEAR_BATCH_SIZE = 100
TRACEBACK_PREVIEW_LIMIT = 1024
COMPLETION_RESULT_BYTE_LIMIT = 1024

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
    # Match the partial indexes with OR equality terms. SQLite cannot prove
    # a parameterized IN predicate implies an index's literal IN condition.
    active = list(
        SimulatedTask.objects.filter(
            Q(status=SimulatedTask.Status.PENDING) | Q(status=SimulatedTask.Status.RUNNING)
        )
    )
    result_ids = set()
    for row in active:
        try:
            result_ids.add(UUID(row.backend_task_id))
        except ValueError:
            pass  # Malformed IDs follow the same missing-result policy as get_result().
    # in_bulk() uses parameter-safe batches on each supported database.
    # Keep full stored diagnostics in SQLite. The public task_result property
    # receives only a bounded tail, never a deferred read of the full traceback.
    backend_rows = (
        DBTaskResult.objects.defer("traceback")
        .annotate(traceback_preview=Right("traceback", TRACEBACK_PREVIEW_LIMIT))
        .in_bulk(result_ids)
    )

    def load_result(result_id: str):
        try:
            backend_row = backend_rows[UUID(result_id)]
        except (KeyError, ValueError) as exc:
            raise TaskResultDoesNotExist(result_id) from exc
        if (
            backend_row.task_path != run_simulated_task.module_path
            or backend_row.backend_name != run_simulated_task.backend
            or backend_row.queue_name != run_simulated_task.queue_name
        ):
            raise TaskResultMismatch("Task does not match")
        backend_row.traceback = backend_row.traceback_preview
        return backend_row.task_result

    reconciled = (reconcile_task_with_backend(row, result_loader=load_result) for row in active)
    active = [row for row in reconciled if row is not None]
    # Query history after reconciliation so fresh completions are visible in
    # this response, even when the task was queued long ago.
    history = list(
        SimulatedTask.objects.filter(
            Q(status=SimulatedTask.Status.DONE) | Q(status=SimulatedTask.Status.FAILED)
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


def clear_finished_routines() -> None:
    history = SimulatedTask.objects.filter(
        status__in=[SimulatedTask.Status.DONE, SimulatedTask.Status.FAILED]
    ).order_by("pk")
    with transaction.atomic():
        _lock_routine_writes()
        # Snapshot history finished when the clear starts. A routine whose
        # completion commits later stays for the next clear, even when its
        # worker computed the completion time before this snapshot.
        eligible_ids = list(history.values_list("pk", flat=True))

    shared_ids: set[UUID] = set()
    for start in range(0, len(eligible_ids), CLEAR_BATCH_SIZE):
        with transaction.atomic():
            _lock_routine_writes()
            batch_ids = eligible_ids[start : start + CLEAR_BATCH_SIZE]
            rows = list(history.filter(pk__in=batch_ids).values_list("pk", "backend_task_id"))
            if not rows:
                continue

            routine_ids = {}
            for pk, backend_id in rows:
                try:
                    routine_ids[UUID(backend_id)] = pk
                except ValueError:
                    pass  # Missing and malformed legacy IDs have no owned result.

            # Remember shared IDs when one reference is cleared ahead of another.
            # Check references in every state, including rows outside this batch.
            shared_ids.update(_shared_backend_ids(routine_ids.keys() - shared_ids))
            candidates = (
                DBTaskResult.objects.filter(
                    pk__in=routine_ids.keys() - shared_ids,
                    status__in=[TaskResultStatus.SUCCESSFUL, TaskResultStatus.FAILED],
                    task_path=run_simulated_task.module_path,
                    backend_name=run_simulated_task.backend,
                    queue_name=run_simulated_task.queue_name,
                )
                .order_by()
                .values_list("pk", "args_kwargs")
            )
            owned_ids = [
                result_id
                for result_id, arguments in candidates
                if isinstance(arguments, dict)
                and _matches_routine_argument(
                    routine_ids[result_id], arguments.get("args"), arguments.get("kwargs")
                )
            ]
            DBTaskResult.objects.filter(pk__in=owned_ids).delete()
            history.filter(pk__in=[pk for pk, _ in rows]).delete()


def _lock_routine_writes() -> None:
    # Serialize selection and deletion with queue writers on SQLite,
    # including development connections with deferred transactions.
    SimulatedTask.objects.filter(pk=0).update(status=F("status"))


def _shared_backend_ids(result_ids: set[UUID]) -> set[UUID]:
    if not result_ids:
        return set()
    # Account for UUID spellings that could resolve to the same backend row.
    normalized: Func = Lower("backend_task_id")
    for token in ("urn:", "uuid:", "{", "}", "-"):
        normalized = Replace(normalized, Value(token), Value(""))
    shared = (
        SimulatedTask.objects.annotate(result_hex=normalized)
        .filter(result_hex__in=[result_id.hex for result_id in result_ids])
        .order_by()
        .values("result_hex")
        .annotate(reference_count=Count("pk"))
        .filter(reference_count__gt=1)
        .values_list("result_hex", flat=True)
    )
    return {UUID(result_hex) for result_hex in shared}


def reconcile_task_with_backend(
    task_row: SimulatedTask, *, result_loader: Callable[[str], TaskResult] | None = None
) -> SimulatedTask | None:
    if task_row.status in {SimulatedTask.Status.DONE, SimulatedTask.Status.FAILED}:
        return task_row

    backend_task_id = task_row.backend_task_id
    if not backend_task_id:
        return task_row

    try:
        backend_result = (result_loader or run_simulated_task.get_result)(backend_task_id)
        if not _matches_routine_argument(task_row.pk, backend_result.args, backend_result.kwargs):
            raise TaskResultMismatch("Routine argument does not match")
    except (TaskResultDoesNotExist, TaskResultMismatch):
        # Missing queue metadata cannot prove that a claimed worker has stopped.
        # Startup reconciliation retires abandoned claims after a restart.
        if task_row.status == SimulatedTask.Status.PENDING:
            return _mark_task_failed(task_row, backend_task_id, MISSING_BACKEND_RESULT)
        return _refresh_reconciled_task(task_row)

    if backend_result.status in {TaskResultStatus.READY, TaskResultStatus.RUNNING}:
        # Only the worker may claim the demo row; polling cannot reset a claim.
        return task_row

    if backend_result.status == TaskResultStatus.FAILED:
        return _mark_task_failed(
            task_row, backend_task_id, _backend_failure_message(backend_result)
        )

    if backend_result.status == TaskResultStatus.SUCCESSFUL:
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
            return _mark_task_failed(task_row, backend_task_id, INVALID_BACKEND_PAYLOAD)
        task_row.status = status
        task_row.result = result
        task_row.duration = duration
        task_row.completed_at = completed_at
        return _save_reconciled_task(
            task_row, backend_task_id, ["status", "result", "duration", "completed_at"]
        )

    return _mark_task_failed(task_row, backend_task_id, UNEXPECTED_BACKEND_RESULT)


def _matches_routine_argument(task_id: int, args: object, kwargs: object) -> bool:
    return (
        isinstance(args, list)
        and len(args) == 1
        and type(args[0]) is int
        and args[0] == task_id
        and kwargs == {}
    )


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
    # Every UTF-8 character takes at least one byte. Bound the encoding work
    # before checking the byte length and rejecting unencodable text.
    if (
        len(result) > COMPLETION_RESULT_BYTE_LIMIT
        or len(result.encode("utf-8")) > COMPLETION_RESULT_BYTE_LIMIT
    ):
        raise ValueError("Completion result exceeds the UTF-8 byte limit")
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
    return status, result, float(duration), timestamp.astimezone(UTC)


def _serialized_terminal_payload(task_row: SimulatedTask) -> dict[str, object]:
    return {
        "status": task_row.status,
        "result": task_row.result or "",
        "duration": task_row.duration,
        "completed_at": task_row.completed_at.isoformat() if task_row.completed_at else None,
    }


def _mark_task_failed(
    task_row: SimulatedTask, backend_task_id: str, result: str
) -> SimulatedTask | None:
    task_row.status = SimulatedTask.Status.FAILED
    task_row.result = result
    task_row.completed_at = task_row.completed_at or timezone.now()
    return _save_reconciled_task(task_row, backend_task_id, ["status", "result", "completed_at"])


def _save_reconciled_task(
    task_row: SimulatedTask, backend_task_id: str, fields: list[str]
) -> SimulatedTask | None:
    updated = SimulatedTask.objects.filter(
        pk=task_row.pk,
        backend_task_id=backend_task_id,
        status__in=[SimulatedTask.Status.PENDING, SimulatedTask.Status.RUNNING],
    ).update(**{field: getattr(task_row, field) for field in fields})
    if updated:
        return task_row
    return _refresh_reconciled_task(task_row)


def _refresh_reconciled_task(task_row: SimulatedTask) -> SimulatedTask | None:
    try:
        task_row.refresh_from_db()
    except SimulatedTask.DoesNotExist:
        return None
    return task_row


def _backend_failure_message(backend_result) -> str:
    if backend_result.errors:
        error = backend_result.errors[-1]
        exception_class = f"{SimulatedTaskFailure.__module__}.{SimulatedTaskFailure.__qualname__}"
        if error.exception_class_path == exception_class:
            # Also bound callers using get_result() or a supplied result loader.
            preview = error.traceback[-TRACEBACK_PREVIEW_LIMIT:]
            lines = preview.strip().splitlines()
            last_line = lines[-1] if lines else ""
            for message in FAILURE_RESULTS:
                if last_line in {
                    f"{exception_class}: {message}",
                    f"SimulatedTaskFailure: {message}",
                }:
                    return message
    return UNEXPECTED_BACKEND_RESULT
