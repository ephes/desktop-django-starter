from django.db import models


class Item(models.Model):
    class Status(models.TextChoices):
        BACKLOG = "backlog", "Grazing"
        ACTIVE = "active", "Galloping"
        DONE = "done", "Show Ready"

    title = models.CharField(max_length=200)
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.BACKLOG,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-created_at"]

    def __str__(self) -> str:
        return self.title


class DemoContentState(models.Model):
    class Key(models.TextChoices):
        FIRST_RUN_PONY_SEED = "first_run_pony_seed", "First-run pony seed"

    key = models.CharField(max_length=64, unique=True, choices=Key.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.get_key_display()
