import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from unittest import mock
from uuid import UUID

import pytest
from django.db import close_old_connections
from django.db.models import QuerySet
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
        task = SimulatedTask.objects.create(label="Restocking hay loft")

        assert task.pk is not None
        assert task.label == "Restocking hay loft"
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
                        return_value="Routine complete: supplies are counted and stowed.",
                    ):
                        result = run_simulated_task.call(task.pk)

        task.refresh_from_db()
        assert task.status == SimulatedTask.Status.DONE
        assert task.result == "Routine complete: supplies are counted and stowed."
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
                        return_value="Routine failed: the hay cart lost a wheel.",
                    ):
                        with pytest.raises(SimulatedTaskFailure):
                            run_simulated_task.call(task.pk)

        task.refresh_from_db()
        assert task.status == SimulatedTask.Status.FAILED
        assert task.result == "Routine failed: the hay cart lost a wheel."
        assert task.duration == 3.0
        assert task.completed_at is not None

    def test_interleaved_claim_runs_body_once(self, client):
        task = SimulatedTask.objects.create(label="Overlapping task")
        scheduled_task = enqueue_demo_task(task)
        scheduled_task.status = TaskResultStatus.RUNNING
        scheduled_task.save(update_fields=["status"])
        original_update = QuerySet.update
        loser_results = []
        interleaved = False

        def interleave(queryset, **kwargs):
            nonlocal interleaved
            if (
                queryset.model is SimulatedTask
                and kwargs == {"status": "RUNNING"}
                and not interleaved
            ):
                interleaved = True
                loser_results.append(run_simulated_task.call(task.pk))
            return original_update(queryset, **kwargs)

        with (
            mock.patch("django.db.models.QuerySet.update", autospec=True, side_effect=interleave),
            mock.patch("tasks_demo.tasks.time.sleep") as sleep,
            mock.patch("tasks_demo.tasks.random.uniform", return_value=4.0) as uniform,
            mock.patch("tasks_demo.tasks.random.random", return_value=1.0),
            mock.patch("tasks_demo.tasks.random.choice", return_value="Winner result"),
        ):
            result = run_simulated_task.call(task.pk)

        assert interleaved
        sleep.assert_called_once_with(4.0)
        uniform.assert_called_once()
        task.refresh_from_db()
        assert task.status == "DONE"
        assert task.result == "Winner result"
        assert loser_results[0]["status"] == "DONE"
        assert result == loser_results[0]

    def test_duplicate_during_work_preserves_running_row(self, client):
        task = SimulatedTask.objects.create(label="Winner still working")
        enqueue_demo_task(task)
        duplicates = []

        def during_work(duration):
            # READY queue state must not let polling reset the worker's claim.
            assert (
                client.get(reverse("tasks_demo:task-status")).json()["tasks"][0]["status"]
                == "RUNNING"
            )
            duplicates.append(run_simulated_task.call(task.pk))
            task.refresh_from_db()
            assert task.status == "RUNNING"
            assert task.completed_at is None

        with (
            mock.patch("tasks_demo.tasks.time.sleep", side_effect=during_work) as sleep,
            mock.patch("tasks_demo.tasks.random.uniform", return_value=4.0),
            mock.patch("tasks_demo.tasks.random.random", return_value=1.0),
            mock.patch("tasks_demo.tasks.random.choice", return_value="Winner finished"),
        ):
            result = run_simulated_task.call(task.pk)
        sleep.assert_called_once_with(4.0)
        assert duplicates[0]["status"] == "RUNNING"
        task.refresh_from_db()
        assert task.status == "DONE"
        assert task.result == result["result"] == "Winner finished"

    def test_running_duplicate_does_not_finalize_winner(self, client):
        task = SimulatedTask.objects.create(label="Running duplicate")
        scheduled_task = enqueue_demo_task(task)
        task.status = SimulatedTask.Status.RUNNING
        task.save(update_fields=["status"])
        with mock.patch("tasks_demo.tasks.time.sleep") as sleep:
            payload = run_simulated_task.call(task.pk)
        sleep.assert_not_called()
        assert payload["status"] == "RUNNING"
        assert payload["completed_at"] is None
        scheduled_task.status = TaskResultStatus.SUCCESSFUL
        scheduled_task.return_value = payload
        scheduled_task.save(update_fields=["status", "return_value"])
        response = client.get(reverse("tasks_demo:task-status"))
        task.refresh_from_db()
        assert response.json()["tasks"][0]["status"] == "RUNNING"
        assert task.completed_at is None

    def test_ready_backend_does_not_reset_claim(self, client):
        task = SimulatedTask.objects.create(label="Claimed task")
        enqueue_demo_task(task)
        task.status = SimulatedTask.Status.RUNNING
        task.save(update_fields=["status"])
        client.get(reverse("tasks_demo:task-status"))
        task.refresh_from_db()
        assert task.status == "RUNNING"

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
        assert "Start Routine" in response.content.decode()

    def test_task_list_empty_state(self, client):
        response = client.get(reverse("tasks_demo:task-list"))

        assert "No routines underway" in response.content.decode()

    def test_task_status_empty(self, client):
        response = client.get(reverse("tasks_demo:task-status"))

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data == {"tasks": []}

    def test_task_create_returns_201_and_enqueues_backend_task(self, client):
        with mock.patch("tasks_demo.views.random.choice", return_value="Restocking hay loft"):
            response = client.post(reverse("tasks_demo:task-run"))

        assert response.status_code == 201
        data = json.loads(response.content)
        task = SimulatedTask.objects.get(pk=data["id"])
        scheduled_task = DBTaskResult.objects.get(pk=task.backend_task_id)

        assert data == {"id": task.pk, "label": "Restocking hay loft", "status": "PENDING"}
        assert task.backend_task_id
        assert UUID(task.backend_task_id)
        assert scheduled_task.status == TaskResultStatus.READY

    def test_enqueue_failure_rolls_back_and_returns_controlled_error(self, client):
        with mock.patch.object(
            type(run_simulated_task), "enqueue", side_effect=RuntimeError("offline")
        ):
            response = client.post(reverse("tasks_demo:task-run"))
        assert response.status_code == 503
        assert response.json() == {"error": "Routine could not be queued. Please try again."}
        assert not SimulatedTask.objects.exists()
        assert not DBTaskResult.objects.exists()
        assert client.get(reverse("tasks_demo:task-status")).json() == {"tasks": []}

    def test_enqueue_signal_failure_rolls_back_queue_and_demo(self, client):
        from django_tasks.signals import task_enqueued

        def fail_after_insert(sender, **kwargs):
            assert DBTaskResult.objects.count() == 1
            raise RuntimeError("notification failed")

        task_enqueued.connect(fail_after_insert)
        try:
            response = client.post(reverse("tasks_demo:task-run"))
        finally:
            task_enqueued.disconnect(fail_after_insert)
        assert response.status_code == 503
        assert not DBTaskResult.objects.exists()
        assert not SimulatedTask.objects.exists()
        retry = client.post(reverse("tasks_demo:task-run"))
        assert retry.status_code == 201
        task = SimulatedTask.objects.get(pk=retry.json()["id"])
        assert DBTaskResult.objects.filter(pk=task.backend_task_id).exists()
        with (
            mock.patch("tasks_demo.tasks.time.sleep"),
            mock.patch("tasks_demo.tasks.random.random", return_value=1.0),
        ):
            run_simulated_task.call(task.pk)
        task.refresh_from_db()
        assert task.status == "DONE"

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

    def test_task_status_does_not_claim_before_worker(self, client):
        task = SimulatedTask.objects.create(label="Queued task")
        scheduled_task = enqueue_demo_task(task)
        scheduled_task.status = TaskResultStatus.RUNNING
        scheduled_task.started_at = timezone.now()
        scheduled_task.save(update_fields=["status", "started_at"])

        response = client.get(reverse("tasks_demo:task-status"))

        task.refresh_from_db()
        data = json.loads(response.content)
        assert response.status_code == 200
        assert task.status == SimulatedTask.Status.PENDING
        assert data["tasks"][0]["status"] == "PENDING"

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
            "result": "Routine complete: every stall passed inspection.",
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
        assert task.result == "Routine complete: every stall passed inspection."
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


