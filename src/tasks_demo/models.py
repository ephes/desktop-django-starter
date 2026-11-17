from django.db import models


class SimulatedTask(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RUNNING = "RUNNING", "Running"
        DONE = "DONE", "Done"
        FAILED = "FAILED", "Failed"

    label = models.CharField(max_length=200)
    backend_task_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    result = models.TextField(blank=True, null=True)
    duration = models.FloatField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["-created_at"],
                condition=models.Q(status="PENDING") | models.Q(status="RUNNING"),
                name="routine_active_created_idx",
            ),
            models.Index(
                fields=["-completed_at", "-created_at", "-id"],
                condition=models.Q(status="DONE") | models.Q(status="FAILED"),
                name="routine_history_order_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.label} ({self.status})"
