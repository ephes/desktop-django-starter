"""Release All confirms one displayed whole-inventory snapshot."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.core import signing
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from example_app.models import Item


@pytest.mark.django_db
def test_list_hydrates_only_one_page_as_inventory_grows(client, monkeypatch):
    hydrated = []
    original = Item.from_db

    def from_db(cls, db, fields, values, **kwargs):
        item = original(db, fields, values, **kwargs)
        hydrated.append(item.pk)
        return item

    monkeypatch.setattr(Item, "from_db", classmethod(from_db))
    url = reverse("example_app:item-list")

    for total in (21, 121):
        Item.objects.bulk_create(
            [
                Item(title="Synthetic", notes="Personality " * 100)
                for _ in range(total - Item.objects.count())
            ]
        )
        hydrated.clear()
        with CaptureQueriesContext(connection) as queries:
            response = client.get(url)
        assert response.status_code == 200
        assert response.context["paginator"].count == total
        assert response.context["inventory_revision"]
        assert len(hydrated) == 20
        content_queries = [
            query["sql"] for query in queries if '"example_app_item"."notes"' in query["sql"]
        ]
        assert len(content_queries) == 1
        assert "LIMIT 20" in content_queries[0]


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
    with CaptureQueriesContext(connection) as queries:
        assert (
            client.post(reverse("example_app:item-clear"), {"revision": current}).status_code == 200
        )
    assert all('"example_app_item"."notes"' not in query["sql"] for query in queries)
    assert not Item.objects.exists()
    assert client.post(reverse("example_app:item-clear"), {"revision": current}).status_code == 409


@pytest.mark.django_db
def test_inventory_generation_rolls_back_with_raw_item_write(client):
    item = Item.objects.create(title="Synthetic")
    list_url = reverse("example_app:item-list")
    clear_url = reverse("example_app:item-clear")
    revision = client.get(list_url).context["inventory_revision"]

    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("UPDATE example_app_item SET notes = %s WHERE id = %s", ["Changed", item.pk])
        assert client.post(clear_url, {"revision": revision}).status_code == 409
        transaction.set_rollback(True)

    item.refresh_from_db()
    assert item.notes == ""
    assert client.post(clear_url, {"revision": revision}).status_code == 200


@pytest.mark.django_db(transaction=True)
def test_inventory_migration_preserves_items_and_requires_fresh_confirmation(client):
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    previous = [("example_app", "0003_alter_item_status")]
    try:
        executor.migrate(previous)
        item = Item.objects.create(title="Synthetic", notes="Retained personality")
        legacy_revision = signing.dumps("a" * 64, salt="example_app.inventory-revision")
    finally:
        MigrationExecutor(connection).migrate(latest)

    clear_url = reverse("example_app:item-clear")
    assert client.post(clear_url, {"revision": legacy_revision}).status_code == 409
    assert Item.objects.get(pk=item.pk).notes == "Retained personality"
    revision = client.get(reverse("example_app:item-list")).context["inventory_revision"]
    assert client.post(clear_url, {"revision": revision}).status_code == 200


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
from django.db import connection, connections, transaction
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
elif role == 'reader':
    # Another window holds SQLite's writer lock with an uncommitted insert.
    peer = connection.copy(alias='peer')
    connections['peer'] = peer
    with connection.cursor() as cursor:
        cursor.execute('PRAGMA busy_timeout=0')
    try:
        with transaction.atomic(using='peer'):
            Item.objects.using('peer').create(title='Uncommitted arrival')
            response = ItemListView.as_view()(factory.get('/'))
            assert response.context_data['paginator'].count == 1
            assert response.context_data['inventory_revision']
        old = response.context_data['inventory_revision']
        assert clear(old) == 409
        assert Item.objects.count() == 2
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
@pytest.mark.parametrize("scenario", ["add", "edit", "fence", "race", "reader"])
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
