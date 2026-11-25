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


def test_packaged_settings_create_owner_only_secret_key_once(monkeypatch, tmp_path: Path) -> None:
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


def test_packaged_settings_env_secret_key_overrides_key_file(monkeypatch, tmp_path: Path) -> None:
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


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory fsync")
def test_secret_key_retries_directory_sync_without_replacing_published_key(
    monkeypatch, tmp_path: Path
) -> None:
    events = []
    real_link = os.link
    real_fsync = os.fsync
    sync_error = OSError("synthetic directory sync failure")

    def link(source, destination):
        real_link(source, destination)
        events.append("link")

    def fsync(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            events.append("directory sync")
            if events.count("directory sync") == 1:
                raise sync_error
        else:
            events.append("file sync")
        real_fsync(descriptor)

    monkeypatch.setattr(runtime_secret.os, "link", link)
    monkeypatch.setattr(runtime_secret.os, "fsync", fsync)
    with pytest.raises(OSError) as exc:
        load_or_create_secret_key(tmp_path)

    key_path = tmp_path / SECRET_KEY_FILENAME
    assert exc.value is sync_error
    assert events == ["file sync", "link", "directory sync"]
    published_key = key_path.read_bytes()
    assert list(tmp_path.iterdir()) == [key_path]

    assert load_or_create_secret_key(tmp_path).encode("ascii") == published_key
    assert key_path.read_bytes() == published_key
    assert events == ["file sync", "link", "directory sync", "directory sync"]


@pytest.mark.parametrize("operation", ["fsync", "link"])
def test_secret_key_stage_cleanup_preserves_creation_failure(
    monkeypatch, tmp_path: Path, operation: str
) -> None:
    creation_error = OSError(f"synthetic {operation} failure")

    def fail_creation(*args):
        raise creation_error

    def fail_cleanup(path, *, missing_ok=False):
        raise PermissionError("synthetic stage cleanup failure")

    monkeypatch.setattr(runtime_secret.os, operation, fail_creation)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_cleanup)
        with pytest.raises(OSError) as exc:
            load_or_create_secret_key(tmp_path)

    assert exc.value is creation_error
    assert any("synthetic stage cleanup failure" in note for note in exc.value.__notes__)
    assert not (tmp_path / SECRET_KEY_FILENAME).exists()


@pytest.mark.parametrize("another_creator_wins", [False, True])
def test_secret_key_stage_cleanup_failure_keeps_published_key(
    monkeypatch, tmp_path: Path, caplog, another_creator_wins: bool
) -> None:
    key_path = tmp_path / SECRET_KEY_FILENAME
    real_link = os.link

    def publish(source, destination):
        if another_creator_wins:
            key_path.write_text("winner-secret")
        real_link(source, destination)

    def fail_cleanup(path, *, missing_ok=False):
        raise PermissionError("synthetic stage cleanup failure")

    monkeypatch.setattr(runtime_secret.os, "link", publish)
    monkeypatch.setattr(runtime_secret.secrets, "token_urlsafe", lambda _: "our-secret")
    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_cleanup)
        key = load_or_create_secret_key(tmp_path)

    assert key == ("winner-secret" if another_creator_wins else "our-secret")
    assert load_or_create_secret_key(tmp_path) == key_path.read_text() == key
    assert "synthetic stage cleanup failure" in caplog.text


