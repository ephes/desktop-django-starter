"""Background-work status for desktop shells."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import ExitStack, closing, contextmanager, nullcontext
from time import monotonic

from django.apps import apps
from django.conf import settings
from django.db import connections, router
from django.db.models import Count, Q


@contextmanager
def _sqlite_activity_probe(alias: str, timeout: float) -> Iterator[None]:
    original = connections[alias]
    probe = original.copy()
    options = probe.settings_dict["OPTIONS"]
    factory = options.get("factory", sqlite3.Connection)
    deadline = monotonic() + timeout
    with ExitStack() as resources:

        def open_probe(*args, **kwargs):
            # Own the raw handle even if Django's connection setup raises.
            raw = resources.enter_context(closing(factory(*args, **kwargs)))
            raw.set_progress_handler(lambda: monotonic() >= deadline, 1000)
            return raw

        # The read needs no startup pragmas such as journal_mode=WAL, which
        # can themselves take locks. Set the busy timeout before opening.
        options.update(timeout=timeout, init_command="", factory=open_probe)
        connections[alias] = probe
        try:
            yield
        finally:
            connections[alias] = original


def background_task_counts(*, sqlite_timeout: float | None = None) -> dict[str, int]:
    """Count running and queued tasks for the shell's database worker.

    Shells use this to ask before quitting while work is still in flight.
    Apps without the django-tasks-db backend report no tasks. The optional
    timeout is for the Positron quit probe on a disposable SQLite connection.
    """
    if not apps.is_installed("django_tasks_db"):
        return {"running_tasks": 0, "queued_tasks": 0}

    from django.tasks import DEFAULT_TASK_BACKEND_ALIAS, TaskResultStatus
    from django_tasks_db.models import DBTaskResult

    # django-tasks-db enqueues through the ORM's write router.
    writer = router.db_for_write(DBTaskResult)
    active = DBTaskResult.objects.using(writer).filter(
        backend_name=DEFAULT_TASK_BACKEND_ALIAS,
        status__in=[TaskResultStatus.READY, TaskResultStatus.RUNNING],
    )
    queues = settings.DESKTOP_DJANGO_WORKER_QUEUES.split(",")
    if "*" not in queues:
        active = active.filter(queue_name__in=queues)
    alias = active.db
    probe = (
        _sqlite_activity_probe(alias, sqlite_timeout)
        if sqlite_timeout is not None and connections[alias].vendor == "sqlite"
        else nullcontext()
    )
    with probe:
        return active.aggregate(
            running_tasks=Count("pk", filter=Q(status=TaskResultStatus.RUNNING)),
            queued_tasks=Count("pk", filter=Q(status=TaskResultStatus.READY)),
        )
