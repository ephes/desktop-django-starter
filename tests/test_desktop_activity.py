import pytest
from django.db import DEFAULT_DB_ALIAS, connections
from django.tasks import TaskResultStatus
from django_tasks_db.models import DBTaskResult

from tasks_demo.tasks import run_simulated_task


@pytest.mark.django_db
def test_activity_reports_no_work_when_idle(client) -> None:
    response = client.get("/desktop/activity/")

    assert response.status_code == 200
    assert response.json() == {"running_tasks": 0, "queued_tasks": 0}


@pytest.mark.django_db
def test_activity_counts_running_and_queued_tasks(client) -> None:
    first = run_simulated_task.enqueue(1)
    run_simulated_task.enqueue(2)
    DBTaskResult.objects.filter(id=first.id).update(status=TaskResultStatus.RUNNING)

    response = client.get("/desktop/activity/")

    assert response.json() == {"running_tasks": 1, "queued_tasks": 1}


@pytest.mark.django_db
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


def test_activity_reads_task_writer(
    client, django_db_blocker, monkeypatch, settings, tmp_path
) -> None:
    reader, writer = "task_reader", "task_writer"
    aliases = (reader, writer)
    for alias in aliases:
        monkeypatch.setitem(
            connections.databases,
            alias,
            {**connections.databases[DEFAULT_DB_ALIAS], "NAME": str(tmp_path / f"{alias}.sqlite3")},
        )

    class TaskRouter:
        def db_for_read(self, model, **hints):
            return reader if model is DBTaskResult else None

        def db_for_write(self, model, **hints):
            return writer if model is DBTaskResult else None

    settings.DATABASE_ROUTERS = [TaskRouter()]
    with django_db_blocker.unblock():
        try:
            for alias in aliases:
                with connections[alias].schema_editor() as editor:
                    editor.create_model(DBTaskResult)

            task_result = run_simulated_task.enqueue(1)
            DBTaskResult.objects.filter(pk=task_result.id).update(status=TaskResultStatus.RUNNING)
            assert not DBTaskResult.objects.using(reader).exists()

            response = client.get("/desktop/activity/")
            assert response.json() == {"running_tasks": 1, "queued_tasks": 0}
        finally:
            for alias in aliases:
                connections[alias].close()
                del connections[alias]


@pytest.mark.django_db
def test_activity_without_backend_uses_no_database(django_assert_num_queries):
    from unittest.mock import patch

    from desktop_django_starter.activity import background_task_counts

    with patch("desktop_django_starter.activity.apps.is_installed", return_value=False):
        with django_assert_num_queries(0):
            assert background_task_counts() == {"running_tasks": 0, "queued_tasks": 0}


@pytest.mark.django_db
def test_activity_stays_fresh_with_cache_middleware(client, settings, tmp_path) -> None:
    settings.DESKTOP_DJANGO_AUTH_TOKEN = ""
    settings.DESKTOP_DJANGO_REQUIRE_AUTH_TOKEN = False
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": str(tmp_path),
        }
    }
    settings.MIDDLEWARE = [
        "django.middleware.cache.UpdateCacheMiddleware",
        *settings.MIDDLEWARE,
        "django.middleware.cache.FetchFromCacheMiddleware",
    ]

    idle = client.get("/desktop/activity/")
    assert idle.json() == {"running_tasks": 0, "queued_tasks": 0}

    run_simulated_task.enqueue(1)
    active = client.get("/desktop/activity/")
    assert active.json() == {"running_tasks": 0, "queued_tasks": 1}
    for response in (idle, active):
        assert "no-store" in response["Cache-Control"].split(", ")
