import pytest
from django.urls import reverse

from example_app.models import Item

pytestmark = pytest.mark.django_db


def test_item_list_empty_state(client) -> None:
    response = client.get(reverse("example_app:item-list"))

    assert response.status_code == 200
    assert "No ponies in the stable yet." in response.content.decode()


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
