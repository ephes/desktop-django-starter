import json
import subprocess
from pathlib import Path

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
@pytest.mark.parametrize("configured_queues", [None, "priority,desktop"])
def test_only_served_queues_prompt_on_quit(client, settings, configured_queues):
    served_queue = "default"
    if configured_queues is not None:
        settings.DESKTOP_DJANGO_WORKER_QUEUES = configured_queues
        served_queue = "desktop"

    active = [run_simulated_task.enqueue(i).id for i in range(4)]
    for queue, (running, ready) in zip((served_queue, "unserved"), (active[:2], active[2:])):
        DBTaskResult.objects.filter(pk=running).update(
            queue_name=queue, status=TaskResultStatus.RUNNING
        )
        DBTaskResult.objects.filter(pk=ready).update(queue_name=queue)

    busy = client.get("/desktop/activity/").json()
    DBTaskResult.objects.filter(pk__in=active[:2]).update(status=TaskResultStatus.SUCCESSFUL)
    idle = client.get("/desktop/activity/").json()
    assert busy == {"running_tasks": 1, "queued_tasks": 1}
    assert idle == {"running_tasks": 0, "queued_tasks": 0}

    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            "node",
            "-e",
            """
const assert = require("node:assert/strict");
const { createQuitGuard } = require("./shells/electron/scripts/quit-guard.cjs");
const [busy, idle] = JSON.parse(process.argv[1]);
async function check() {
  for (const [activity, expected] of [[busy, false], [idle, true]]) {
    let prompts = 0;
    const guard = createQuitGuard({
      fetchActivity: async () => activity,
      confirmQuit: async () => { prompts++; return false; },
    });
    assert.equal(await guard.shouldProceed(), expected);
    assert.equal(prompts, expected ? 0 : 1);
  }
}
check().catch(error => { console.error(error); process.exitCode = 1; });
""",
            json.dumps([busy, idle]),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.django_db
def test_activity_wildcard_serves_all_queues_on_the_default_backend(client, settings):
    settings.DESKTOP_DJANGO_WORKER_QUEUES = "*"
    served = run_simulated_task.enqueue(1)
    other_backend = run_simulated_task.enqueue(2)
    DBTaskResult.objects.filter(pk=served.id).update(queue_name="extra")
    DBTaskResult.objects.filter(pk=other_backend.id).update(backend_name="other")

    assert client.get("/desktop/activity/").json() == {"running_tasks": 0, "queued_tasks": 1}


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
