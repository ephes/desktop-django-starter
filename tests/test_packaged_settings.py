import importlib
import sys
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db.backends.sqlite3.base import DatabaseWrapper

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
    bundle_dir = tmp_path / "bundle"
    monkeypatch.setenv("DJANGO_SECRET_KEY", "packaged-test-secret")
    monkeypatch.setenv("DESKTOP_DJANGO_APP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DESKTOP_DJANGO_BUNDLE_DIR", str(bundle_dir))
    unload_packaged_settings()

    settings = importlib.import_module(MODULE)

    assert settings.DATABASES["default"]["NAME"] == tmp_path / "app.sqlite3"
    assert settings.DATABASES["default"]["OPTIONS"]["transaction_mode"] == "IMMEDIATE"
    assert settings.DATABASES["default"]["OPTIONS"]["timeout"] == 20
    init_command = settings.DATABASES["default"]["OPTIONS"]["init_command"]
    assert "PRAGMA journal_mode=WAL;" in init_command
    assert "PRAGMA synchronous=NORMAL;" in init_command
    assert "PRAGMA cache_size=-20000;" in init_command
    assert "PRAGMA mmap_size=134217728;" in init_command
    assert settings.STATIC_ROOT == bundle_dir / "staticfiles"
    assert "django_tasks" in settings.INSTALLED_APPS
    assert "django_tasks_db" in settings.INSTALLED_APPS
    assert settings.TASKS["default"]["BACKEND"] == "django_tasks_db.DatabaseBackend"

    unload_packaged_settings()


def test_packaged_sqlite_pragmas_apply_on_connection(
    monkeypatch, tmp_path: Path
) -> None:
    bundle_dir = tmp_path / "bundle"
    monkeypatch.setenv("DJANGO_SECRET_KEY", "packaged-test-secret")
    monkeypatch.setenv("DESKTOP_DJANGO_APP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DESKTOP_DJANGO_BUNDLE_DIR", str(bundle_dir))
    unload_packaged_settings()

    settings = importlib.import_module(MODULE)
    database_settings = settings.DATABASES["default"]
    wrapper = DatabaseWrapper(database_settings, alias="default")
    connection_params = wrapper.get_connection_params()
    connection = wrapper.get_new_connection(connection_params)

    try:
        journal_mode = connection.execute("PRAGMA journal_mode;").fetchone()[0]
        synchronous = connection.execute("PRAGMA synchronous;").fetchone()[0]
    finally:
        connection.close()
        unload_packaged_settings()

    assert journal_mode.lower() == "wal"
    assert synchronous == 1
