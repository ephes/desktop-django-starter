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
from tasks_demo.tasks import SimulatedTaskFailure, run_simulated_task

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
