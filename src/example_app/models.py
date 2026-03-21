from django.db import models


class Item(models.Model):
    class Status(models.TextChoices):
        BACKLOG = "backlog", "Backlog"
        ACTIVE = "active", "Active"
        DONE = "done", "Done"

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
