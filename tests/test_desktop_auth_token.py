from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import override_settings

from desktop_django_starter.middleware import DESKTOP_AUTH_COOKIE

TOKEN = "test-desktop-auth-token"
HEADER = {"HTTP_X_DESKTOP_DJANGO_TOKEN": TOKEN}
BOOTSTRAP_PATH = "/desktop-auth/bootstrap/"


def test_without_configured_token_health_remains_available(client) -> None:
    with override_settings(DESKTOP_DJANGO_AUTH_TOKEN=""):
        response = client.get("/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_configured_token_rejects_missing_header(client) -> None:
    with override_settings(DESKTOP_DJANGO_AUTH_TOKEN=TOKEN):
        response = client.get("/health/")

    assert response.status_code == 403
    assert response.content == b"Forbidden"


def test_configured_token_rejects_wrong_header(client) -> None:
    with override_settings(DESKTOP_DJANGO_AUTH_TOKEN=TOKEN):
        response = client.get("/health/", HTTP_X_DESKTOP_DJANGO_TOKEN="wrong")

    assert response.status_code == 403
    assert response.content == b"Forbidden"


def test_configured_token_accepts_health_request_with_correct_header(client) -> None:
    with override_settings(DESKTOP_DJANGO_AUTH_TOKEN=TOKEN):
        response = client.get("/health/", **HEADER)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_configured_token_accepts_app_page_with_correct_header(client, db) -> None:
    with override_settings(DESKTOP_DJANGO_AUTH_TOKEN=TOKEN):
        response = client.get("/", **HEADER)

    assert response.status_code == 200


def test_bootstrap_rejects_missing_token(client) -> None:
    with override_settings(DESKTOP_DJANGO_AUTH_TOKEN=TOKEN):
        response = client.get(BOOTSTRAP_PATH, {"next": "/"})

    assert response.status_code == 403
    assert response.content == b"Forbidden"


def test_bootstrap_rejects_wrong_token(client) -> None:
    with override_settings(DESKTOP_DJANGO_AUTH_TOKEN=TOKEN):
        response = client.get(BOOTSTRAP_PATH, {"token": "wrong", "next": "/"})

    assert response.status_code == 403
    assert response.content == b"Forbidden"


def test_bootstrap_sets_httponly_cookie_and_redirects_to_safe_target(client) -> None:
    with override_settings(DESKTOP_DJANGO_AUTH_TOKEN=TOKEN):
        response = client.get(
            BOOTSTRAP_PATH,
            {"token": TOKEN, "next": "/tasks/?status=queued"},
        )

    cookie = response.cookies[DESKTOP_AUTH_COOKIE]
    assert response.status_code == 302
    assert response["Location"] == "/tasks/?status=queued"
    assert cookie.value == TOKEN
    assert cookie["httponly"] is True
    assert cookie["path"] == "/"
    assert cookie["samesite"] == "Strict"
    assert not cookie["secure"]


def test_bootstrap_defaults_missing_next_to_app_root(client) -> None:
    with override_settings(DESKTOP_DJANGO_AUTH_TOKEN=TOKEN):
        response = client.get(BOOTSTRAP_PATH, {"token": TOKEN})

    assert response.status_code == 302
    assert response["Location"] == "/"
    assert DESKTOP_AUTH_COOKIE in response.cookies


def test_bootstrap_rejects_unsafe_next_values(client) -> None:
    unsafe_targets = [
        "https://example.com/",
        "//example.com/",
        "http://127.0.0.1.evil.test/",
        "tasks/",
        "/\\evil.com",
        "/\r\nSet-Cookie:bad=1",
    ]

    with override_settings(DESKTOP_DJANGO_AUTH_TOKEN=TOKEN):
        responses = [
            client.get(BOOTSTRAP_PATH, {"token": TOKEN, "next": next_value})
            for next_value in unsafe_targets
        ]

    assert [response.status_code for response in responses] == [403] * len(unsafe_targets)


def test_bootstrap_cookie_grants_access_to_health_and_app_page(client, db) -> None:
    client.cookies[DESKTOP_AUTH_COOKIE] = TOKEN

    with override_settings(DESKTOP_DJANGO_AUTH_TOKEN=TOKEN):
        health_response = client.get("/health/")
        app_response = client.get("/")

    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}
    assert app_response.status_code == 200


def test_configured_token_protects_packaged_static_route(client, tmp_path: Path) -> None:
    static_root = tmp_path / "staticfiles"

    with override_settings(DEBUG=False, STATIC_ROOT=static_root):
        call_command("collectstatic", interactive=False, verbosity=0, clear=True)

    with override_settings(
        DEBUG=False,
        STATIC_ROOT=static_root,
        DESKTOP_DJANGO_AUTH_TOKEN=TOKEN,
    ):
        missing_token_response = client.get("/static/desktop_django_starter/app.css")
        correct_token_response = client.get(
            "/static/desktop_django_starter/app.css",
            **HEADER,
        )
        client.cookies[DESKTOP_AUTH_COOKIE] = TOKEN
        correct_cookie_response = client.get("/static/desktop_django_starter/app.css")

    assert missing_token_response.status_code == 403
    assert correct_token_response.status_code == 200
    content = b"".join(correct_token_response.streaming_content).decode()
    assert "font-family" in content
    assert correct_cookie_response.status_code == 200


def test_csrf_middleware_remains_enabled() -> None:
    assert "django.middleware.csrf.CsrfViewMiddleware" in settings.MIDDLEWARE
