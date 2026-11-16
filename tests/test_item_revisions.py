"""Displayed content, rather than a fresh POST lookup, owns mutation intent."""

import pytest
from django.urls import reverse

from example_app.models import Item

pytestmark = pytest.mark.django_db


def token(response):
    # Missing token in the original templates still exercises the unsafe POST.
    return response.context.get("item_revision", "")


def test_edit_rejects_stale_form_and_retains_input_until_reload(client):
    item = Item.objects.create(title="Displayed pony", notes="Original")
    url = reverse("example_app:item-update", args=[item.pk]) + "?page=2"
    old = token(client.get(url))
    Item.objects.filter(pk=item.pk).update(title="Newer pony", notes="Newer notes")
    submitted = {"title": "My edit", "notes": "Keep my input", "status": "active", "revision": old}
    response = client.post(url, submitted)
    assert response.status_code == 409
    item.refresh_from_db()
    assert (item.title, item.notes) == ("Newer pony", "Newer notes")
    assert response.context["form"]["title"].value() == "My edit"
    assert response.context["form"]["notes"].value() == "Keep my input"
    assert response.context["item_revision"] == old
    assert "Reload current pony" in response.content.decode()
    # Replaying a conflict must not silently adopt a new revision.
    assert client.post(url, submitted).status_code == 409
    submitted["revision"] = token(client.get(url))
    assert client.post(url, submitted).status_code == 302
    item.refresh_from_db()
    assert item.title == "My edit"


@pytest.mark.parametrize("revision", ["", "tampered", "another-item"])
def test_edit_refuses_missing_forged_and_cross_item_revision(client, revision):
    item = Item.objects.create(title="Current", notes="Current")
    other = Item.objects.create(title="Other", notes="Other")
    url = reverse("example_app:item-update", args=[item.pk])
    if revision == "another-item":
        revision = token(client.get(reverse("example_app:item-update", args=[other.pk])))
    response = client.post(
        url, {"title": "Overwrite", "notes": "Overwrite", "status": "done", "revision": revision}
    )
    assert response.status_code == 409
    item.refresh_from_db()
    assert item.title == "Current"


def test_invalid_form_keeps_original_revision(client):
    item = Item.objects.create(title="Original", notes="Original")
    url = reverse("example_app:item-update", args=[item.pk])
    original = token(client.get(url))
    assert original
    response = client.post(
        url, {"title": "", "notes": "", "status": "backlog", "revision": original}
    )
    assert response.status_code == 200
    assert token(response) == original
    assert response.context["form"].errors


def test_delete_rejects_stale_confirmation_then_fresh_confirmation_deletes_once(client):
    item = Item.objects.create(title="Displayed pony", notes="Displayed notes")
    url = reverse("example_app:item-delete", args=[item.pk])
    old = token(client.get(url))
    Item.objects.filter(pk=item.pk).update(notes="New personality")
    response = client.post(url, {"revision": old})
    assert response.status_code == 409
    assert Item.objects.filter(pk=item.pk).exists()
    assert "Reload current pony" in response.content.decode()
    assert token(response) == old
    assert client.post(url, {"revision": old}).status_code == 409
    current = token(client.get(url))
    assert current and current != old
    assert client.post(url, {"revision": current}).status_code == 302
    assert client.post(url, {"revision": current}).status_code == 404


@pytest.mark.parametrize("revision", ["", "tampered", "another-item"])
def test_delete_refuses_missing_forged_and_cross_item_revision(client, revision):
    item = Item.objects.create(title="Current", notes="Current")
    other = Item.objects.create(title="Other", notes="Other")
    url = reverse("example_app:item-delete", args=[item.pk])
    if revision == "another-item":
        revision = token(client.get(reverse("example_app:item-delete", args=[other.pk])))
    assert client.post(url, {"revision": revision}).status_code == 409
    assert Item.objects.filter(pk=item.pk).exists()


def test_delete_from_last_page_clamps_return_navigation(client):
    Item.objects.bulk_create([Item(title=f"Pony {i}") for i in range(20)])
    item = Item.objects.create(title="Last page", notes="Synthetic")
    url = reverse("example_app:item-delete", args=[item.pk]) + "?page=2"
    current = token(client.get(url))
    response = client.post(url, {"revision": current})
    assert response.url == reverse("example_app:item-list") + "?page=1"
    assert client.get(response.url).status_code == 200