class TestTaskClear:
    def test_clear_preserves_active_rows_and_queue(self, client):
        queued = SimulatedTask.objects.create(label="Queued")
        queued_backend = enqueue_demo_task(queued)
        running = SimulatedTask.objects.create(label="Running", status="RUNNING")
        running_backend = enqueue_demo_task(running)
        for status in ("DONE", "FAILED"):
            SimulatedTask.objects.create(label=status, status=status)

        response = client.post(reverse("tasks_demo:task-clear"))

        assert response.status_code == 200
        assert response.json() == {"cleared": True}
        assert set(SimulatedTask.objects.values_list("pk", flat=True)) == {queued.pk, running.pk}
        assert set(DBTaskResult.objects.values_list("pk", flat=True)) == {
            queued_backend.pk,
            running_backend.pk,
        }
        with (
            mock.patch("tasks_demo.tasks.time.sleep"),
            mock.patch("tasks_demo.tasks.random.random", return_value=1.0),
        ):
            result = run_simulated_task.call(queued.pk)
        queued.refresh_from_db()
        assert queued.status == result["status"] == "DONE"

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.parametrize("failed", [False, True])
    def test_clear_during_execution_preserves_worker_row(self, client, failed):
        task = SimulatedTask.objects.create(label="Working")
        backend = enqueue_demo_task(task)
        history = SimulatedTask.objects.create(label="History", status="DONE")
        sleeping = Event()
        resume = Event()

        def pause_at_sleep(duration):
            sleeping.set()
            assert resume.wait(timeout=10), "Worker was not resumed"

        def execute():
            close_old_connections()
            try:
                return run_simulated_task.call(task.pk)
            finally:
                close_old_connections()

        with (
            mock.patch("tasks_demo.tasks.time.sleep", side_effect=pause_at_sleep),
            mock.patch("tasks_demo.tasks.random.random", return_value=0.0 if failed else 1.0),
            ThreadPoolExecutor(max_workers=1) as executor,
        ):
            future = executor.submit(execute)
            try:
                assert sleeping.wait(timeout=10), "Worker did not reach sleep"
                task.refresh_from_db()
                assert task.status == "RUNNING"
                assert client.post(reverse("tasks_demo:task-clear")).status_code == 200
                assert not SimulatedTask.objects.filter(pk=history.pk).exists()
                task.refresh_from_db()
                assert task.status == "RUNNING"
                assert DBTaskResult.objects.filter(pk=backend.pk).exists()
            finally:
                resume.set()
            if failed:
                with pytest.raises(SimulatedTaskFailure):
                    future.result(timeout=10)
            else:
                assert future.result(timeout=10)["status"] == "DONE"
        task.refresh_from_db()
        assert task.status == ("FAILED" if failed else "DONE")
        assert task.completed_at is not None
        assert task.result

    @pytest.mark.parametrize("overlapping_poll", [False, True])
    def test_clear_ui_refreshes_active_rows_and_keeps_polling(self, client, overlapping_poll):
        page = client.get(reverse("tasks_demo:task-list")).content.decode()
        assert "Clear Finished Routines" in page
        assert "Queued and running routines keep working." in page
        script = next(
            block.split("</script>")[0]
            for block in page.split("<script>")[1:]
            if "const STATUS_URL" in block
        )
        harness = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const listeners = {};
