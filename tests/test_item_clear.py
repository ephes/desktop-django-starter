"""Release All confirms one displayed whole-inventory snapshot."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.urls import reverse

from example_app.models import Item


@pytest.mark.django_db
@pytest.mark.parametrize("change", ["add", "edit", "delete"])
def test_clear_rejects_changed_inventory_including_other_pages(client, change):
    Item.objects.bulk_create([Item(title=f"Synthetic {i}") for i in range(21)])
    old = client.get(reverse("example_app:item-list")).context.get("inventory_revision", "")
    # This oldest row is outside the displayed first page.
    item = Item.objects.order_by("pk").first()
    if change == "add":
        Item.objects.create(title="New arrival")
    elif change == "edit":
        Item.objects.filter(pk=item.pk).update(notes="New personality")
    else:
        item.delete()
    before = list(Item.objects.order_by("pk").values())
    response = client.post(reverse("example_app:item-clear"), {"revision": old})
    assert response.status_code == 409
    assert list(Item.objects.order_by("pk").values()) == before
    assert client.post(reverse("example_app:item-clear"), {"revision": old}).status_code == 409
    current = client.get(reverse("example_app:item-list")).context["inventory_revision"]
    assert client.post(reverse("example_app:item-clear"), {"revision": current}).status_code == 200
    assert not Item.objects.exists()
    assert client.post(reverse("example_app:item-clear"), {"revision": current}).status_code == 409


@pytest.mark.django_db
@pytest.mark.parametrize("revision", ["", "forged", "item-token"])
def test_clear_requires_signed_inventory_not_item_revision(client, revision):
    item = Item.objects.create(title="Synthetic")
    if revision == "item-token":
        revision = client.get(reverse("example_app:item-delete", args=[item.pk])).context[
            "item_revision"
        ]
    assert client.post(reverse("example_app:item-clear"), {"revision": revision}).status_code == 409
    assert Item.objects.filter(pk=item.pk).exists()


SCRIPT = """
import json, os, sys, time
from pathlib import Path
import django
from django.conf import settings

directory, mode, role = sys.argv[1:]
directory = Path(directory)
os.environ['DJANGO_SETTINGS_MODULE'] = 'desktop_django_starter.settings.' + mode
os.environ['DESKTOP_DJANGO_APP_DATA_DIR'] = str(directory / 'app-data')
settings.DATABASES['default']['NAME'] = directory / 'clear.sqlite3'
django.setup()
from django.core.management import call_command
from django.db import connection, connections
from django.test import RequestFactory
from example_app.models import Item
from example_app.views import ItemListView, item_clear
factory = RequestFactory()

def displayed():
    return ItemListView.as_view()(factory.get('/')).context_data.get('inventory_revision', '')

def clear(revision):
    return item_clear(factory.post('/items/clear/', {'revision': revision})).status_code

if role == 'setup':
    call_command('migrate', verbosity=0)
    Item.objects.create(title='Synthetic')
    (directory / 'revision').write_text(displayed())
elif role == 'fence':
    from django.db import OperationalError
    from example_app import views
    peer = connection.copy(alias='peer')
    connections['peer'] = peer
    with peer.cursor() as cursor:
        cursor.execute('PRAGMA busy_timeout=0')
    checked = False
    original = views.matches_inventory_revision
    def check(revision):
        global checked
        valid = original(revision)
        try:
            Item.objects.using('peer').create(title='Intervening arrival')
        except OperationalError as error:
            assert 'locked' in str(error)
            checked = True
        else:
            raise AssertionError('Another writer committed between verification and clear')
        return valid
    views.matches_inventory_revision = check
    try:
        assert clear(displayed()) == 200
        assert checked
        Item.objects.using('peer').create(title='Later arrival')
        assert Item.objects.get().title == 'Later arrival'
    finally:
        peer.close()
    print(0)
elif role in ('add', 'edit'):
    old = displayed()
    # Another window commits through a separate SQLite connection.
    peer = connection.copy(alias='peer')
    connections['peer'] = peer
    try:
        if role == 'add':
            Item.objects.using('peer').create(title='New arrival')
        else:
            Item.objects.using('peer').update(notes='New personality')
    finally:
        peer.close()
    before = list(Item.objects.order_by('pk').values())
    assert clear(old) == 409
    assert list(Item.objects.order_by('pk').values()) == before
    assert clear(displayed()) == 200
    print(Item.objects.count())
else:
    revision = (directory / 'revision').read_text()
    (directory / role).touch()
    deadline = time.monotonic() + 10
    while not all((directory / name).exists() for name in ('one', 'two')):
        if time.monotonic() > deadline:
            raise RuntimeError('Clear rendezvous timed out')
        time.sleep(0.01)
    print(clear(revision))
"""


@pytest.mark.parametrize("mode", ["local", "packaged"])
@pytest.mark.parametrize("scenario", ["add", "edit", "fence", "race"])
def test_clear_across_sqlite_connections(tmp_path, mode, scenario):
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}

    def command(role):
        return [sys.executable, "-c", SCRIPT, str(tmp_path), mode, role]

    subprocess.run(command("setup"), env=env, check=True, capture_output=True, timeout=30)
    if scenario != "race":
        result = subprocess.run(
            command(scenario), env=env, check=True, capture_output=True, timeout=20
        )
        assert int(result.stdout) == 0
        return
    children = [
        subprocess.Popen(command(role), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for role in ("one", "two")
    ]
    try:
        outputs = [child.communicate(timeout=20) for child in children]
        assert [child.returncode for child in children] == [0, 0], outputs
        assert sorted(int(out) for out, err in outputs) == [200, 409], outputs
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait()
