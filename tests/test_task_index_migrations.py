"""Upgrade and reverse the app-owned indexes against the locked backend schema."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.tasks import TaskResultStatus
from django.utils import timezone
from django_tasks_db.models import DBTaskResult

from tasks_demo.models import SimulatedTask


@pytest.mark.django_db(transaction=True)
def test_task_indexes_upgrade_reverse_and_preserve_rows():
    routine = SimulatedTask.objects.create(label="Synthetic retained history", status="DONE")
    backend = DBTaskResult.objects.create(
        status=TaskResultStatus.SUCCESSFUL,
        args_kwargs={"args": [], "kwargs": {}},
        task_path="tasks_demo.tasks.run_simulated_task",
        backend_name="default",
        run_after=timezone.now(),
    )
    routine_indexes = {"routine_active_created_idx", "routine_history_order_idx"}
    backend_index = "dds_backend_status_idx"

    def indexes(model):
        with connection.cursor() as cursor:
            return connection.introspection.get_constraints(cursor, model._meta.db_table)

    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    old = [("tasks_demo", "0002_simulatedtask_backend_task_id")]
    try:
        executor.migrate(old)
        assert routine_indexes.isdisjoint(indexes(SimulatedTask))
        assert backend_index not in indexes(DBTaskResult)
        MigrationExecutor(connection).migrate(latest)
        assert routine_indexes <= indexes(SimulatedTask).keys()
        constraints = indexes(DBTaskResult)
        assert constraints[backend_index]["columns"] == ["status"]
        assert constraints[backend_index]["index"]
        assert "tasks_db_new_ordering_idx" in constraints  # Dependency's worker index stays.
        with connection.cursor() as cursor:
            cursor.execute("SELECT sql FROM sqlite_master WHERE name = %s", [backend_index])
            assert "WHERE" not in cursor.fetchone()[0]  # Ordinary, includes RUNNING.
        assert SimulatedTask.objects.get(pk=routine.pk).status == "DONE"
        assert DBTaskResult.objects.get(pk=backend.pk).status == TaskResultStatus.SUCCESSFUL
    finally:
        MigrationExecutor(connection).migrate(latest)


def test_core_app_has_no_backend_migration_dependency():
    """Removing the optional extension and backend must still let core apps migrate."""
    loader = MigrationLoader(None, ignore_no_migrations=True)
    for (app_label, _name), migration in loader.disk_migrations.items():
        if app_label in {"tasks_demo", "django_tasks_database"}:
            continue
        assert all(dep[0] != "django_tasks_database" for dep in migration.dependencies), app_label
    assert "desktop_django_starter" not in loader.migrated_apps
