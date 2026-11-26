"""Real subprocess interruption and first-open oracles; synthetic SQLite/media only."""

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

from desktop_django_starter import app_state


def seed(root):
    old = app_state.prepare_versioned_state(root, "1.0.0")
    connection = sqlite3.connect(old / "app.sqlite3")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE sentinel (value TEXT)")
    connection.execute("INSERT INTO sentinel VALUES ('wal-sentinel')")
    connection.commit()
    (old / "media" / "upload").write_bytes(b"synthetic-media")
    return old, connection


def assert_generation(state):
    with sqlite3.connect(state / "app.sqlite3") as connection:
        assert connection.execute("SELECT value FROM sentinel").fetchall() == [("wal-sentinel",)]
    assert (state / "media" / "upload").read_bytes() == b"synthetic-media"
    assert json.loads((state / "state.json").read_text())["version"] == "2.0.0"


@pytest.mark.parametrize(
    "filename", [".stage-owner.json", "app.sqlite3", "media/upload", "state.json"]
)
def test_file_sync_failure_never_publishes(monkeypatch, tmp_path, filename):
    old, connection = seed(tmp_path)
    try:
        real_sync = os.fsync

        def fail(descriptor):
            for stage in (tmp_path / "state").glob(".dds-stage-*"):
                target = stage / filename
                if target.exists() and os.path.samestat(target.stat(), os.fstat(descriptor)):
                    raise OSError("injected sync failure")
            real_sync(descriptor)

        monkeypatch.setattr(os, "fsync", fail)
        with pytest.raises(ImproperlyConfigured):
            app_state.prepare_versioned_state(tmp_path, "2.0.0")
        assert not (tmp_path / "state" / "2.0.0").exists()
        assert (old / "media" / "upload").read_bytes() == b"synthetic-media"
    finally:
        connection.close()


def test_short_stage_owner_write_aborts_before_copying_state(monkeypatch, tmp_path):
    old, connection = seed(tmp_path)
    real_write_text = Path.write_text

    def short_owner_write(path, text, *args, **kwargs):
        written = real_write_text(path, text, *args, **kwargs)
        if path.name == app_state.OWNER_FILENAME:
            # The write reports success, but the bytes on disk are cut short.
            with path.open("r+b") as stream:
                stream.truncate(path.stat().st_size - 1)
        return written

    def unexpected_copy(source, staging):
        pytest.fail("state copy began after a short stage-owner marker write")

    try:
        monkeypatch.setattr(Path, "write_text", short_owner_write)
        monkeypatch.setattr(app_state, "_copy_state", unexpected_copy)
        with pytest.raises(ImproperlyConfigured, match="incomplete stage-owner marker"):
            app_state.prepare_versioned_state(tmp_path, "2.0.0")

        assert not (old.parent / "2.0.0").exists()
        assert not list(old.parent.glob(".dds-stage-*"))
        assert connection.execute("SELECT value FROM sentinel").fetchall() == [("wal-sentinel",)]
        assert (old / "media" / "upload").read_bytes() == b"synthetic-media"
    finally:
        connection.close()


def test_marker_sync_follows_payload_sync(monkeypatch, tmp_path):
    old, connection = seed(tmp_path)
    calls = []
    real_sync = os.fsync

    def observe(descriptor):
        stages = list((tmp_path / "state").glob(".dds-stage-*"))
        for stage in stages:
            for filename in ("app.sqlite3", "media/upload", "state.json"):
                target = stage / filename
                if target.exists() and os.path.samestat(target.stat(), os.fstat(descriptor)):
                    calls.append(filename)
        real_sync(descriptor)

    monkeypatch.setattr(os, "fsync", observe)
    try:
        state = app_state.prepare_versioned_state(tmp_path, "2.0.0")
        assert_generation(state)
        assert calls.index("app.sqlite3") < calls.index("state.json")
        assert calls.index("media/upload") < calls.index("state.json")
    finally:
        connection.close()


CHILD = r"""
import json, sqlite3, sys, time
from pathlib import Path
from desktop_django_starter import app_state
root, control, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
control.mkdir(exist_ok=True)
(control / 'entered').touch()
def pause():
    (control / 'paused').touch()
    deadline = time.monotonic() + 15
    while not (control / 'release').exists():
        if time.monotonic() > deadline:
            raise RuntimeError('barrier timeout')
        time.sleep(0.01)
if mode in {'database', 'copy', 'fail'}:
    copy = app_state._copy_database if mode == 'database' else app_state._copy_state
    def hooked(source, destination):
        copy(source, destination)
        pause()
        if mode == 'fail':
            raise OSError('injected copy failure')
    if mode == 'database':
        app_state._copy_database = hooked
    else:
        app_state._copy_state = hooked
elif mode in {'rename', 'published'}:
    rename = Path.rename
    def hooked(self, target):
        if self.parent == root / 'state' and self.name.startswith('.'):
            if mode == 'rename':
                pause()
            result = rename(self, target)
            if mode == 'published':
                pause()
            return result
        return rename(self, target)
    Path.rename = hooked
try:
    state = app_state.prepare_versioned_state(root, '2.0.0')
except Exception as error:
    print(type(error).__name__, flush=True)
    sys.exit(7)
with sqlite3.connect(state / 'app.sqlite3') as db:
    values = db.execute('SELECT value FROM sentinel').fetchall()
print(json.dumps([str(state), values, (state / 'media' / 'upload').read_text()]), flush=True)
"""


