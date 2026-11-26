"""Exercise the migrated SQLite indexes with the production ORM's bound SQL."""

from contextlib import contextmanager
from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from tasks_demo.models import SimulatedTask
from tasks_demo.tasks import TERMINAL_HISTORY_LIMIT, visible_tasks


@contextmanager
def capture_selects():
    statements = []

    def capture(execute, sql, params, many, context):
        if sql.startswith("SELECT"):
            statements.append((sql, params))
        return execute(sql, params, many, context)

    with connection.execute_wrapper(capture):
        yield statements


def plan_and_work(statement):
    sql, params = statement
    with connection.cursor() as cursor:
        cursor.execute("EXPLAIN QUERY PLAN " + sql, params)
        plan = "\n".join(row[-1] for row in cursor.fetchall())
        ticks = 0

        def tick():
            nonlocal ticks
            ticks += 1
            return 0

        connection.connection.set_progress_handler(tick, 100)
        try:
            cursor.execute(sql, params)
            cursor.fetchall()
        finally:
            connection.connection.set_progress_handler(None, 0)
    return plan, ticks * 100


@pytest.mark.django_db
def test_routine_poll_uses_bounded_index_work_with_large_history():
    completed = timezone.now()
    history = SimulatedTask.objects.bulk_create(
        [
            SimulatedTask(
                label=f"Synthetic history {i}",
                status="DONE" if i % 2 else "FAILED",
                completed_at=completed if i % 3 else None,
            )
            for i in range(10_000)
        ]
    )
    # Equal completion and creation times exercise the final ID tie breaker.
    created = completed - timedelta(days=1)
    SimulatedTask.objects.update(created_at=created)
    active = SimulatedTask.objects.bulk_create(
        [
            SimulatedTask(label=f"Synthetic active {i}", status=status)
            for i, status in enumerate(["PENDING", "RUNNING", "PENDING", "RUNNING"])
        ]
    )
    with capture_selects() as statements:
        rows = visible_tasks()
    assert len(statements) == 3
    expected_history = sorted([row.pk for i, row in enumerate(history) if i % 3], reverse=True)[
        :TERMINAL_HISTORY_LIMIT
    ]
    assert {row.pk for row in rows} == {row.pk for row in active} | set(expected_history)
    assert [row.pk for row in rows if row.pk in expected_history] == expected_history
    for statement, lookup in zip(
        statements,
        ["routine_active_created_idx", "SEARCH", "routine_history_order_idx"],
        strict=True,
    ):
        plan, work = plan_and_work(statement)
        assert lookup in plan, plan
        assert "TEMP B-TREE" not in plan, plan
        assert work < 5_000, (plan, work)
    assert set(statements[1][1]) == {row.pk for row in active}


@pytest.mark.django_db
def test_activity_aggregate_searches_active_statuses_before_counting():
    from django.tasks import TaskResultStatus
    from django_tasks_db.models import DBTaskResult

    from desktop_django_starter.activity import background_task_counts

    for expected in [
        {"running_tasks": 0, "queued_tasks": 0},
        {"running_tasks": 2, "queued_tasks": 3},
    ]:
        if expected["running_tasks"]:
            DBTaskResult.objects.bulk_create(
                [
                    backend_row(status)
                    for status in [TaskResultStatus.RUNNING] * 2 + [TaskResultStatus.READY] * 3
                ]
            )
        with capture_selects() as statements:
            assert background_task_counts() == expected
        assert len(statements) == 1
        _, small_work = plan_and_work(statements[0])
        DBTaskResult.objects.bulk_create(
            [
                backend_row(TaskResultStatus.SUCCESSFUL if i % 2 else TaskResultStatus.FAILED)
                for i in range(10_000)
            ]
        )
        DBTaskResult.objects.bulk_create(
            [backend_row(TaskResultStatus.READY, queue_name="unserved") for _ in range(10_000)]
        )
        with capture_selects() as statements:
            assert background_task_counts() == expected
        assert len(statements) == 1
        sql, params = statements[0]
        assert '"status" IN' in sql
        assert params[2:] == (
            "default",
            TaskResultStatus.READY,
            TaskResultStatus.RUNNING,
            "default",
        )
        plan, large_work = plan_and_work(statements[0])
        assert "SEARCH" in plan and "dds_backend_activity_idx" in plan, plan
        assert "TEMP B-TREE" not in plan, plan
        assert large_work <= small_work + 500, (small_work, large_work)
        DBTaskResult.objects.all().delete()


def backend_row(status, *, queue_name="default"):
    from django_tasks_db.models import DBTaskResult

    return DBTaskResult(
        status=status,
        args_kwargs={"args": [], "kwargs": {}},
        task_path="tasks_demo.tasks.run_simulated_task",
        backend_name="default",
        queue_name=queue_name,
        run_after=timezone.now(),
    )
