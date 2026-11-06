"""Exercise both shell credentials through the real CSRF and mutation stack."""

import pytest
from django.conf import settings
from django.test import Client, override_settings
from django.urls import reverse
from django_tasks_db.models import DBTaskResult

from desktop_django_starter.middleware import DESKTOP_AUTH_COOKIE
from example_app.models import Item
from tasks_demo.models import SimulatedTask
from tasks_demo.tasks import run_simulated_task

TOKEN = "synthetic-shell-token"


@pytest.mark.django_db
@pytest.mark.parametrize("credential", ["header", "cookie"])
@pytest.mark.parametrize("action", ["item-delete", "item-clear", "task-run", "task-clear"])
@pytest.mark.parametrize(
    "csrf", ["missing", "wrong", "foreign-origin", "valid", "no-origin", "no-shell", "neither"]
)
def test_shell_auth_and_csrf_are_both_required(credential, action, csrf) -> None:
    item = Item.objects.create(title="Synthetic pony")
    other_item = Item.objects.create(title="Another synthetic pony")
    pending = SimulatedTask.objects.create(label="Synthetic queued routine")
    queued = run_simulated_task.enqueue(pending.pk)
    pending.backend_task_id = queued.id
    pending.save(update_fields=["backend_task_id"])
    running = SimulatedTask.objects.create(
        label="Synthetic running routine", status=SimulatedTask.Status.RUNNING
    )
    SimulatedTask.objects.create(label="Synthetic done routine", status=SimulatedTask.Status.DONE)
    SimulatedTask.objects.create(
        label="Synthetic failed routine", status=SimulatedTask.Status.FAILED
    )
    before_items = list(Item.objects.order_by("pk").values())
    before_tasks = list(SimulatedTask.objects.order_by("pk").values())
    before_queue = list(DBTaskResult.objects.order_by("pk").values())

    client = Client(enforce_csrf_checks=True)
    headers = {}
    if credential == "header":
        headers["HTTP_X_DESKTOP_DJANGO_TOKEN"] = TOKEN
    else:
        client.cookies[DESKTOP_AUTH_COOKIE] = TOKEN

    with override_settings(DESKTOP_DJANGO_AUTH_TOKEN=TOKEN):
        # Use an actual form GET so the CSRF cookie comes from the application.
        page = client.get(reverse("example_app:item-create"), **headers)
        assert page.status_code == 200
        csrf_token = client.cookies[settings.CSRF_COOKIE_NAME].value
        headers["HTTP_ORIGIN"] = "http://testserver"
        if csrf not in {"missing", "neither"}:
            headers["HTTP_X_CSRFTOKEN"] = "x" * 32 if csrf == "wrong" else csrf_token
        if csrf == "foreign-origin":
            headers["HTTP_ORIGIN"] = "https://foreign.example"
        if csrf == "no-origin":
            headers.pop("HTTP_ORIGIN")
        if csrf in {"no-shell", "neither"}:
            headers.pop("HTTP_X_DESKTOP_DJANGO_TOKEN", None)
            client.cookies.pop(DESKTOP_AUTH_COOKIE, None)

        if action == "item-delete":
            url = reverse("example_app:item-delete", args=[item.pk])
        elif action == "item-clear":
            url = reverse("example_app:item-clear")
        else:
            url = reverse(f"tasks_demo:{action}")
        response = client.post(url, **headers)

    if csrf not in {"valid", "no-origin"}:
        assert response.status_code == 403
        if csrf in {"no-shell", "neither"}:
            # Shell authentication rejects before Django's CSRF failure page.
            assert response.content == b"Forbidden"
        else:
            assert b"CSRF verification failed" in response.content
        assert list(Item.objects.order_by("pk").values()) == before_items
        assert list(SimulatedTask.objects.order_by("pk").values()) == before_tasks
        assert list(DBTaskResult.objects.order_by("pk").values()) == before_queue
        return

    if action == "item-delete":
        assert response.status_code == 302
        assert list(Item.objects.values_list("pk", flat=True)) == [other_item.pk]
    elif action == "item-clear":
        assert response.status_code == 200
        assert not Item.objects.exists()
    else:
        assert list(Item.objects.order_by("pk").values()) == before_items

    if action == "task-run":
        assert response.status_code == 201
        created = SimulatedTask.objects.get(pk=response.json()["id"])
        assert created.status == SimulatedTask.Status.PENDING
        assert DBTaskResult.objects.filter(pk=created.backend_task_id).exists()
        assert SimulatedTask.objects.count() == len(before_tasks) + 1
        assert DBTaskResult.objects.count() == len(before_queue) + 1
    elif action == "task-clear":
        assert response.status_code == 200
        assert set(SimulatedTask.objects.values_list("pk", flat=True)) == {pending.pk, running.pk}
    else:
        assert list(SimulatedTask.objects.order_by("pk").values()) == before_tasks
    if action != "task-run":
        assert list(DBTaskResult.objects.order_by("pk").values()) == before_queue
