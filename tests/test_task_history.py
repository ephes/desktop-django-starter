import pytest
from django.tasks import TaskResultStatus, task
from django.urls import reverse
from django.utils import timezone
from django_tasks_db.models import DBTaskResult

from tasks_demo import tasks as task_module
from tasks_demo.models import SimulatedTask
from tasks_demo.tasks import run_simulated_task

pytestmark = pytest.mark.django_db


@task()
def other_task():
    pass


@pytest.mark.parametrize("endpoint", ["task-list", "task-status"])
def test_history_is_bounded_but_all_active_rows_remain(
    client, django_assert_max_num_queries, endpoint
):
    SimulatedTask.objects.bulk_create(
        [
            SimulatedTask(
                label=f"Old synthetic routine {i}", status="DONE", completed_at=timezone.now()
            )
            for i in range(1500)
        ]
    )
    active = []
    for i in range(125):
        row = SimulatedTask.objects.create(label=f"Active synthetic routine {i}")
        result = run_simulated_task.enqueue(row.pk)
        row.backend_task_id = result.id
        row.save(update_fields=["backend_task_id"])
        active.append(row.pk)
    # Three SELECTs: active demo rows, bulk queue lookup, bounded history.
    with django_assert_max_num_queries(3):
        response = client.get(reverse(f"tasks_demo:{endpoint}"))
    assert response.status_code == 200
    tasks = response.context["tasks"] if endpoint == "task-list" else response.json()["tasks"]
    ids = [row.pk if endpoint == "task-list" else row["id"] for row in tasks]
    assert len(ids) == 225
    assert set(active) <= set(ids)
    assert len(set(ids)) == len(ids)
    assert SimulatedTask.objects.count() == 1625  # Visibility is not deletion/retention.


def test_new_completion_of_old_task_is_visible_immediately(client):
    old = SimulatedTask.objects.create(label="Old active task")
    backend = run_simulated_task.enqueue(old.pk)
    old.backend_task_id = backend.id
    old.save(update_fields=["backend_task_id"])
    SimulatedTask.objects.bulk_create(
        [
            SimulatedTask(label=f"Finished task {i}", status="DONE", completed_at=timezone.now())
            for i in range(110)
        ]
    )
    DBTaskResult.objects.filter(pk=backend.id).update(
        status=TaskResultStatus.SUCCESSFUL,
        return_value={
            "status": "DONE",
            "result": "Fresh completion",
            "duration": 1,
            "completed_at": timezone.now().isoformat(),
        },
    )
    tasks = client.get(reverse("tasks_demo:task-status")).json()["tasks"]
    assert len(tasks) == 100
    assert next(row for row in tasks if row["id"] == old.pk)["result"] == "Fresh completion"


def test_bulk_lookup_preserves_missing_and_mismatched_result_rules(client):
    rows = [
        SimulatedTask.objects.create(label="Missing pending", backend_task_id="not-a-uuid"),
        SimulatedTask.objects.create(
            label="Missing running", backend_task_id="not-a-uuid", status="RUNNING"
        ),
        SimulatedTask.objects.create(label="Mismatched pending"),
    ]
    backend = run_simulated_task.enqueue(rows[2].pk)
    # A valid task object belonging to a different function must not be admitted.
    DBTaskResult.objects.filter(pk=backend.id).update(task_path=f"{__name__}.other_task")
    rows[2].backend_task_id = backend.id
    rows[2].save(update_fields=["backend_task_id"])
    response = client.get(reverse("tasks_demo:task-status"))
    assert response.status_code == 200
    for row, expected in zip(rows, ["FAILED", "RUNNING", "FAILED"], strict=True):
        row.refresh_from_db()
        assert row.status == expected


