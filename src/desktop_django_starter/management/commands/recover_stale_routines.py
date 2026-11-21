import logging

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import OperationalError, ProgrammingError
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Recover abandoned demo routines after an owned desktop profile restart."

    def handle(self, *args: object, **options: object) -> None:
        if not apps.is_installed("tasks_demo"):
            return

        from tasks_demo.models import SimulatedTask

        try:
            SimulatedTask.objects.filter(
                status__in=[SimulatedTask.Status.PENDING, SimulatedTask.Status.RUNNING]
            ).update(
                status=SimulatedTask.Status.FAILED,
                result="Abandoned - app restarted",
                completed_at=timezone.now(),
            )
        except (OperationalError, ProgrammingError):
            logger.warning("Routine startup recovery failed. Abandoned routines may remain active.")
