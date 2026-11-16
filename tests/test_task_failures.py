"""Failure diagnostics stay bounded and private at the routine display boundary."""

from types import SimpleNamespace

import pytest
from django.tasks import TaskResultStatus
from django.urls import reverse
from django.utils import timezone
from django_tasks_db.models import DBTaskResult

from tasks_demo.models import SimulatedTask
from tasks_demo.tasks import (
    FAILURE_RESULTS,
    UNEXPECTED_BACKEND_RESULT,
    _backend_failure_message,
    run_simulated_task,
)

pytestmark = pytest.mark.django_db
DEMO_FAILURE_CLASS = "tasks_demo.tasks.SimulatedTaskFailure"


def failed_backend(traceback, exception_class_path="builtins.RuntimeError"):
    row = SimulatedTask.objects.create(label="Synthetic failing routine", status="RUNNING")
    result = run_simulated_task.enqueue(row.pk)
    row.backend_task_id = result.id
    row.save(update_fields=["backend_task_id"])
    DBTaskResult.objects.filter(pk=result.id).update(
        status=TaskResultStatus.FAILED,
        exception_class_path=exception_class_path,
        traceback=traceback,
        finished_at=timezone.now(),
    )
    return row


@pytest.mark.parametrize("endpoint", ["task-list", "task-status"])
def test_unexpected_failures_are_safe_and_other_routines_complete(client, endpoint):
    private_traceback = (
        "synthetic-secret\x1b[31m\r\n" * 100_000
    ) + "PrivateError: synthetic-secret"
    broken = failed_backend(private_traceback)
    healthy = SimulatedTask.objects.create(label="Synthetic independent routine")
    backend = run_simulated_task.enqueue(healthy.pk)
    healthy.backend_task_id = backend.id
    healthy.save(update_fields=["backend_task_id"])
    DBTaskResult.objects.filter(pk=backend.id).update(
        status=TaskResultStatus.SUCCESSFUL,
        return_value={
            "status": "DONE",
            "result": "Safe completion",
            "duration": 1,
            "completed_at": timezone.now().isoformat(),
        },
    )
    response = client.get(reverse(f"tasks_demo:{endpoint}"))
    assert response.status_code == 200
    content = response.content.decode()
    assert "synthetic-secret" not in content
    assert "PrivateError" not in content
    assert "\\u001b" not in content and "\x1b" not in content
    assert UNEXPECTED_BACKEND_RESULT in content
    assert "Safe completion" in content
    broken.refresh_from_db()
    healthy.refresh_from_db()
    assert broken.result == UNEXPECTED_BACKEND_RESULT
    assert healthy.status == "DONE"
    assert DBTaskResult.objects.get(pk=broken.backend_task_id).traceback == private_traceback


def test_poll_bounds_traceback_before_backend_result_materialization(client, monkeypatch):
    failed_backend("synthetic-secret\n" * 100_000, DEMO_FAILURE_CLASS)
    original = DBTaskResult.task_result.fget
    seen = []

    def bounded_task_result(self):
        # Inspect the loaded field, avoiding a lazy full-field read in the oracle.
        assert "traceback" in self.__dict__
        assert len(self.__dict__["traceback"]) <= 1024
        seen.append(self.pk)
        return original(self)

    monkeypatch.setattr(DBTaskResult, "task_result", property(bounded_task_result))
    assert client.get(reverse("tasks_demo:task-status")).status_code == 200
    assert len(seen) == 1


def test_failure_preview_is_sliced_before_strip_and_split():
    class GuardedTraceback(str):
        def strip(self, *args):
            raise AssertionError("Expanded full traceback before taking a preview")

    backend = SimpleNamespace(
        errors=[
            SimpleNamespace(
                exception_class_path=DEMO_FAILURE_CLASS,
                traceback=GuardedTraceback("synthetic-secret\n" * 100_000),
            )
        ]
    )
    assert _backend_failure_message(backend) == UNEXPECTED_BACKEND_RESULT


@pytest.mark.parametrize("message", FAILURE_RESULTS)
@pytest.mark.parametrize("prefix", ["SimulatedTaskFailure", DEMO_FAILURE_CLASS])
def test_known_demo_failure_messages_are_preserved(client, message, prefix):
    row = failed_backend("Synthetic stack\n" + prefix + ": " + message, DEMO_FAILURE_CLASS)
    client.get(reverse("tasks_demo:task-status"))
    row.refresh_from_db()
    assert row.result == message


def test_exception_class_and_exact_message_must_both_be_allowlisted():
    for exception_class, line in (
        ("builtins.RuntimeError", DEMO_FAILURE_CLASS + ": " + FAILURE_RESULTS[0]),
        (DEMO_FAILURE_CLASS, DEMO_FAILURE_CLASS + ": " + FAILURE_RESULTS[0] + " synthetic-secret"),
    ):
        result = SimpleNamespace(
            errors=[
                SimpleNamespace(
                    exception_class_path=exception_class,
                    traceback=line,
                )
            ]
        )
        assert _backend_failure_message(result) == UNEXPECTED_BACKEND_RESULT
