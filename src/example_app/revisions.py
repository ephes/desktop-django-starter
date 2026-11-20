"""Signed snapshots of the item content shown in a mutation form."""

import hashlib
import json

from django.core import signing
from django.db.models import F
from django.utils.crypto import constant_time_compare

from .models import Item, ItemInventory

SALT = "example_app.item-content-revision"
CONFLICT_MESSAGE = "This pony changed since you opened it. Reload the current pony before retrying."


def _content_revision(item: Item) -> str:
    content = [item.pk, item.title, item.notes, item.status, item.updated_at.isoformat()]
    return hashlib.sha256(json.dumps(content, ensure_ascii=True).encode()).hexdigest()


def displayed_revision(item: Item) -> str:
    return signing.dumps(_content_revision(item), salt=SALT)


def matches_displayed_revision(item: Item, token: str) -> bool:
    try:
        revision = signing.loads(token, salt=SALT)
    except signing.BadSignature:
        return False
    return isinstance(revision, str) and constant_time_compare(revision, _content_revision(item))


INVENTORY_SALT = "example_app.inventory-generation"


def lock_item_writes() -> None:
    # A write statement acquires SQLite's writer even if the row is absent.
    ItemInventory.objects.filter(pk=1).update(generation=F("generation"))


def _inventory_generation() -> str | None:
    return ItemInventory.objects.filter(pk=1).values_list("generation", flat=True).first()


def displayed_inventory_revision() -> str:
    generation = _inventory_generation()
    return signing.dumps(generation, salt=INVENTORY_SALT) if generation is not None else ""


def matches_inventory_revision(token: str) -> bool:
    try:
        revision = signing.loads(token, salt=INVENTORY_SALT)
    except signing.BadSignature:
        return False
    generation = _inventory_generation()
    return (
        isinstance(revision, str)
        and generation is not None
        and constant_time_compare(revision, generation)
    )