@pytest.mark.parametrize("csrf", ["missing", "wrong", "foreign", "valid"])
def test_edit_revision_does_not_bypass_csrf(csrf):
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    item = Item.objects.create(title="Current", notes="Current")
    url = reverse("example_app:item-update", args=[item.pk])
    revision = token(client.get(url))
    data = {"title": "New", "notes": "New", "status": "done", "revision": revision}
    headers = {
        "HTTP_ORIGIN": "https://foreign.example" if csrf == "foreign" else "http://testserver"
    }
    if csrf != "missing":
        headers["HTTP_X_CSRFTOKEN"] = (
            "x" * 32 if csrf == "wrong" else client.cookies["csrftoken"].value
        )
    response = client.post(url, data, **headers)
    assert response.status_code == (302 if csrf == "valid" else 403)
    item.refresh_from_db()
    assert item.title == ("New" if csrf == "valid" else "Current")


def test_modal_submits_list_revision_and_keeps_conflict_visible(client):
    import json
    import re
    import subprocess

    item = Item.objects.create(title="Displayed", notes="Displayed")
    page = client.get(reverse("example_app:item-list")).content.decode()
    revision = re.search(r'data-revision="([^"]+)"', page)[1]
    script = next(
        block.split("</script>")[0]
        for block in page.split("<script>")[1:]
        if "delete-modal" in block
    )
    # The token rendered on the list is accepted by the actual delete endpoint.
    url = reverse("example_app:item-delete", args=[item.pk]) + "?page=1"
    Item.objects.filter(pk=item.pk).update(notes="Newer")
    assert client.post(url, {"revision": revision}).status_code == 409
    harness = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const elements = {};
const listeners = {};
let reloads = 0;
let status = 409;
const calls = [];
function element(id) {
    return elements[id] ||= {
        hidden: false, disabled: false,
        classList: {add() {}, remove() {}, contains() {return true;}},
        addEventListener(event, fn) {listeners[id + ':' + event] = fn;},
        focus() {},
    };
}
const link = {
    getAttribute(name) {return name === 'href' ? URL : REVISION;},
    closest() {return {querySelector() {return {textContent: 'Displayed'};}};},
};
vm.runInNewContext(SCRIPT, {
    document: {
        cookie: '',
        getElementById: element,
        querySelector() {return {value: 'synthetic-csrf'};},
        addEventListener(event, fn) {listeners['document:' + event] = fn;},
    },
    fetch(url, options) {
        calls.push({url, options});
        return Promise.resolve({ok: status === 200, status});
    },
    window: {location: {reload() {reloads++;}}},
});
function open() {
    listeners['document:click']({target: {closest() {return link;}}, preventDefault() {}});
}
open();
listeners['delete-confirm:click']();
setImmediate(() => {
    assert.equal(calls[0].url, URL);
    const body = new URLSearchParams(calls[0].options.body);
    assert.equal(body.get('revision'), REVISION);
    assert.equal(body.get('csrfmiddlewaretoken'), 'synthetic-csrf');
    assert.equal(calls[0].options.headers['X-CSRFToken'], 'synthetic-csrf');
    assert.equal(reloads, 0);
    assert.equal(elements['delete-error'].hidden, false);
    assert.match(elements['delete-error'].textContent, /changed/);
    assert.equal(elements['delete-reload'].href, URL);
    assert.equal(elements['delete-reload'].hidden, false);
    assert.equal(elements['delete-confirm'].disabled, true);
    open();
    assert.equal(elements['delete-error'].hidden, true);
    assert.equal(elements['delete-confirm'].disabled, false);
    status = 200;
    listeners['delete-confirm:click']();
    setImmediate(() => assert.equal(reloads, 1));
});
"""
    result = subprocess.run(
        [
            "node",
            "-e",
            f"const SCRIPT={json.dumps(script)}, REVISION={json.dumps(revision)};"
            f"const URL={json.dumps(url)};"
            + harness,
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
