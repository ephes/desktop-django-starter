"""Private shell content and refusals must not outlive the shell session in caches."""

import pytest
from django.http import HttpResponse
from django.test import Client, RequestFactory, override_settings

from desktop_django_starter.middleware import DESKTOP_AUTH_COOKIE, DesktopAuthTokenMiddleware

TOKEN = "synthetic-shell-token"


def assert_private(response):
    directives = set(response["Cache-Control"].split(", "))
    assert {"private", "no-store"} <= directives
    assert "public" not in directives


@pytest.mark.django_db
@pytest.mark.parametrize("method", ["get", "head"])
@pytest.mark.parametrize("path", ["/", "/items/new/", "/tasks/status/", "/missing/"])
@pytest.mark.parametrize("credential", ["header", "cookie", "retired", "missing", "unconfigured"])
def test_shell_responses_and_denials_are_private(method, path, credential):
    client = Client()
    headers = {}
    if credential == "header":
        headers["HTTP_X_DESKTOP_DJANGO_TOKEN"] = TOKEN
    elif credential in {"cookie", "retired"}:
        client.cookies[DESKTOP_AUTH_COOKIE] = TOKEN if credential == "cookie" else "old-token"
    with override_settings(
        DESKTOP_DJANGO_AUTH_TOKEN="" if credential == "unconfigured" else TOKEN,
        DESKTOP_DJANGO_REQUIRE_AUTH_TOKEN=True,
    ):
        response = getattr(client, method)(path, **headers)
    expected = 403
    if credential in {"header", "cookie"}:
        expected = 404 if path == "/missing/" else 200
        # task_status currently accepts GET only; cache policy must include its 405.
        if path == "/tasks/status/" and method == "head":
            expected = 405
    assert response.status_code == expected
    assert_private(response)


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["/", "/items/new/", "/tasks/status/"])
def test_development_without_shell_auth_preserves_cache_behavior(client, path):
    with override_settings(DESKTOP_DJANGO_AUTH_TOKEN="", DESKTOP_DJANGO_REQUIRE_AUTH_TOKEN=False):
        response = client.get(path)
    assert response.status_code == 200
    assert "Cache-Control" not in response


@pytest.mark.django_db
def test_shell_csrf_denial_is_also_private():
    with override_settings(DESKTOP_DJANGO_AUTH_TOKEN=TOKEN):
        response = Client(enforce_csrf_checks=True).post(
            "/items/clear/", HTTP_X_DESKTOP_DJANGO_TOKEN=TOKEN
        )
    assert response.status_code == 403
    assert b"CSRF verification failed" in response.content
    assert_private(response)


def test_shell_policy_overrides_downstream_public_caching():
    middleware = DesktopAuthTokenMiddleware(
        lambda request: HttpResponse("Synthetic", headers={"Cache-Control": "public, max-age=3600"})
    )
    request = RequestFactory().get("/", HTTP_X_DESKTOP_DJANGO_TOKEN=TOKEN)
    with override_settings(DESKTOP_DJANGO_AUTH_TOKEN=TOKEN):
        assert_private(middleware(request))
