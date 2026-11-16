"""Synthetic SQLite admission, including two independent web processes."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.urls import reverse
from django_tasks_db.models import DBTaskResult

from tasks_demo.models import SimulatedTask
from tasks_demo.tasks import run_simulated_task


@pytest.mark.django_db
def test_active_limit_refuses_without_queue_orphans_and_allows_retry(client):
    for index in range(16):
        row = SimulatedTask.objects.create(
            label=f"Synthetic {index}", status="RUNNING" if index % 2 else "PENDING"
        )
        result = run_simulated_task.enqueue(row.pk)
        row.backend_task_id = result.id
        row.save(update_fields=["backend_task_id"])
    SimulatedTask.objects.create(label="History", status="DONE")
    response = client.post(reverse("tasks_demo:task-run"))
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
    assert "16" in response.json()["error"]
    assert SimulatedTask.objects.count() == 17
    assert DBTaskResult.objects.count() == 16
    assert len(client.get(reverse("tasks_demo:task-status")).json()["tasks"]) == 17
    SimulatedTask.objects.filter(pk=row.pk).update(status="DONE")
    assert client.post(reverse("tasks_demo:task-run")).status_code == 201
    assert DBTaskResult.objects.count() == 17


SCRIPT = """
import json, os, sys, time
from pathlib import Path
import django
from django.conf import settings

directory, mode, role = sys.argv[1:]
directory = Path(directory)
os.environ['DJANGO_SETTINGS_MODULE'] = 'desktop_django_starter.settings.' + mode
os.environ['DESKTOP_DJANGO_APP_DATA_DIR'] = str(directory / 'app-data')
settings.DATABASES['default']['NAME'] = directory / 'admission.sqlite3'
# Model two request processes in one running session, not app restarts.
from unittest.mock import patch
with patch('tasks_demo.apps.TasksDemoConfig.reconcile_stale_tasks'):
    django.setup()
from django.core.management import call_command
from django.test import RequestFactory
from django_tasks_db.models import DBTaskResult
from tasks_demo.models import SimulatedTask
from tasks_demo.tasks import run_simulated_task
from tasks_demo.views import task_create

if role == 'setup':
    call_command('migrate', verbosity=0)
    for i in range(15):
        row = SimulatedTask.objects.create(label='Synthetic')
        result = run_simulated_task.enqueue(row.pk)
        row.backend_task_id = result.id
        row.save(update_fields=['backend_task_id'])
elif role == 'inspect':
    print(json.dumps([SimulatedTask.objects.count(), DBTaskResult.objects.count()]))
else:
    (directory / role).touch()
    deadline = time.monotonic() + 10
    while not all((directory / name).exists() for name in ('one', 'two')):
        if time.monotonic() > deadline:
            raise RuntimeError('Admission rendezvous timed out')
        time.sleep(0.01)
    print(task_create(RequestFactory().post('/tasks/run/')).status_code)
"""


@pytest.mark.parametrize("mode", ["local", "packaged"])
def test_final_slot_is_shared_between_web_processes(tmp_path, mode):
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}

    def command(role):
        return [sys.executable, "-c", SCRIPT, str(tmp_path), mode, role]

    subprocess.run(command("setup"), env=env, check=True, capture_output=True, timeout=30)
    children = [
        subprocess.Popen(command(role), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for role in ("one", "two")
    ]
    try:
        outputs = [child.communicate(timeout=20) for child in children]
        assert [child.returncode for child in children] == [0, 0], outputs
        assert sorted(int(out) for out, err in outputs) == [201, 503], outputs
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait()
    inspection = subprocess.run(
        command("inspect"), env=env, check=True, capture_output=True, timeout=10
    )
    assert json.loads(inspection.stdout) == [16, 16]
