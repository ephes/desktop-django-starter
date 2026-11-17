"""Own the shell activity index without changing django-tasks-db's model state.

The index lives in ``tasks_demo`` because this optional extension is the app
that requires the ``django_tasks_db`` backend. The core
``desktop_django_starter`` app keeps no migration dependency on the backend, so
removing the extension and backend from ``INSTALLED_APPS`` still migrates.
"""

from django.db import migrations, models


def add_status_index(apps, schema_editor):
    schema_editor.add_index(
        apps.get_model("django_tasks_database", "DBTaskResult"),
        models.Index(fields=["status"], name="dds_backend_status_idx"),
    )


def remove_status_index(apps, schema_editor):
    schema_editor.remove_index(
        apps.get_model("django_tasks_database", "DBTaskResult"),
        models.Index(fields=["status"], name="dds_backend_status_idx"),
    )


class Migration(migrations.Migration):
    # django-tasks-db==0.13.0 (uv.lock): the READY-only worker index cannot
    # serve the shell's READY/RUNNING aggregate. Keep this dependency pinned
    # and recheck the external schema when upgrading the backend.
    dependencies = [
        ("tasks_demo", "0003_routine_poll_indexes"),
        ("django_tasks_database", "0021_conditional_partial_index_ordering"),
    ]

    operations = [migrations.RunPython(add_status_index, remove_status_index)]
