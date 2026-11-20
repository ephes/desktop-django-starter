import logging
import sqlite3
import warnings

from django.apps import AppConfig
from django.db import OperationalError, ProgrammingError

logger = logging.getLogger(__name__)


class TasksDemoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tasks_demo"

    def ready(self):
        self.reconcile_stale_tasks()

    @staticmethod
    def reconcile_stale_tasks():
        """Mark any non-terminal tasks as failed.

        Called on startup to clean up tasks that were interrupted by an
        app restart. A missing routine table is expected before migrations.
        Other database failures are logged without driver details.
        """
        from django.utils import timezone

        from .models import SimulatedTask

        try:
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
        except (OperationalError, ProgrammingError) as exc:
            cause = exc.__cause__
            if (
                isinstance(exc, OperationalError)
                and isinstance(cause, sqlite3.OperationalError)
                and cause.args == (f"no such table: {SimulatedTask._meta.db_table}",)
            ):
                return
            logger.warning("Routine startup recovery failed. Abandoned routines may remain active.")
