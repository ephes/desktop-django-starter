import pytest
from django.tasks import TaskResultStatus
from django_tasks_db.models import DBTaskResult

from tasks_demo.tasks import run_simulated_task

pytestmark = pytest.mark.django_db


def test_activity_reports_no_work_when_idle(client) -> None:
    response = client.get("/desktop/activity/")

    assert response.status_code == 200
    assert response.json() == {"running_tasks": 0, "queued_tasks": 0}


def test_activity_counts_running_and_queued_tasks(client) -> None:
    first = run_simulated_task.enqueue(1)
    run_simulated_task.enqueue(2)
    DBTaskResult.objects.filter(id=first.id).update(status=TaskResultStatus.RUNNING)

    response = client.get("/desktop/activity/")

    assert response.json() == {"running_tasks": 1, "queued_tasks": 1}
