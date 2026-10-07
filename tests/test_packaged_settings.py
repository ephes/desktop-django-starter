import importlib
import os
import stat
import sys
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db.backends.sqlite3.base import DatabaseWrapper

from desktop_django_starter import runtime_secret
from desktop_django_starter.runtime_secret import SECRET_KEY_FILENAME, load_or_create_secret_key

MODULE = "desktop_django_starter.settings.packaged"


def unload_packaged_settings() -> None:
    sys.modules.pop(MODULE, None)


def load_packaged_settings(monkeypatch, app_data_dir: Path):
    monkeypatch.setenv("DESKTOP_DJANGO_APP_DATA_DIR", str(app_data_dir))
    unload_packaged_settings()
    try:
        return importlib.import_module(MODULE)
    finally:
        unload_packaged_settings()


def test_packaged_settings_create_owner_only_secret_key_once(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)

    first = load_packaged_settings(monkeypatch, tmp_path)
    key_path = tmp_path / SECRET_KEY_FILENAME

    assert key_path.is_file()
    assert first.SECRET_KEY == key_path.read_text()
    assert len(first.SECRET_KEY) >= 50
    assert first.SECRET_KEY != "desktop-django-starter-packaged-runtime-secret"
    if os.name != "nt":
        assert stat.S_IMODE(key_path.stat().st_mode) == 0o600
    assert sorted(path.name for path in tmp_path.iterdir() if "secret" in path.name) == [
        SECRET_KEY_FILENAME
    ]

    second = load_packaged_settings(monkeypatch, tmp_path)

    assert second.SECRET_KEY == first.SECRET_KEY


def test_packaged_settings_generate_distinct_keys_per_app_data_dir(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)

    first = load_packaged_settings(monkeypatch, tmp_path / "install-a")
    second = load_packaged_settings(monkeypatch, tmp_path / "install-b")

    assert first.SECRET_KEY != second.SECRET_KEY


def test_packaged_settings_env_secret_key_overrides_key_file(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DJANGO_SECRET_KEY", "explicit-env-secret")

    settings = load_packaged_settings(monkeypatch, tmp_path)

    assert settings.SECRET_KEY == "explicit-env-secret"
    assert not (tmp_path / SECRET_KEY_FILENAME).exists()


def test_packaged_settings_reject_empty_secret_key_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)
    (tmp_path / SECRET_KEY_FILENAME).write_text("  \n")

    with pytest.raises(ImproperlyConfigured):
        load_packaged_settings(monkeypatch, tmp_path)


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_secret_key_file_permissions_are_tightened(tmp_path: Path) -> None:
    key_path = tmp_path / SECRET_KEY_FILENAME
    key_path.write_text("existing-install-secret")
    key_path.chmod(0o644)

    assert load_or_create_secret_key(tmp_path) == "existing-install-secret"
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600


def test_secret_key_creation_keeps_the_key_another_process_created(
    monkeypatch, tmp_path: Path
) -> None:
    key_path = tmp_path / SECRET_KEY_FILENAME
    real_link = os.link

    def racing_link(source, destination):
        key_path.write_text("winner-secret")
        real_link(source, destination)

    monkeypatch.setattr(runtime_secret.os, "link", racing_link)

    assert load_or_create_secret_key(tmp_path) == "winner-secret"
    assert [path.name for path in tmp_path.iterdir()] == [SECRET_KEY_FILENAME]


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
