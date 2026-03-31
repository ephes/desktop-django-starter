import warnings

from django.apps import AppConfig
from django.db import OperationalError, ProgrammingError


class TasksDemoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tasks_demo"

    def ready(self):
        self.reconcile_stale_tasks()

    @staticmethod
    def reconcile_stale_tasks():
        """Mark any non-terminal tasks as failed.

        Called on startup to clean up tasks that were interrupted by an
        app restart.  Fails silently when the database table does not
        exist yet (before migrations) and is safe to call multiple times.
        """
        try:
            from django.utils import timezone

            from .models import SimulatedTask

            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="Accessing the database during app initialization",
                    category=RuntimeWarning,
                )
                SimulatedTask.objects.filter(
                    status__in=[
                        SimulatedTask.Status.PENDING,
                        SimulatedTask.Status.RUNNING,
                    ]
                ).update(
                    status=SimulatedTask.Status.FAILED,
                    result="Abandoned - app restarted",
                    completed_at=timezone.now(),
                )
        except (OperationalError, ProgrammingError):
            # Table does not exist yet - migrations haven't run.
            pass
