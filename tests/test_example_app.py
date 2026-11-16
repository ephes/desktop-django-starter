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


def test_item_list_pages_equal_timestamps_without_omissions(client, django_assert_num_queries):
    from django.utils import timezone

    Item.objects.bulk_create([Item(title=f"Pony {i}") for i in range(103)])
    Item.objects.update(created_at=timezone.now(), updated_at=timezone.now())
    seen = []
    for page in range(1, 6):
        # Snapshot savepoint + count/page/inventory queries + release.
        with django_assert_num_queries(5):
            response = client.get(reverse("example_app:item-list"), {"page": page})
        assert response.status_code == 200
        items = list(response.context["items"])
        assert len(items) == (20 if page < 6 else 3)
        seen.extend(item.pk for item in items)
        html = response.content.decode()
        assert f"Page {page} of 6" in html
        assert f"?page={page + 1}" in html
        assert f"?page={page}" in html  # CRUD links retain the displayed page.
    response = client.get(reverse("example_app:item-list"), {"page": 6})
    seen.extend(item.pk for item in response.context["items"])
    assert seen == list(Item.objects.order_by("-pk").values_list("pk", flat=True))
    assert 'rel="next"' not in response.content.decode()


def test_item_create_returns_to_displayed_page(client):
    Item.objects.bulk_create([Item(title=f"Pony {i}") for i in range(21)])
    response = client.post(
        reverse("example_app:item-create") + "?page=2",
        {"title": "New pony", "notes": "Synthetic", "status": Item.Status.ACTIVE},
    )
    assert response.url == reverse("example_app:item-list") + "?page=2"


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
    assert DemoContentState.objects.count() == 1


def test_seed_demo_content_does_not_reseed_after_clearing_stable(client) -> None:
    call_command("seed_demo_content")

    revision = client.get(reverse("example_app:item-list")).context["inventory_revision"]
    clear_response = client.post(reverse("example_app:item-clear"), {"revision": revision})

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
            "revision": client.get(reverse("example_app:item-update", args=[item.pk])).context[
                "item_revision"
            ],
            "title": "Updated item",
            "notes": "Edited in place.",
            "status": Item.Status.DONE,
        },
    )
    assert update_response.status_code == 302

    item.refresh_from_db()
    assert item.title == "Updated item"
    assert item.status == Item.Status.DONE

    delete_url = reverse("example_app:item-delete", args=[item.pk])
    delete_response = client.post(
        delete_url, {"revision": client.get(delete_url).context["item_revision"]}
    )
    assert delete_response.status_code == 302
    assert Item.objects.count() == 0
