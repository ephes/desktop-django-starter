from pathlib import Path

from django.core.management import call_command
from django.test import override_settings


def test_packaged_static_route_serves_collected_assets(client, tmp_path: Path) -> None:
    static_root = tmp_path / "staticfiles"

    with override_settings(DEBUG=False, STATIC_ROOT=static_root):
        call_command("collectstatic", interactive=False, verbosity=0, clear=True)

        response = client.get("/static/desktop_django_starter/app.css")

    assert response.status_code == 200
    content = b"".join(response.streaming_content).decode()
    assert "font-family" in content
