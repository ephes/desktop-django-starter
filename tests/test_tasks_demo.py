import json
from datetime import timedelta
from unittest import mock
from uuid import UUID

import pytest
from django.urls import reverse
from django.utils import timezone
from django_tasks import TaskResultStatus
from django_tasks_db.models import DBTaskResult

from tasks_demo.apps import TasksDemoConfig
from tasks_demo.models import SimulatedTask
from tasks_demo.tasks import SimulatedTaskFailure, run_simulated_task

pytestmark = pytest.mark.django_db


def enqueue_demo_task(task: SimulatedTask) -> DBTaskResult:
    backend_result = run_simulated_task.enqueue(task.pk)
    task.backend_task_id = backend_result.id
    task.save(update_fields=["backend_task_id"])
    return DBTaskResult.objects.get(pk=backend_result.id)


class TestSimulatedTaskModel:
    def test_create_task_with_defaults(self):
        task = SimulatedTask.objects.create(label="Crunching numbers")

        assert task.pk is not None
        assert task.label == "Crunching numbers"
        assert task.backend_task_id == ""
        assert task.status == SimulatedTask.Status.PENDING
        assert task.result is None
        assert task.duration is None
        assert task.created_at is not None
        assert task.completed_at is None

    def test_status_choices_are_valid(self):
        choices = {c.value for c in SimulatedTask.Status}
        assert choices == {"PENDING", "RUNNING", "DONE", "FAILED"}

    def test_ordering_is_newest_first(self):
        task_a = SimulatedTask.objects.create(label="First")
        task_b = SimulatedTask.objects.create(label="Second")

        tasks = list(SimulatedTask.objects.all())
        assert tasks[0].pk == task_b.pk
        assert tasks[1].pk == task_a.pk


class TestRunSimulatedTask:
    def test_task_transitions_to_done(self):
        task = SimulatedTask.objects.create(label="Test task")

        with mock.patch("tasks_demo.tasks.time.sleep"):
            with mock.patch("tasks_demo.tasks.random.random", return_value=1.0):
                with mock.patch("tasks_demo.tasks.random.uniform", return_value=4.0):
                    with mock.patch(
                        "tasks_demo.tasks.random.choice",
                        return_value="Generated 3 summary tables",
                    ):
                        result = run_simulated_task.call(task.pk)

        task.refresh_from_db()
        assert task.status == SimulatedTask.Status.DONE
        assert task.result == "Generated 3 summary tables"
        assert task.duration == 4.0
        assert task.completed_at is not None
        assert result["status"] == SimulatedTask.Status.DONE

    def test_task_transitions_to_failed(self):
        task = SimulatedTask.objects.create(label="Failing task")

        with mock.patch("tasks_demo.tasks.time.sleep"):
            with mock.patch("tasks_demo.tasks.random.random", return_value=0.0):
                with mock.patch("tasks_demo.tasks.random.uniform", return_value=3.0):
                    with mock.patch(
                        "tasks_demo.tasks.random.choice",
                        return_value="Failed: simulated random error",
                    ):
                        with pytest.raises(SimulatedTaskFailure):
                            run_simulated_task.call(task.pk)

        task.refresh_from_db()
        assert task.status == SimulatedTask.Status.FAILED
        assert task.result == "Failed: simulated random error"
        assert task.duration == 3.0
        assert task.completed_at is not None

    def test_terminal_tasks_are_left_unchanged(self):
        completed_at = timezone.now()
        task = SimulatedTask.objects.create(
            label="Already failed",
            status=SimulatedTask.Status.FAILED,
            result="Abandoned - app restarted",
            duration=2.0,
            completed_at=completed_at,
        )

        with mock.patch("tasks_demo.tasks.time.sleep") as sleep:
            result = run_simulated_task.call(task.pk)

        task.refresh_from_db()
        sleep.assert_not_called()
        assert task.status == SimulatedTask.Status.FAILED
        assert result == {
            "status": SimulatedTask.Status.FAILED,
            "result": "Abandoned - app restarted",
            "duration": 2.0,
            "completed_at": completed_at.isoformat(),
        }


