"""Background task worker with a patchable launcher/worker split.

_launch_task(task_id) is called by the view. In production it starts a
daemon thread targeting _run_task_worker.  Tests patch _launch_task to
call _run_task_worker synchronously or to do nothing.

_run_task_worker(task_id) is the pure worker body.  Tests call it
directly with time.sleep and random.random patched for determinism.
"""

from __future__ import annotations

import random
import threading
import time

from django.utils import timezone

DURATION_RANGE: tuple[int, int] = (3, 10)
FAILURE_RATE: float = 0.2

TASK_LABELS: list[str] = [
    "Crunching numbers",
    "Analyzing data",
    "Generating report",
    "Processing records",
    "Compiling results",
    "Scanning inputs",
]

SUCCESS_RESULTS: list[str] = [
    "Processed 42 records, avg score 87.3",
    "Generated 3 summary tables",
    "Analysis complete — 12 anomalies flagged",
    "All 128 entries validated successfully",
    "Report compiled: 7 sections, 24 pages",
]

FAILURE_RESULTS: list[str] = [
    "Failed: simulated random error",
    "Error: timeout during processing",
    "Failed: unexpected data format",
]


def _launch_task(task_id: int) -> None:
    """Start the worker in a daemon thread.  Patchable in tests."""
    thread = threading.Thread(
        target=_run_task_worker,
        args=(task_id,),
        daemon=True,
    )
    thread.start()


def _run_task_worker(task_id: int) -> None:
    """Execute the simulated task.  Called directly in tests."""
    from tasks_demo.models import SimulatedTask

    task = SimulatedTask.objects.get(pk=task_id)
    task.status = SimulatedTask.Status.RUNNING
    task.save(update_fields=["status"])

    duration = random.uniform(*DURATION_RANGE)
    time.sleep(duration)

    failed = random.random() < FAILURE_RATE
    task.status = SimulatedTask.Status.FAILED if failed else SimulatedTask.Status.DONE
    task.result = random.choice(FAILURE_RESULTS if failed else SUCCESS_RESULTS)
    task.duration = round(duration, 1)
    task.completed_at = timezone.now()
    task.save(update_fields=["status", "result", "duration", "completed_at"])
