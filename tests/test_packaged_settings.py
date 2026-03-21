import importlib
import sys
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

MODULE = "desktop_django_starter.settings.packaged"


def unload_packaged_settings() -> None:
    sys.modules.pop(MODULE, None)


def test_packaged_settings_require_secret_key(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)
    monkeypatch.setenv("DESKTOP_DJANGO_APP_DATA_DIR", str(tmp_path))
    unload_packaged_settings()

    with pytest.raises(ImproperlyConfigured):
        importlib.import_module(MODULE)

    unload_packaged_settings()


def test_packaged_settings_use_app_data_dir(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DJANGO_SECRET_KEY", "packaged-test-secret")
    monkeypatch.setenv("DESKTOP_DJANGO_APP_DATA_DIR", str(tmp_path))
    unload_packaged_settings()

    settings = importlib.import_module(MODULE)

    assert settings.DATABASES["default"]["NAME"] == tmp_path / "app.sqlite3"
    assert settings.STATIC_ROOT == tmp_path / "staticfiles"

    unload_packaged_settings()
