"""Keep the shell activity query bounded to active work on its served queues."""

from django.db import migrations, models

STATUS_INDEX = models.Index(fields=["status"], name="dds_backend_status_idx")
ACTIVITY_INDEX = models.Index(
    fields=["status", "backend_name", "queue_name"], name="dds_backend_activity_idx"
)


def add_activity_index(apps, schema_editor):
    results = apps.get_model("django_tasks_database", "DBTaskResult")
    schema_editor.add_index(results, ACTIVITY_INDEX)
    schema_editor.remove_index(results, STATUS_INDEX)


def restore_status_index(apps, schema_editor):
    results = apps.get_model("django_tasks_database", "DBTaskResult")
    schema_editor.add_index(results, STATUS_INDEX)
    schema_editor.remove_index(results, ACTIVITY_INDEX)


class Migration(migrations.Migration):
    dependencies = [("tasks_demo", "0004_backend_activity_index")]

    operations = [migrations.RunPython(add_activity_index, restore_status_index)]