class TestTaskViews:
    def test_task_list_page_renders(self, client):
        response = client.get(reverse("tasks_demo:task-list"))

        assert response.status_code == 200
        assert "Run Task" in response.content.decode()

    def test_task_list_empty_state(self, client):
        response = client.get(reverse("tasks_demo:task-list"))

        assert "No tasks yet" in response.content.decode()

    def test_task_status_empty(self, client):
        response = client.get(reverse("tasks_demo:task-status"))

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data == {"tasks": []}

    def test_task_create_returns_201_and_enqueues_backend_task(self, client):
        with mock.patch("tasks_demo.views.random.choice", return_value="Crunching numbers"):
            response = client.post(reverse("tasks_demo:task-run"))

        assert response.status_code == 201
        data = json.loads(response.content)
        task = SimulatedTask.objects.get(pk=data["id"])
        scheduled_task = DBTaskResult.objects.get(pk=task.backend_task_id)

        assert data == {"id": task.pk, "label": "Crunching numbers", "status": "PENDING"}
        assert task.backend_task_id
        assert UUID(task.backend_task_id)
        assert scheduled_task.status == TaskResultStatus.READY

    def test_task_create_only_accepts_post(self, client):
        response = client.get(reverse("tasks_demo:task-run"))

        assert response.status_code == 405

    def test_task_status_returns_created_tasks(self, client):
        SimulatedTask.objects.create(
            label="Done task",
            backend_task_id="done-task-id",
            status=SimulatedTask.Status.DONE,
            result="All good",
            duration=5.2,
            completed_at=timezone.now(),
        )

        response = client.get(reverse("tasks_demo:task-status"))

        data = json.loads(response.content)
        assert len(data["tasks"]) == 1
        task_data = data["tasks"][0]
        assert task_data["label"] == "Done task"
        assert task_data["status"] == "DONE"
        assert task_data["result"] == "All good"
        assert task_data["duration"] == 5.2
        assert task_data["created_at"] is not None
        assert task_data["completed_at"] is not None

    def test_task_status_promotes_ready_backend_task_to_running(self, client):
        task = SimulatedTask.objects.create(label="Queued task")
        scheduled_task = enqueue_demo_task(task)
        scheduled_task.status = TaskResultStatus.RUNNING
        scheduled_task.started_at = timezone.now()
        scheduled_task.save(update_fields=["status", "started_at"])

        response = client.get(reverse("tasks_demo:task-status"))

        task.refresh_from_db()
        data = json.loads(response.content)
        assert response.status_code == 200
        assert task.status == SimulatedTask.Status.RUNNING
        assert data["tasks"][0]["status"] == "RUNNING"

    def test_task_status_recovers_successful_backend_result(self, client):
        task = SimulatedTask.objects.create(
            label="Recoverable task",
            status=SimulatedTask.Status.RUNNING,
        )
        scheduled_task = enqueue_demo_task(task)
        completed_at = timezone.now()
        scheduled_task.status = TaskResultStatus.SUCCESSFUL
        scheduled_task.return_value = {
            "status": SimulatedTask.Status.DONE,
            "result": "Processed 42 records, avg score 87.3",
            "duration": 4.2,
            "completed_at": completed_at.isoformat(),
        }
        scheduled_task.finished_at = completed_at
        scheduled_task.save(update_fields=["status", "return_value", "finished_at"])

        response = client.get(reverse("tasks_demo:task-status"))

        task.refresh_from_db()
        data = json.loads(response.content)
        assert response.status_code == 200
        assert task.status == SimulatedTask.Status.DONE
        assert task.result == "Processed 42 records, avg score 87.3"
        assert task.duration == 4.2
        assert task.completed_at == completed_at
        assert data["tasks"][0]["status"] == "DONE"

    def test_task_status_marks_missing_backend_results_failed(self, client):
        task = SimulatedTask.objects.create(
            label="Missing backend task",
            backend_task_id="00000000-0000-0000-0000-000000000000",
        )

        response = client.get(reverse("tasks_demo:task-status"))

        task.refresh_from_db()
        data = json.loads(response.content)
        assert response.status_code == 200
        assert task.status == SimulatedTask.Status.FAILED
        assert task.result == "Task result could not be found."
        assert task.completed_at is not None
        assert data["tasks"][0]["status"] == "FAILED"

    def test_task_status_handles_empty_backend_tracebacks(self, client):
        task = SimulatedTask.objects.create(
            label="Broken backend task",
            status=SimulatedTask.Status.RUNNING,
        )
        scheduled_task = enqueue_demo_task(task)
        task.backend_task_id = str(scheduled_task.pk)
        task.save(update_fields=["backend_task_id"])
        scheduled_task.status = TaskResultStatus.FAILED
        scheduled_task.exception_class_path = "builtins.RuntimeError"
        scheduled_task.traceback = ""
        scheduled_task.finished_at = timezone.now()
        scheduled_task.save(
            update_fields=["status", "exception_class_path", "traceback", "finished_at"]
        )

        response = client.get(reverse("tasks_demo:task-status"))

        task.refresh_from_db()
        data = json.loads(response.content)
        assert response.status_code == 200
        assert task.status == SimulatedTask.Status.FAILED
        assert task.result == "Task exited before the demo row was finalized."
        assert data["tasks"][0]["status"] == "FAILED"

    def test_task_status_only_accepts_get(self, client):
        response = client.post(reverse("tasks_demo:task-status"))

        assert response.status_code == 405

    def test_task_list_sets_csrf_cookie(self, client):
        response = client.get(reverse("tasks_demo:task-list"))

        assert "csrftoken" in response.cookies


class TestStartupReconciliation:
    def test_stale_pending_tasks_marked_failed(self):
        task = SimulatedTask.objects.create(
            label="Stale pending",
            backend_task_id="stale-pending",
            status=SimulatedTask.Status.PENDING,
        )

        TasksDemoConfig.reconcile_stale_tasks()

        task.refresh_from_db()
        assert task.status == SimulatedTask.Status.FAILED
        assert task.result == "Abandoned - app restarted"
        assert task.completed_at is not None

    def test_stale_running_tasks_marked_failed(self):
        task = SimulatedTask.objects.create(
            label="Stale running",
            backend_task_id="stale-running",
            status=SimulatedTask.Status.RUNNING,
        )

        TasksDemoConfig.reconcile_stale_tasks()

        task.refresh_from_db()
        assert task.status == SimulatedTask.Status.FAILED
        assert task.result == "Abandoned - app restarted"
        assert task.completed_at is not None

    def test_completed_tasks_not_affected(self):
        completed_at = timezone.now() - timedelta(minutes=1)
        task = SimulatedTask.objects.create(
            label="Done task",
            backend_task_id="done-task",
            status=SimulatedTask.Status.DONE,
            result="All good",
            completed_at=completed_at,
        )

        TasksDemoConfig.reconcile_stale_tasks()

        task.refresh_from_db()
        assert task.status == SimulatedTask.Status.DONE
        assert task.result == "All good"
        assert task.completed_at == completed_at
