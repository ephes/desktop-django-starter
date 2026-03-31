import json
from unittest import mock

import pytest
from django.urls import reverse
from django.utils import timezone

from tasks_demo.apps import TasksDemoConfig
from tasks_demo.models import SimulatedTask
from tasks_demo.worker import _run_task_worker

pytestmark = pytest.mark.django_db


class TestSimulatedTaskModel:
    def test_create_task_with_defaults(self):
        task = SimulatedTask.objects.create(label="Crunching numbers")

        assert task.pk is not None
        assert task.label == "Crunching numbers"
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


class TestRunTaskWorker:
    def test_worker_transitions_to_done(self):
        task = SimulatedTask.objects.create(label="Test task")

        with mock.patch("tasks_demo.worker.time.sleep"):
            with mock.patch("tasks_demo.worker.random.random", return_value=1.0):
                with mock.patch(
                    "tasks_demo.worker.random.uniform", return_value=4.0
                ):
                    _run_task_worker(task.pk)

        task.refresh_from_db()
        assert task.status == SimulatedTask.Status.DONE
        assert task.result is not None
        assert task.duration == 4.0
        assert task.completed_at is not None

    def test_worker_transitions_to_failed(self):
        task = SimulatedTask.objects.create(label="Failing task")

        with mock.patch("tasks_demo.worker.time.sleep"):
            with mock.patch("tasks_demo.worker.random.random", return_value=0.0):
                with mock.patch(
                    "tasks_demo.worker.random.uniform", return_value=3.0
                ):
                    _run_task_worker(task.pk)

        task.refresh_from_db()
        assert task.status == SimulatedTask.Status.FAILED
        assert task.result is not None
        assert "error" in task.result.lower() or "failed" in task.result.lower()
        assert task.duration == 3.0
        assert task.completed_at is not None


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

    def test_task_create_returns_201(self, client):
        with mock.patch("tasks_demo.views._launch_task"):
            response = client.post(reverse("tasks_demo:task-run"))

        assert response.status_code == 201
        data = json.loads(response.content)
        assert "id" in data
        assert "label" in data
        assert data["status"] == "PENDING"

    def test_task_create_only_accepts_post(self, client):
        response = client.get(reverse("tasks_demo:task-run"))

        assert response.status_code == 405

    def test_task_status_returns_created_tasks(self, client):
        SimulatedTask.objects.create(
            label="Done task",
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

    def test_task_status_only_accepts_get(self, client):
        response = client.post(reverse("tasks_demo:task-status"))

        assert response.status_code == 405

    def test_task_list_sets_csrf_cookie(self, client):
        response = client.get(reverse("tasks_demo:task-list"))

        assert "csrftoken" in response.cookies


class TestStartupReconciliation:
    def test_stale_pending_tasks_marked_failed(self):
        task = SimulatedTask.objects.create(
            label="Stale pending", status=SimulatedTask.Status.PENDING
        )

        TasksDemoConfig.reconcile_stale_tasks()

        task.refresh_from_db()
        assert task.status == SimulatedTask.Status.FAILED
        assert task.result == "Abandoned \u2014 app restarted"
        assert task.completed_at is not None

    def test_stale_running_tasks_marked_failed(self):
        task = SimulatedTask.objects.create(
            label="Stale running", status=SimulatedTask.Status.RUNNING
        )

        TasksDemoConfig.reconcile_stale_tasks()

        task.refresh_from_db()
        assert task.status == SimulatedTask.Status.FAILED
        assert task.result == "Abandoned \u2014 app restarted"
        assert task.completed_at is not None

    def test_completed_tasks_not_affected(self):
        task = SimulatedTask.objects.create(
            label="Done task",
            status=SimulatedTask.Status.DONE,
            result="All good",
            completed_at=timezone.now(),
        )

        TasksDemoConfig.reconcile_stale_tasks()

        task.refresh_from_db()
        assert task.status == SimulatedTask.Status.DONE
        assert task.result == "All good"
