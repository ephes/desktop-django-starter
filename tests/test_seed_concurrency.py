import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.db import transaction

from example_app.demo_content import seed_first_run_demo_content
from example_app.models import DemoContentState, Item

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = """
import json, os, sys, time
from pathlib import Path
import django
from django.conf import settings

directory, mode, role, existing = sys.argv[1:]
directory = Path(directory)
os.environ['DJANGO_SETTINGS_MODULE'] = 'desktop_django_starter.settings.' + mode
os.environ['DESKTOP_DJANGO_APP_DATA_DIR'] = str(directory / 'app-data')
settings.DATABASES['default']['NAME'] = directory / 'seed.sqlite3'
django.setup()
from django.core.management import call_command
from django.db import connection
from example_app.models import Item, DemoContentState
from example_app.demo_content import seed_first_run_demo_content

if role == 'setup':
    call_command('migrate', verbosity=0)
    if existing == 'yes':
        Item.objects.create(title='User pony', notes='Keep me')
elif role == 'inspect':
    print(json.dumps([list(Item.objects.values_list('title', flat=True)),
                      DemoContentState.objects.count()]))
else:
    def rendezvous():
        (directory / role).touch()
        deadline = time.monotonic() + 10
        while not all((directory / name).exists() for name in ('one', 'two')):
            if time.monotonic() > deadline:
                raise RuntimeError('Seed rendezvous timed out')
            time.sleep(0.01)

    waited = False
    def before_write(execute, sql, params, many, context):
        global waited
        if sql.startswith('INSERT') and not waited:
            waited = True
            rendezvous()
        return execute(sql, params, many, context)

    if mode == 'packaged':
        # IMMEDIATE owns the write lock before the first INSERT.
        rendezvous()
        print(seed_first_run_demo_content())
    else:
        # Both deferred callers reach their first write together. The old
        # helper already held read snapshots here, making lock upgrade fail.
        with connection.execute_wrapper(before_write):
            print(seed_first_run_demo_content())
"""


@pytest.mark.parametrize("mode", ["local", "packaged"])
@pytest.mark.parametrize("existing", [False, True])
def test_concurrent_seed_processes(tmp_path, mode, existing):
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}

    def command(role):
        return [
            sys.executable,
            "-c",
            SCRIPT,
            str(tmp_path),
            mode,
            role,
            "yes" if existing else "no",
        ]

    subprocess.run(command("setup"), env=env, check=True, capture_output=True, timeout=30)
    children = [
        subprocess.Popen(command(role), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for role in ("one", "two")
    ]
    try:
        results = [child.communicate(timeout=20) for child in children]
        assert [child.returncode for child in children] == [0, 0], results
        assert sorted(int(out) for out, err in results) == ([0, 0] if existing else [0, 3])
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait()
    inspection = subprocess.run(
        command("inspect"), env=env, check=True, capture_output=True, timeout=10
    )
    titles, markers = json.loads(inspection.stdout)
    assert len(titles) == (1 if existing else 3)
    assert markers == (0 if existing else 1)
    if existing:
        assert titles == ["User pony"]


@pytest.mark.django_db
def test_failed_seed_rolls_back_marker_and_all_ponies(monkeypatch):
    create = Item.objects.create
    calls = 0

    def fail_second(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("Synthetic seed failure")
        return create(**kwargs)

    monkeypatch.setattr(Item.objects, "create", fail_second)
    with pytest.raises(RuntimeError, match="Synthetic seed failure"):
        seed_first_run_demo_content()
    assert not Item.objects.exists()
    assert not DemoContentState.objects.exists()
    # The caller's transaction remains usable after the seed's savepoint rolls back.
    with transaction.atomic():
        Item.objects.create(title="Caller pony")
