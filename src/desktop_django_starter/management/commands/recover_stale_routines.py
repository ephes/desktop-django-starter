from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError
from django.utils import timezone


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
        except DatabaseError as error:
            raise CommandError(
                "Routine startup recovery failed: the routine database could not be updated."
            ) from error
