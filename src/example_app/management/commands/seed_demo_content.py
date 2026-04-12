from django.core.management.base import BaseCommand

from example_app.demo_content import seed_first_run_demo_content


class Command(BaseCommand):
    help = "Seed the first-run Flying Stable demo ponies when the database is eligible."

    def handle(self, *args, **options) -> None:
        created = seed_first_run_demo_content()
        if created:
            self.stdout.write(self.style.SUCCESS(f"Seeded {created} first-run demo ponies."))
            return

        self.stdout.write("Demo pony seed skipped; existing data or prior seed state found.")
