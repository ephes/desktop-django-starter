"""Signed snapshots of the item content shown in a mutation form."""

import hashlib
import json

from django.core import signing
from django.utils.crypto import constant_time_compare

from .models import Item

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


INVENTORY_SALT = "example_app.inventory-revision"


def _inventory_revision() -> str:
    digest = hashlib.sha256()
    for item in Item.objects.order_by("pk").iterator():
        digest.update(_content_revision(item).encode("ascii"))
    return digest.hexdigest()


def displayed_inventory_revision() -> str:
    return signing.dumps(_inventory_revision(), salt=INVENTORY_SALT)


def matches_inventory_revision(token: str) -> bool:
    try:
        revision = signing.loads(token, salt=INVENTORY_SALT)
    except signing.BadSignature:
        return False
    return isinstance(revision, str) and constant_time_compare(revision, _inventory_revision())