def test_packaged_settings_use_app_data_dir(monkeypatch, tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    monkeypatch.setenv("DJANGO_SECRET_KEY", "packaged-test-secret")
    monkeypatch.setenv("DESKTOP_DJANGO_APP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DESKTOP_DJANGO_BUNDLE_DIR", str(bundle_dir))
    monkeypatch.setenv("DESKTOP_DJANGO_APP_VERSION", "1.2.3")
    unload_packaged_settings()

    settings = importlib.import_module(MODULE)

    state_dir = tmp_path / "state" / "1.2.3"
    assert settings.DATABASES["default"]["NAME"] == state_dir / "app.sqlite3"
    assert settings.MEDIA_ROOT == state_dir / "media"
    assert settings.CACHES["default"]["LOCATION"] == state_dir / "cache"
    assert settings.DATABASES["default"]["OPTIONS"]["transaction_mode"] == "IMMEDIATE"
    assert settings.DATABASES["default"]["OPTIONS"]["timeout"] == 20
    init_command = settings.DATABASES["default"]["OPTIONS"]["init_command"]
    assert "PRAGMA journal_mode=WAL;" in init_command
    assert "PRAGMA synchronous=NORMAL;" in init_command
    assert "PRAGMA cache_size=-20000;" in init_command
    assert "PRAGMA mmap_size=134217728;" in init_command
    assert settings.STATIC_ROOT == bundle_dir / "staticfiles"
    assert "django_tasks" not in settings.INSTALLED_APPS
    assert "django_tasks_db" in settings.INSTALLED_APPS
    assert settings.TASKS["default"]["BACKEND"] == "django_tasks_db.DatabaseBackend"

    unload_packaged_settings()


def test_packaged_sqlite_pragmas_apply_on_connection(monkeypatch, tmp_path: Path) -> None:
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


def test_packaged_settings_require_token_and_keep_app_data_private(
    monkeypatch, tmp_path: Path
) -> None:
    app_data_dir = tmp_path / "app-data"
    app_data_dir.mkdir(mode=0o755)

    settings_module = load_packaged_settings(monkeypatch, app_data_dir)

    assert settings_module.DEBUG is False
    assert settings_module.DESKTOP_DJANGO_REQUIRE_AUTH_TOKEN is True
    if os.name != "nt":
        assert stat.S_IMODE(app_data_dir.stat().st_mode) == 0o700


@pytest.mark.parametrize("kind", ["fifo", "reparse", "oversized"])
def test_secret_key_descriptor_rejects_unsafe_files(monkeypatch, tmp_path: Path, kind) -> None:
    from types import SimpleNamespace

    key_path = tmp_path / SECRET_KEY_FILENAME
    key_path.write_text("synthetic-key")
    original_fstat = os.fstat
    calls = []

    def unsafe_info(descriptor):
        calls.append(descriptor)
        info = original_fstat(descriptor)
        return SimpleNamespace(
            st_mode=stat.S_IFIFO if kind == "fifo" else info.st_mode,
            st_size=4097 if kind == "oversized" else info.st_size,
            st_uid=getattr(info, "st_uid", 0),
            st_file_attributes=0x400 if kind == "reparse" else 0,
        )

    monkeypatch.setattr(runtime_secret.os, "fstat", unsafe_info)
    with pytest.raises(ImproperlyConfigured, match="unsafe or invalid"):
        load_or_create_secret_key(tmp_path)
    assert len(calls) == 1
    assert key_path.read_text() == "synthetic-key"


def test_secret_key_symlink_is_rejected_without_touching_target(tmp_path: Path) -> None:
    target = tmp_path / "unrelated"
    target.write_text("unrelated-secret")
    target.chmod(0o644)
    original_mode = target.stat().st_mode
    (tmp_path / SECRET_KEY_FILENAME).symlink_to(target)
    with pytest.raises(ImproperlyConfigured):
        load_or_create_secret_key(tmp_path)
    assert target.read_text() == "unrelated-secret"
    assert target.stat().st_mode == original_mode


def test_secret_key_directory_has_controlled_error(tmp_path: Path) -> None:
    (tmp_path / SECRET_KEY_FILENAME).mkdir()
    with pytest.raises(ImproperlyConfigured):
        load_or_create_secret_key(tmp_path)


def test_secret_key_read_is_bounded_if_file_grows(monkeypatch, tmp_path: Path) -> None:
    key_path = tmp_path / SECRET_KEY_FILENAME
    key_path.write_bytes(b"a" * 4097)
    original_fstat = os.fstat

    def stale_info(descriptor):
        from types import SimpleNamespace

        info = original_fstat(descriptor)
        return SimpleNamespace(
            st_mode=info.st_mode,
            st_size=1,
            st_uid=getattr(info, "st_uid", 0),
            st_file_attributes=0,
        )

    monkeypatch.setattr(runtime_secret.os, "fstat", stale_info)
    with pytest.raises(ImproperlyConfigured):
        load_or_create_secret_key(tmp_path)


@pytest.mark.parametrize("replacement", [b"edited-secret", b"short"])
def test_secret_key_refuses_in_place_changes_during_read(
    monkeypatch, tmp_path: Path, replacement: bytes
) -> None:
    key_path = tmp_path / SECRET_KEY_FILENAME
    key_path.write_bytes(b"stable-secret")
    assert load_or_create_secret_key(tmp_path) == "stable-secret"
    original_fdopen = os.fdopen
    original_info = key_path.stat()

    def edit_before_read(descriptor, mode, **kwargs):
        key_path.write_bytes(replacement)
        os.utime(
            key_path,
            ns=(original_info.st_atime_ns, original_info.st_mtime_ns - 2_000_000_000),
        )
        return original_fdopen(descriptor, mode, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(runtime_secret.os, "fdopen", edit_before_read)
        with pytest.raises(ImproperlyConfigured, match="changed while being read"):
            load_or_create_secret_key(tmp_path)

    assert load_or_create_secret_key(tmp_path) == replacement.decode("ascii")


def test_windows_secret_open_preserves_reparse_points(monkeypatch, tmp_path: Path) -> None:
    import ctypes
    from types import SimpleNamespace

    calls = []

    class CreateFile:
        def __call__(self, *args):
            calls.append(args)
            return 123

    class CloseHandle:
        def __call__(self, handle):
            raise AssertionError("descriptor owns handle after successful conversion")

    kernel32 = SimpleNamespace(CreateFileW=CreateFile(), CloseHandle=CloseHandle())
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **kw: kernel32, raising=False)
    monkeypatch.setattr(os, "O_BINARY", 0x8000, raising=False)
    monkeypatch.setitem(sys.modules, "msvcrt", SimpleNamespace(open_osfhandle=lambda h, f: 456))
    assert runtime_secret._open_key_windows(tmp_path / SECRET_KEY_FILENAME) == 456
    assert calls[0][4] == 3  # OPEN_EXISTING, never create a missing source
    assert calls[0][5] & 0x00200000  # FILE_FLAG_OPEN_REPARSE_POINT


@pytest.mark.skipif(os.name == "nt", reason="Only POSIX repairs permissions on the descriptor")
def test_secret_key_permissions_follow_descriptor_after_path_replacement(
    monkeypatch, tmp_path: Path
) -> None:
    key_path = tmp_path / SECRET_KEY_FILENAME
    key_path.write_text("original-key")
    key_path.chmod(0o644)
    unrelated = tmp_path / "unrelated"
    unrelated.write_text("unrelated")
    unrelated.chmod(0o644)
    unrelated_mode = unrelated.stat().st_mode
    original_fchmod = os.fchmod
    changed = []

    def replace_path_and_repair(descriptor, mode):
        key_path.rename(tmp_path / "saved-key")
        key_path.symlink_to(unrelated)
        changed.append(True)
        original_fchmod(descriptor, mode)

    monkeypatch.setattr(runtime_secret.os, "fchmod", replace_path_and_repair)
    with pytest.raises(ImproperlyConfigured, match="secret key path .* changed while being read"):
        load_or_create_secret_key(tmp_path)
    assert changed == [True]
    assert stat.S_IMODE((tmp_path / "saved-key").stat().st_mode) == 0o600
    assert unrelated.stat().st_mode == unrelated_mode
    assert unrelated.read_text() == "unrelated"


@pytest.mark.parametrize("replace_key", [False, True], ids=["removed", "replaced"])
def test_secret_key_path_changes_after_final_descriptor_check(
    monkeypatch, tmp_path: Path, replace_key: bool
) -> None:
    key_path = tmp_path / SECRET_KEY_FILENAME
    key_path.write_bytes(b"original-key")
    key_path.chmod(0o600)
    replacement = tmp_path / "replacement"
    replacement.write_bytes(b"new-key-data")
    real_fstat = os.fstat
    calls = 0

    def change_path_after_final_check(descriptor):
        nonlocal calls
        info = real_fstat(descriptor)
        calls += 1
        if calls == 2:
            key_path.rename(tmp_path / "saved-key")
            if replace_key:
                replacement.replace(key_path)
        return info

    with monkeypatch.context() as patch:
        patch.setattr(runtime_secret.os, "fstat", change_path_after_final_check)
        with pytest.raises(
            ImproperlyConfigured, match="secret key path .* changed while being read"
        ):
            load_or_create_secret_key(tmp_path)

    if replace_key:
        assert load_or_create_secret_key(tmp_path) == "new-key-data"
    else:
        assert not key_path.exists()


def test_concurrent_secret_creators_read_one_complete_key(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=8) as pool:
        keys = list(pool.map(lambda _: load_or_create_secret_key(tmp_path), range(16)))
    assert len(set(keys)) == 1
    assert len(keys[0]) >= 50
    assert [p.name for p in tmp_path.iterdir()] == [SECRET_KEY_FILENAME]


@pytest.mark.parametrize("retire_after_descriptor_check", [False, True])
def test_secret_key_read_survives_creator_retiring_its_temp_link(
    monkeypatch, tmp_path: Path, retire_after_descriptor_check: bool
) -> None:
    key_path = tmp_path / SECRET_KEY_FILENAME
    temp_path = tmp_path / ".secret_key.synthetic.tmp"
    temp_path.write_bytes(b"published-key")
    os.link(temp_path, key_path)
    original_fdopen = os.fdopen
    original_fstat = os.fstat
    checks = 0

    def retire_temp_link(descriptor, mode, **kwargs):
        temp_path.unlink()
        return original_fdopen(descriptor, mode, **kwargs)

    def retire_after_check(descriptor):
        nonlocal checks
        info = original_fstat(descriptor)
        checks += 1
        if checks == 2:
            temp_path.unlink()
        return info

    if retire_after_descriptor_check:
        monkeypatch.setattr(runtime_secret.os, "fstat", retire_after_check)
    else:
        monkeypatch.setattr(runtime_secret.os, "fdopen", retire_temp_link)
    assert load_or_create_secret_key(tmp_path) == "published-key"
    assert not temp_path.exists()
