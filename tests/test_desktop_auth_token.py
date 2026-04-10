from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import override_settings

TOKEN = "test-desktop-auth-token"
HEADER = {"HTTP_X_DESKTOP_DJANGO_TOKEN": TOKEN}


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

    assert missing_token_response.status_code == 403
    assert correct_token_response.status_code == 200
    content = b"".join(correct_token_response.streaming_content).decode()
    assert "font-family" in content


def test_csrf_middleware_remains_enabled() -> None:
    assert "django.middleware.csrf.CsrfViewMiddleware" in settings.MIDDLEWARE