def wait_file(path, child):
    deadline = time.monotonic() + 10
    while not path.exists():
        if child.poll() is not None:
            raise AssertionError(child.communicate())
        if time.monotonic() > deadline:
            raise AssertionError(f"barrier not reached: {path.name}")
        time.sleep(0.01)


def start(root, control, mode):
    return subprocess.Popen(
        [sys.executable, "-c", CHILD, str(root), str(control), mode],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def stop(child):
    if child.poll() is None:
        child.kill()
    child.communicate(timeout=5)


@pytest.mark.parametrize("point", ["database", "copy", "rename", "published"])
def test_killed_initializer_recovers_only_its_owned_stage(tmp_path, point):
    root = tmp_path / "app"
    old, connection = seed(root)
    unrelated = root / "state" / ".unrelated"
    unrelated.mkdir()
    (unrelated / "sentinel").write_text("keep")
    child = start(root, tmp_path / "control", point)
    try:
        wait_file(tmp_path / "control" / "paused", child)
        child.kill()
        child.communicate(timeout=5)
        state = app_state.prepare_versioned_state(root, "2.0.0")
        assert_generation(state)
        assert [p for p in (root / "state").iterdir() if p.is_dir() and p.name.startswith(".")] == [
            unrelated
        ]
        assert (unrelated / "sentinel").read_text() == "keep"
        with sqlite3.connect(old / "app.sqlite3") as db:
            assert db.execute("SELECT value FROM sentinel").fetchall() == [("wal-sentinel",)]
    finally:
        stop(child)
        connection.close()


@pytest.mark.parametrize("first_mode", ["copy", "fail"])
def test_two_real_initializers_converge_without_deleting_active_stage(tmp_path, first_mode):
    root = tmp_path / "app"
    old, connection = seed(root)
    one = tmp_path / "one"
    two = tmp_path / "two"
    first = start(root, one, first_mode)
    second = None
    try:
        wait_file(one / "paused", first)
        active = list((root / "state").glob(".dds-stage-*"))
        second = start(root, two, "normal")
        wait_file(two / "entered", second)
        # The contender must remain blocked while the owner is alive.
        with pytest.raises(subprocess.TimeoutExpired):
            second.wait(timeout=0.15)
        assert active and all(path.is_dir() for path in active)
        (one / "release").touch()
        first_out, first_err = first.communicate(timeout=10)
        second_out, second_err = second.communicate(timeout=10)
        assert first.returncode == (7 if first_mode == "fail" else 0), first_err
        assert second.returncode == 0, second_err
        if first_mode == "copy":
            assert json.loads(first_out) == json.loads(second_out)
        assert_generation(root / "state" / "2.0.0")
        assert list((root / "state").glob(".dds-stage-*")) == []
        assert (old / "media" / "upload").read_bytes() == b"synthetic-media"
    finally:
        stop(first)
        if second is not None:
            stop(second)
        connection.close()


def test_invalid_staged_database_is_refused_before_publication(monkeypatch, tmp_path):
    old, connection = seed(tmp_path)
    state_root = old.parent
    sync = app_state.sync_directory

    def replace_staged_database(path):
        sync(path)
        if path.name.startswith(app_state.STAGE_PREFIX) and (path / "state.json").exists():
            database = path / "app.sqlite3"
            database.unlink()
            database.mkdir()

    try:
        with monkeypatch.context() as patch:
            patch.setattr(app_state, "sync_directory", replace_staged_database)
            with pytest.raises(ImproperlyConfigured, match="single-link regular file"):
                app_state.prepare_versioned_state(tmp_path, "2.0.0")

        assert not (state_root / "2.0.0").exists()
        assert list(state_root.glob(f"{app_state.STAGE_PREFIX}*")) == []
        assert app_state.prepare_versioned_state(tmp_path, "1.0.0") == old
        assert connection.execute("SELECT value FROM sentinel").fetchall() == [("wal-sentinel",)]
        assert_generation(app_state.prepare_versioned_state(tmp_path, "2.0.0"))
    finally:
        connection.close()


def test_post_rename_sync_error_retains_visible_complete_generation(monkeypatch, tmp_path):
    old, connection = seed(tmp_path)
    sync = app_state.sync_directory

    def fail_after_rename(path):
        if path == tmp_path / "state" and (path / "2.0.0").exists():
            raise OSError("injected final directory sync failure")
        sync(path)

    try:
        monkeypatch.setattr(app_state, "sync_directory", fail_after_rename)
        with pytest.raises(ImproperlyConfigured, match="visible.*durability is uncertain"):
            app_state.prepare_versioned_state(tmp_path, "2.0.0")
        assert_generation(tmp_path / "state" / "2.0.0")
        assert (old / "app.sqlite3").is_file()
        monkeypatch.undo()
        assert_generation(app_state.prepare_versioned_state(tmp_path, "2.0.0"))
    finally:
        connection.close()


def test_rename_failure_preserves_predecessor_and_retry(monkeypatch, tmp_path):

    old, connection = seed(tmp_path)
    rename = Path.rename

    def fail(stage, destination):
        if stage.name.startswith(".dds-stage-"):
            raise OSError("injected rename failure")
        return rename(stage, destination)

    try:
        monkeypatch.setattr(Path, "rename", fail)
        with pytest.raises(ImproperlyConfigured):
            app_state.prepare_versioned_state(tmp_path, "2.0.0")
        assert not (tmp_path / "state" / "2.0.0").exists()
        assert list((tmp_path / "state").glob(".dds-stage-*")) == []
        assert (old / "media" / "upload").read_bytes() == b"synthetic-media"
        monkeypatch.undo()
        assert_generation(app_state.prepare_versioned_state(tmp_path, "2.0.0"))
    finally:
        connection.close()


@pytest.mark.parametrize("damage", ["no-owner", "wrong-owner", "link", "unknown-file", "budget"])
def test_ambiguous_stage_is_retained_with_bounded_diagnostic(monkeypatch, tmp_path, caplog, damage):
    from desktop_django_starter import state_staging

    root = tmp_path / "app"
    previous = app_state.prepare_versioned_state(root, "1.0.0")
    stage = root / "state" / (".dds-stage-" + "a" * 32)
    stage.mkdir()
    owner = {"schema": 1, "stage": stage.name, "kind": "dds-state-initialization"}
    if damage == "wrong-owner":
        owner["schema"] = 99
    if damage != "no-owner":
        (stage / ".stage-owner.json").write_text(json.dumps(owner))
    if damage == "link":
        (stage / "media").symlink_to(previous, target_is_directory=True)
    elif damage == "unknown-file":
        (stage / "unrelated").write_text("keep")
    elif damage == "budget":
        monkeypatch.setattr(state_staging, "MAX_RECOVERY_ENTRIES", 1)
        (stage / "media").mkdir()
        (stage / "media" / "extra").write_text("keep")
    app_state.prepare_versioned_state(root, "2.0.0")
    assert stage.is_dir()
    assert "Retained" in caplog.text
    assert len(caplog.text) < 1000


def test_failing_warning_sink_does_not_stop_stage_recovery(monkeypatch, tmp_path):
    import contextlib
    import logging

    from desktop_django_starter import state_staging

    class BrokenSink(logging.Handler):
        def emit(self, record):
            raise RuntimeError("log sink unavailable")

    root = tmp_path / "app"
    app_state.prepare_versioned_state(root, "1.0.0")
    owner = {"schema": 1, "kind": "dds-state-initialization"}
    ambiguous = root / "state" / (".dds-stage-" + "0" * 32)
    ambiguous.mkdir()
    (ambiguous / "unrelated").write_text("keep")
    owned = root / "state" / (".dds-stage-" + "f" * 32)
    owned.mkdir()
    (owned / ".stage-owner.json").write_text(json.dumps({**owner, "stage": owned.name}))
    (owned / "media").mkdir()
    real_scandir = os.scandir

    @contextlib.contextmanager
    def ambiguous_first(path):
        # Make the refused stage precede the owned one regardless of fs order.
        with real_scandir(path) as entries:
            yield iter(sorted(entries, key=lambda entry: entry.name))

    monkeypatch.setattr(state_staging.os, "scandir", ambiguous_first)
    handler = BrokenSink()
    state_staging.logger.addHandler(handler)
    try:
        app_state.prepare_versioned_state(root, "2.0.0")
    finally:
        state_staging.logger.removeHandler(handler)
    assert (ambiguous / "unrelated").read_text() == "keep"
    assert not owned.exists()
    assert (root / "state" / "2.0.0").is_dir()


def test_recovery_discovery_is_bounded(monkeypatch, tmp_path):
    from desktop_django_starter import state_staging

    app_state.prepare_versioned_state(tmp_path, "1.0.0")
    monkeypatch.setattr(state_staging, "MAX_DISCOVERY_ENTRIES", 1)
    with pytest.raises(ImproperlyConfigured, match="discovery"):
        app_state.prepare_versioned_state(tmp_path, "2.0.0")
    assert not (tmp_path / "state" / "2.0.0").exists()
