import pytest
from django.core.management import call_command
from django.urls import reverse

from example_app.demo_content import FIRST_RUN_PONIES
from example_app.models import DemoContentState, Item

pytestmark = pytest.mark.django_db


def test_item_list_empty_state(client) -> None:
    response = client.get(reverse("example_app:item-list"))

    assert response.status_code == 200
    assert "The stable is empty right now." in response.content.decode()


def test_seed_demo_content_seeds_brand_new_database() -> None:
    call_command("seed_demo_content")

    items = list(Item.objects.order_by("created_at"))

    assert [item.title for item in items] == [pony.title for pony in FIRST_RUN_PONIES]
    assert Item.objects.count() == len(FIRST_RUN_PONIES)
    assert DemoContentState.objects.filter(key=DemoContentState.Key.FIRST_RUN_PONY_SEED).exists()


def test_seed_demo_content_noops_when_pony_rows_exist() -> None:
    Item.objects.create(
        title="Existing Pony",
        notes="Already in the stable.",
        status=Item.Status.ACTIVE,
    )

    call_command("seed_demo_content")

    assert Item.objects.count() == 1
    assert Item.objects.get().title == "Existing Pony"
    assert DemoContentState.objects.count() == 0


def test_seed_demo_content_does_not_reseed_after_clearing_stable(client) -> None:
    call_command("seed_demo_content")

    clear_response = client.post(reverse("example_app:item-clear"))

    assert clear_response.status_code == 200
    assert clear_response.json() == {"cleared": True}
    assert Item.objects.count() == 0

    call_command("seed_demo_content")

    assert Item.objects.count() == 0
    assert DemoContentState.objects.filter(key=DemoContentState.Key.FIRST_RUN_PONY_SEED).exists()


def test_item_crud_flow(client) -> None:
    create_response = client.post(
        reverse("example_app:item-create"),
        {
            "title": "Local-first item",
            "notes": "Created through the test client.",
            "status": Item.Status.ACTIVE,
        },
    )

    assert create_response.status_code == 302

    item = Item.objects.get()

    list_response = client.get(reverse("example_app:item-list"))
    assert "Local-first item" in list_response.content.decode()

    update_response = client.post(
        reverse("example_app:item-update", args=[item.pk]),
        {
            "title": "Updated item",
            "notes": "Edited in place.",
            "status": Item.Status.DONE,
        },
    )
    assert update_response.status_code == 302

    item.refresh_from_db()
    assert item.title == "Updated item"
    assert item.status == Item.Status.DONE

    delete_response = client.post(reverse("example_app:item-delete", args=[item.pk]))
    assert delete_response.status_code == 302
    assert Item.objects.count() == 0
