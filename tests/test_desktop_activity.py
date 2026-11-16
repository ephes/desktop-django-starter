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


def test_activity_transition_between_old_count_queries_cannot_report_idle(client):
    from django.db import connection

    backend = run_simulated_task.enqueue(1)
    statements = []

    def transition_after_first_read(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if sql.startswith("SELECT") and "COUNT(" in sql and DBTaskResult._meta.db_table in sql:
            statements.append(sql)
            if len(statements) == 1:
                # Old running count observed zero. Move READY to RUNNING before
                # its second (queued) read; two separate queries report idle.
                DBTaskResult.objects.filter(pk=backend.id).update(status=TaskResultStatus.RUNNING)
        return result

    with connection.execute_wrapper(transition_after_first_read):
        response = client.get("/desktop/activity/")
    assert sum(response.json().values()) == 1
    assert len(statements) == 1


def test_activity_without_backend_uses_no_database(django_assert_num_queries):
    from unittest.mock import patch

    from desktop_django_starter.activity import background_task_counts

    with patch("desktop_django_starter.activity.apps.is_installed", return_value=False):
        with django_assert_num_queries(0):
            assert background_task_counts() == {"running_tasks": 0, "queued_tasks": 0}
