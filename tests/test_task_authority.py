from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from unittest import mock

import pytest
from django.db import close_old_connections
from django.tasks import TaskResultStatus
from django.urls import reverse
from django.utils import timezone
from django_tasks_db.models import DBTaskResult

from tasks_demo.models import SimulatedTask
from tasks_demo.tasks import SimulatedTaskFailure, reconcile_task_with_backend, run_simulated_task

pytestmark = pytest.mark.django_db


def queued_task():
    row = SimulatedTask.objects.create(label="Synthetic routine")
    result = run_simulated_task.enqueue(row.pk)
    row.backend_task_id = result.id
    row.save(update_fields=["backend_task_id"])
    return row, DBTaskResult.objects.get(pk=result.id)


@pytest.mark.parametrize(
    "change",
    [
        [],
        ["invalid"],
        None,
        {},
        {"status": "UNKNOWN"},
        {"status": []},
        {"duration": float("nan")},
        {"duration": float("inf")},
        {"duration": -1},
        {"duration": True},
        {"duration": "2"},
        {"duration": None},
        {"duration": 10**400},
        {"completed_at": "bad-date"},
        {"completed_at": 42},
        {"completed_at": "2026-01-01T00:00:00"},
        {"completed_at": None},
        {"result": ["invalid"]},
    ],
)
def test_status_rejects_invalid_success_payload(client, change):
    row, backend = queued_task()
    payload = {
        "status": "DONE",
        "result": "Synthetic completion",
        "duration": 2.0,
        "completed_at": timezone.now().isoformat(),
    }
    if isinstance(change, dict) and change:
        payload.update(change)
    else:
        payload = change
    backend.status = TaskResultStatus.SUCCESSFUL
    # Nonfinite numbers cannot be stored in SQLite JSON; inject the backend return
    # at its public lookup boundary while still exercising the real HTTP caller.
    with mock.patch.object(
        DBTaskResult,
        "task_result",
        new_callable=mock.PropertyMock,
        return_value=SimpleNamespace(
            task=run_simulated_task, status=TaskResultStatus.SUCCESSFUL, return_value=payload
        ),
    ):
        response = client.get(reverse("tasks_demo:task-status"))
    assert response.status_code == 200
    row.refresh_from_db()
    assert row.status == "FAILED"
    assert row.result == "Task returned an invalid completion payload."
    assert row.duration is None
    assert row.completed_at is not None


@pytest.mark.parametrize("out_of_range", ["0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00"])
def test_poll_admits_completion_timestamps_in_utc(client, out_of_range):
    invalid, invalid_backend = queued_task()
    valid, valid_backend = queued_task()
    for backend, timestamp in (
        (invalid_backend, out_of_range),
        (valid_backend, "2026-04-09T00:15:00+05:30"),
    ):
        backend.status = TaskResultStatus.SUCCESSFUL
        backend.return_value = {
            "status": "DONE",
            "result": "Synthetic completion",
            "duration": 2.0,
            "completed_at": timestamp,
        }
        backend.save(update_fields=["status", "return_value"])

    response = client.get(reverse("tasks_demo:task-status"))
    assert response.status_code == 200
    rows = {row["id"]: row for row in response.json()["tasks"]}
    assert rows[invalid.pk]["status"] == "FAILED"
    assert rows[invalid.pk]["result"] == "Task returned an invalid completion payload."
    assert rows[invalid.pk]["duration"] is None
    assert rows[valid.pk]["status"] == "DONE"
    assert rows[valid.pk]["completed_at"] == "2026-04-08T18:45:00+00:00"


@pytest.mark.parametrize("status", ["DONE", "FAILED"])
def test_invalid_payload_cannot_replace_worker_completion(client, status):
    row, backend = queued_task()
    SimulatedTask.objects.filter(pk=row.pk).update(status=status, result="Worker result")
    backend.status = TaskResultStatus.SUCCESSFUL
    backend.return_value = ["invalid"]
    backend.save(update_fields=["status", "return_value"])
    assert client.get(reverse("tasks_demo:task-status")).status_code == 200
    row.refresh_from_db()
    assert row.status == status
    assert row.result == "Worker result"


def test_old_backend_completion_cannot_finalize_rebound_routine():
    row, old_backend = queued_task()
    replacement = run_simulated_task.enqueue(row.pk)

    def load_result(backend_id):
        assert backend_id == str(old_backend.pk)
        SimulatedTask.objects.filter(pk=row.pk).update(backend_task_id=replacement.id)
        return SimpleNamespace(
            status=TaskResultStatus.SUCCESSFUL,
            return_value={
                "status": "DONE",
                "result": "Completion for the old backend ID",
                "duration": 2.0,
                "completed_at": timezone.now().isoformat(),
            },
        )

    reconciled = reconcile_task_with_backend(row, result_loader=load_result)
    row.refresh_from_db()
    assert reconciled is not None
    for current in (row, reconciled):
        assert current.backend_task_id == replacement.id
        assert current.status == SimulatedTask.Status.PENDING
        assert current.result is None
        assert current.duration is None
        assert current.completed_at is None


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("retirement", ["missing", "terminal", "clear"])
@pytest.mark.parametrize("failed", [False, True])
def test_late_worker_respects_current_claim(client, retirement, failed):
    row, backend = queued_task()
    sleeping, resume = Event(), Event()

    def pause(duration):
        sleeping.set()
        assert resume.wait(10)

    def execute():
        close_old_connections()
        try:
            return run_simulated_task.call(row.pk)
        finally:
            close_old_connections()

    with (
        mock.patch("tasks_demo.tasks.time.sleep", side_effect=pause),
        mock.patch("tasks_demo.tasks.random.random", return_value=0.0 if failed else 1.0),
        ThreadPoolExecutor(max_workers=1) as executor,
    ):
        future = executor.submit(execute)
        try:
            assert sleeping.wait(10)
            if retirement == "missing":
                backend.delete()
                data = client.get(reverse("tasks_demo:task-status")).json()
                assert data["tasks"][0]["status"] == "RUNNING"
            else:
                backend.status = TaskResultStatus.FAILED
                backend.save(update_fields=["status"])
                assert (
                    client.get(reverse("tasks_demo:task-status")).json()["tasks"][0]["status"]
                    == "FAILED"
                )
            if retirement != "terminal":
                assert client.post(reverse("tasks_demo:task-clear")).status_code == 200
        finally:
            resume.set()
        if retirement == "missing" and failed:
            with pytest.raises(SimulatedTaskFailure):
                future.result(10)
        else:
            future.result(10)
    if retirement == "clear":
        assert not SimulatedTask.objects.filter(pk=row.pk).exists()
    else:
        row.refresh_from_db()
        assert row.status == ("DONE" if retirement == "missing" and not failed else "FAILED")
        if retirement == "terminal":
            assert row.result == "Task exited before the demo row was finalized."
