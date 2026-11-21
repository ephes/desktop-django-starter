"""Background-work status for desktop shells."""

from __future__ import annotations

from django.apps import apps
from django.conf import settings
from django.db import router
from django.db.models import Count, Q


def background_task_counts() -> dict[str, int]:
    """Count running and queued tasks for the shell's database worker.

    Shells use this to ask before quitting while work is still in flight.
    Apps without the django-tasks-db backend report no tasks.
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
    return active.aggregate(
        running_tasks=Count("pk", filter=Q(status=TaskResultStatus.RUNNING)),
        queued_tasks=Count("pk", filter=Q(status=TaskResultStatus.READY)),
    )
