"""Background-work status for desktop shells."""

from __future__ import annotations

from django.apps import apps


def background_task_counts() -> dict[str, int]:
    """Count running and queued django-tasks-db tasks.

    Shells use this to ask before quitting while work is still in flight.
    Apps without the django-tasks-db backend report no tasks.
    """
    if not apps.is_installed("django_tasks_db"):
        return {"running_tasks": 0, "queued_tasks": 0}

    from django.tasks import TaskResultStatus
    from django_tasks_db.models import DBTaskResult

    return {
        "running_tasks": DBTaskResult.objects.filter(status=TaskResultStatus.RUNNING).count(),
        "queued_tasks": DBTaskResult.objects.filter(status=TaskResultStatus.READY).count(),
    }
