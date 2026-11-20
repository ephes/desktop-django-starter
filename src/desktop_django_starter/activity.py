"""Background-work status for desktop shells."""

from __future__ import annotations

from django.apps import apps
from django.db import router
from django.db.models import Count, Q


def background_task_counts() -> dict[str, int]:
    """Count running and queued django-tasks-db tasks.

    Shells use this to ask before quitting while work is still in flight.
    Apps without the django-tasks-db backend report no tasks.
    """
    if not apps.is_installed("django_tasks_db"):
        return {"running_tasks": 0, "queued_tasks": 0}

    from django.tasks import TaskResultStatus
    from django_tasks_db.models import DBTaskResult

    # django-tasks-db enqueues through the ORM's write router.
    writer = router.db_for_write(DBTaskResult)
    return (
        DBTaskResult.objects.using(writer)
        .filter(status__in=[TaskResultStatus.READY, TaskResultStatus.RUNNING])
        .aggregate(
            running_tasks=Count("pk", filter=Q(status=TaskResultStatus.RUNNING)),
            queued_tasks=Count("pk", filter=Q(status=TaskResultStatus.READY)),
        )
    )