@pytest.fixture
def completed_backend():
    def create(label, **overrides):
        row = SimulatedTask.objects.create(label=label)
        backend = run_simulated_task.enqueue(row.pk)
        row.backend_task_id = backend.id
        row.save(update_fields=["backend_task_id"])
        fields = {
            "status": TaskResultStatus.SUCCESSFUL,
            "return_value": {
                "status": "DONE",
                "result": f"{label} completed",
                "duration": 1,
                "completed_at": timezone.now().isoformat(),
            },
        }
        DBTaskResult.objects.filter(pk=backend.id).update(**(fields | overrides))
        return row

    return create


@pytest.mark.parametrize(
    "identity",
    [
        {"task_path": "tasks_demo.retired.retired_routine"},
        {"backend_name": "retired-backend"},
        {"queue_name": "retired-queue"},
    ],
    ids=["retired-task", "different-backend", "different-queue"],
)
def test_poll_rejects_unrelated_result_identity(client, completed_backend, identity, settings):
    default = settings.TASKS["default"]
    settings.TASKS = {
        **settings.TASKS,
        "default": default | {"QUEUES": ["default", "retired-queue"]},
        "retired-backend": default,
    }
    unrelated = completed_backend("Unrelated routine", **identity)
    healthy = completed_backend("Healthy routine")

    response = client.get(reverse("tasks_demo:task-status"))

    assert response.status_code == 200
    by_id = {row["id"]: row for row in response.json()["tasks"]}
    assert by_id[unrelated.pk]["status"] == "FAILED"
    assert by_id[unrelated.pk]["result"] == task_module.MISSING_BACKEND_RESULT
    assert by_id[healthy.pk]["status"] == "DONE"
    assert by_id[healthy.pk]["result"] == "Healthy routine completed"


def test_worker_completion_between_active_and_history_queries_is_not_duplicated(
    client, monkeypatch
):
    row = SimulatedTask.objects.create(label="Finishing during poll")
    reconcile = task_module.reconcile_task_with_backend

    def finish_after_reconciliation(task_row, **kwargs):
        stale = reconcile(task_row, **kwargs)
        SimulatedTask.objects.filter(pk=row.pk).update(status="DONE", completed_at=timezone.now())
        return stale

    monkeypatch.setattr(task_module, "reconcile_task_with_backend", finish_after_reconciliation)
    tasks = client.get(reverse("tasks_demo:task-status")).json()["tasks"]
    assert [(item["id"], item["status"]) for item in tasks] == [(row.pk, "DONE")]


@pytest.mark.parametrize("backend_outcome", ["missing", "successful"])
def test_poll_omits_routine_cleared_during_reconciliation(client, monkeypatch, backend_outcome):
    cleared = SimulatedTask.objects.create(
        label="Cleared during poll", status=SimulatedTask.Status.RUNNING
    )
    remaining = SimulatedTask.objects.create(label="Still active")
    backend = run_simulated_task.enqueue(cleared.pk)
    cleared.backend_task_id = backend.id
    cleared.save(update_fields=["backend_task_id"])
    if backend_outcome == "successful":
        DBTaskResult.objects.filter(pk=backend.id).update(
            status=TaskResultStatus.SUCCESSFUL,
            return_value={
                "status": "DONE",
                "result": "Backend completion",
                "duration": 1,
                "completed_at": timezone.now().isoformat(),
            },
        )
    else:
        DBTaskResult.objects.filter(pk=backend.id).delete()

    reconcile = task_module.reconcile_task_with_backend

    def clear_before_reconciliation(task_row, **kwargs):
        if task_row.pk == cleared.pk:
            SimulatedTask.objects.filter(pk=cleared.pk).update(
                status=SimulatedTask.Status.DONE, completed_at=timezone.now()
            )
            assert client.post(reverse("tasks_demo:task-clear")).status_code == 200
        return reconcile(task_row, **kwargs)

    monkeypatch.setattr(task_module, "reconcile_task_with_backend", clear_before_reconciliation)
    response = client.get(reverse("tasks_demo:task-status"))
    assert response.status_code == 200
    assert [row["id"] for row in response.json()["tasks"]] == [remaining.pk]
    assert not SimulatedTask.objects.filter(pk=cleared.pk).exists()