const container = {innerHTML: ''};
const calls = [];
let scheduled = 0;
let staleResponse;
let cancelled = 0;
const context = {
    console,
    document: {
        cookie: 'csrftoken=test',
        getElementById(id) {
            if (id === 'task-list') return container;
            if (id === 'empty-state-template') return {innerHTML: 'Empty'};
            return {addEventListener(event, callback) {listeners[id] = callback;}};
        },
        querySelectorAll(selector) {
            return OVERLAP && selector.includes('data-status=') ? [{}] : [];
        },
        createElement() {
            return {set textContent(value) {this.innerHTML = value;}};
        },
    },
    setTimeout() {scheduled++; return 1;},
    clearTimeout() {cancelled++;},
    fetch(url, options) {
        calls.push({url, options});
        if (OVERLAP && calls.length === 1) {
            return new Promise(resolve => {staleResponse = resolve;});
        }
        return Promise.resolve({ok: true, json() {
            return Promise.resolve({tasks: [{
                id: 42, label: 'Still queued', status: 'PENDING',
                created_at: new Date().toISOString(),
            }]});
        }});
    },
};
vm.runInNewContext(SCRIPT, context);
listeners['clear-tasks-btn']();
setImmediate(() => {
    const clearIndex = OVERLAP ? 1 : 0;
    assert.equal(calls.length, clearIndex + 2);
    assert.equal(calls[clearIndex].options.method, 'POST');
    assert.equal(calls[clearIndex].options.headers['X-CSRFToken'], 'test');
    assert.equal(calls[clearIndex + 1].url, STATUS_URL);
    assert.equal(cancelled, 1);
    assert.match(container.innerHTML, /Still queued/);
    assert.match(container.innerHTML, /data-status="PENDING"/);
    assert.equal(scheduled, 1);
    assert.ok(listeners['clear-tasks-btn']);
    if (OVERLAP) {
        staleResponse({json() {return Promise.resolve({tasks: []});}});
        setImmediate(() => {
            assert.match(container.innerHTML, /Still queued/);
            assert.equal(scheduled, 1);
        });
    }
});
"""
        result = subprocess.run(
            [
                "node",
                "-e",
                "const SCRIPT = "
                + json.dumps(script)
                + "; const STATUS_URL = "
                + json.dumps(reverse("tasks_demo:task-status"))
                + "; const OVERLAP = "
                + json.dumps(overlapping_poll)
                + ";"
                + harness,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr

    def test_clear_only_accepts_post(self, client):
        assert client.get(reverse("tasks_demo:task-clear")).status_code == 405


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
