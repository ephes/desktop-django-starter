from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from .models import DemoContentState, Item


@dataclass(frozen=True)
class DemoPony:
    title: str
    notes: str
    status: str


FIRST_RUN_PONIES = (
    DemoPony(
        title="Skylark Comet",
        notes="Leads the dawn warm-up lap and keeps the stable bells in rhythm.",
        status=Item.Status.ACTIVE,
    ),
    DemoPony(
        title="Marigold Drift",
        notes="Collects ribbon scraps for the tack room and naps in every patch of sun.",
        status=Item.Status.BACKLOG,
    ),
    DemoPony(
        title="Northwind Glimmer",
        notes="Already brushed, braided, and waiting by the gate for the next parade.",
        status=Item.Status.DONE,
    ),
)


@transaction.atomic
def seed_first_run_demo_content() -> int:
    if DemoContentState.objects.filter(key=DemoContentState.Key.FIRST_RUN_PONY_SEED).exists():
        return 0

    if Item.objects.exists():
        return 0

    for pony in FIRST_RUN_PONIES:
        Item.objects.create(title=pony.title, notes=pony.notes, status=pony.status)

    DemoContentState.objects.create(key=DemoContentState.Key.FIRST_RUN_PONY_SEED)
    return len(FIRST_RUN_PONIES)
