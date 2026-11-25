"""Synthetic restored-state admission and bounded media regression cases."""

import errno
import json
import os
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

from desktop_django_starter import app_state, state_files


def previous(root: Path) -> Path:
    state = app_state.prepare_versioned_state(root, "1.0.0")
    with sqlite3.connect(state / "app.sqlite3") as connection:
        connection.execute("CREATE TABLE sentinel (value TEXT)")
        connection.execute("INSERT INTO sentinel VALUES ('synthetic')")
    return state


@pytest.mark.parametrize("close_fails", [False, True])
def test_regular_reader_closes_descriptor_if_stream_construction_fails(
    monkeypatch, tmp_path, close_fails
):
    source = tmp_path / "state.json"
    source.write_bytes(b"{}")
    wrap_error = OSError("injected stream construction failure")
    descriptors = []
    closed = []
    real_close = os.close

    def fail_fdopen(descriptor, *args, **kwargs):
        os.fstat(descriptor)
        descriptors.append(descriptor)
        raise wrap_error

    def record_close(descriptor):
        if descriptor in descriptors:
            closed.append(descriptor)
        real_close(descriptor)
        if descriptor in descriptors and close_fails:
            raise OSError("injected descriptor cleanup failure")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(os, "fdopen", fail_fdopen)
            patch.setattr(os, "close", record_close)
            with pytest.raises(OSError, match="injected stream construction failure") as error:
                with state_files.regular_reader(source):
                    pytest.fail("the reader yielded after stream construction failed")
            assert error.value is wrap_error

        (descriptor,) = descriptors
        assert closed == [descriptor]
        with pytest.raises(OSError) as retired:
            os.fstat(descriptor)
        assert retired.value.errno == errno.EBADF
    finally:
        for descriptor in descriptors:
            if descriptor not in closed:
                real_close(descriptor)


@pytest.mark.skipif(os.name == "nt", reason="Only POSIX directory guards own a descriptor")
@pytest.mark.parametrize("directory_changed", [False, True])
def test_directory_guard_close_failure_preserves_primary_refusal(
    monkeypatch, tmp_path, directory_changed
):
    directory = tmp_path / "state"
    directory.mkdir()
    real_close = os.close
    close_error = OSError("injected directory close failure")
    closed = []
    guarded_fd = None

    def fail_guard_close(descriptor):
        if descriptor == guarded_fd:
            closed.append(descriptor)
            real_close(descriptor)
            raise close_error
        real_close(descriptor)

    expected = ImproperlyConfigured if directory_changed else OSError
    message = "directory changed during initialization" if directory_changed else str(close_error)
    with monkeypatch.context() as patch:
        patch.setattr(os, "close", fail_guard_close)
        with pytest.raises(expected, match=message) as error:
            with state_files.directory_guard(directory) as guarded_fd:
                assert guarded_fd is not None
                if directory_changed:
                    directory.rename(tmp_path / "original")
                    directory.mkdir()

    assert closed == [guarded_fd]
    if not directory_changed:
        assert error.value is close_error


@pytest.mark.parametrize("damage", ["missing", "json", "version", "database", "media", "cache"])
def test_existing_incomplete_generation_refuses_without_replacement(tmp_path, damage):
    previous(tmp_path)
    state = app_state.prepare_versioned_state(tmp_path, "2.0.0")
    marker = state / "state.json"
    if damage == "missing":
        marker.unlink()
    elif damage == "json":
        marker.write_text("{")
    elif damage == "version":
        data = json.loads(marker.read_text())
        data["version"] = "3.0.0"
        marker.write_text(json.dumps(data))
    elif damage == "database":
        (state / "app.sqlite3").unlink()
    else:
        (state / damage).rmdir()
    before = sorted(p.name for p in state.iterdir())
    with pytest.raises(ImproperlyConfigured, match="state.*repair"):
        app_state.prepare_versioned_state(tmp_path, "2.0.0")
    assert sorted(p.name for p in state.iterdir()) == before


def test_fresh_empty_and_copied_generations_reopen(tmp_path):
    fresh = app_state.prepare_versioned_state(tmp_path, "1.0.0")
    assert app_state.prepare_versioned_state(tmp_path, "1.0.0") == fresh
    previous(tmp_path)
    copied = app_state.prepare_versioned_state(tmp_path, "2.0.0")
    assert app_state.prepare_versioned_state(tmp_path, "2.0.0") == copied


@pytest.mark.parametrize("target", ["app", "root", "current", "previous", "database", "marker"])
def test_state_authority_refuses_symlinks(tmp_path, target):
    app = tmp_path / "app"
    old = previous(app)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel").write_text("untouched")
    if target == "app":
        app.rename(outside / "saved")
        app.symlink_to(outside / "saved", target_is_directory=True)
    elif target == "root":
        (app / "state").rename(outside / "saved")
        (app / "state").symlink_to(outside / "saved", target_is_directory=True)
    elif target in {"current", "previous"}:
        path = app / "state" / ("2.0.0" if target == "current" else "1.0.0")
        if path.exists():
            path.rename(outside / "saved")
        path.symlink_to(outside, target_is_directory=True)
    else:
        path = old / ("app.sqlite3" if target == "database" else "state.json")
        path.rename(outside / "saved")
        path.symlink_to(outside / "saved")
    with pytest.raises(ImproperlyConfigured):
        app_state.prepare_versioned_state(app, "2.0.0")
    assert (outside / "sentinel").read_text() == "untouched"


def test_predecessor_swap_before_copy_cannot_publish(monkeypatch, tmp_path):
    old = previous(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel").write_text("untouched")
    copy = app_state._copy_state

    def swap(source, destination):
        old.rename(tmp_path / "saved")
        old.symlink_to(outside, target_is_directory=True)
        copy(source, destination)

    monkeypatch.setattr(app_state, "_copy_state", swap)
    with pytest.raises(ImproperlyConfigured):
        app_state.prepare_versioned_state(tmp_path, "2.0.0")
    assert not (tmp_path / "state" / "2.0.0").exists()
    assert list(outside.iterdir()) == [outside / "sentinel"]


@pytest.mark.parametrize("kind", ["loop", "escape", "files", "bytes", "depth"])
def test_media_copy_refuses_uncontained_or_over_budget_tree(monkeypatch, tmp_path, kind):
    old = previous(tmp_path)
    media = old / "media"
    (media / "one").write_bytes(b"abc")
    if kind in {"loop", "escape"}:
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "synthetic").write_text("outside")
        (media / "link").symlink_to(media if kind == "loop" else outside, target_is_directory=True)
    elif kind == "files":
        monkeypatch.setenv("DESKTOP_DJANGO_MEDIA_MAX_ENTRIES", "1")
        (media / "two").write_text("extra")
    elif kind == "bytes":
        monkeypatch.setenv("DESKTOP_DJANGO_MEDIA_MAX_BYTES", "2")
    else:
        monkeypatch.setenv("DESKTOP_DJANGO_MEDIA_MAX_DEPTH", "1")
        (media / "nested" / "deep").mkdir(parents=True)
    with pytest.raises(ImproperlyConfigured, match="media"):
        app_state.prepare_versioned_state(tmp_path, "2.0.0")
    assert not (tmp_path / "state" / "2.0.0").exists()
    assert (media / "one").read_bytes() == b"abc"
    assert sorted(
        p.name for p in (tmp_path / "state").iterdir() if p.name != ".initialize.lock"
    ) == ["1.0.0"]


def test_media_depth_override_is_capped(monkeypatch, tmp_path_factory):
    app_data = tmp_path_factory.mktemp("d")
    old = previous(app_data)
    media = old / "media"
    supported = media.joinpath(*(["d"] * 64))
    too_deep = supported / "d"
    too_deep.mkdir(parents=True)
    upload = supported / "u"
    upload.write_bytes(b"synthetic media")
    marker = old / "state.json"
    database = old / "app.sqlite3"
    original_marker = marker.read_bytes()
    original_database = database.read_bytes()
    monkeypatch.setenv("DESKTOP_DJANGO_MEDIA_MAX_DEPTH", "10000")

    with pytest.raises(ImproperlyConfigured, match="media tree refused") as caught:
        app_state.prepare_versioned_state(app_data, "2.0.0")

    assert "media depth budget exceeded" in str(caught.value.__cause__)
    assert sorted(p.name for p in old.parent.iterdir()) == [".initialize.lock", "1.0.0"]
    assert marker.read_bytes() == original_marker
    assert database.read_bytes() == original_database
    assert upload.read_bytes() == b"synthetic media"
    assert too_deep.is_dir()

    too_deep.rmdir()
    upgraded = app_state.prepare_versioned_state(app_data, "2.0.0")
    assert (upgraded / "media" / upload.relative_to(media)).read_bytes() == b"synthetic media"


def test_short_media_write_does_not_publish_generation(monkeypatch, tmp_path):
    old = previous(tmp_path)
    upload = old / "media" / "upload"
    payload = b"synthetic media"
    upload.write_bytes(payload)
    real_open = Path.open
    write_counts = []

    class ShortWriter:
        def __init__(self, stream):
            self.stream = stream

        def write(self, chunk):
            written = self.stream.write(chunk[:-1])
            write_counts.append(written)
            return written

    @contextmanager
    def open_with_short_media_writer(path, *args, **kwargs):
        with real_open(path, *args, **kwargs) as stream:
            yield ShortWriter(stream)

    def open_for_copy(path, mode="r", *args, **kwargs):
        if mode == "xb" and path.name == upload.name and path.parent.name == "media":
            return open_with_short_media_writer(path, mode, *args, **kwargs)
        return real_open(path, mode, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", open_for_copy)
        with pytest.raises(ImproperlyConfigured, match="media.*copy failed") as error:
            app_state.prepare_versioned_state(tmp_path, "2.0.0")

    assert write_counts == [len(payload) - 1]
    assert "short write" in str(error.value.__cause__)
    assert sorted(p.name for p in old.parent.iterdir()) == [".initialize.lock", "1.0.0"]
    assert upload.read_bytes() == payload
    assert app_state.prepare_versioned_state(tmp_path, "1.0.0") == old

    copied = app_state.prepare_versioned_state(tmp_path, "2.0.0")
    assert (copied / "media" / upload.name).read_bytes() == payload


@pytest.mark.parametrize("change", ["insert", "remove"])
def test_media_membership_change_in_already_copied_directory_refuses_publication(
    monkeypatch, tmp_path, change
):
    old = previous(tmp_path)
    media = old / "media"
    for name in ("one", "two"):
        directory = media / name
        directory.mkdir()
        (directory / "upload").write_bytes(b"synthetic media")
        # Keep the mutation observable on filesystems with coarse timestamps.
        os.utime(directory, (1_600_000_000, 1_600_000_000))

    reader = state_files.regular_reader
    copied_files = []

    @contextmanager
    def change_membership_during_copy(path, **kwargs):
        with reader(path, **kwargs) as stream:
            if copied_files:
                first = copied_files[0]
                if change == "insert":
                    (first.parent / "late").write_bytes(b"synthetic late upload")
                else:
                    first.unlink()
            copied_files.append(path)
            yield stream

    with monkeypatch.context() as patch:
        patch.setattr(state_files, "regular_reader", change_membership_during_copy)
        with pytest.raises(ImproperlyConfigured, match="media.*copy failed") as error:
            app_state.prepare_versioned_state(tmp_path, "2.0.0")

    assert len(copied_files) == 2
    assert "directory changed" in str(error.value.__cause__)
    assert sorted(p.name for p in old.parent.iterdir()) == [".initialize.lock", "1.0.0"]
    assert app_state.prepare_versioned_state(tmp_path, "1.0.0") == old

    copied = app_state.prepare_versioned_state(tmp_path, "2.0.0")
    source_files = sorted(p.relative_to(media) for p in media.glob("*/*"))
    assert (
        sorted(p.relative_to(copied / "media") for p in (copied / "media").glob("*/*"))
        == source_files
    )


def test_in_place_edit_to_already_copied_media_file_refuses_publication(monkeypatch, tmp_path):
    old = previous(tmp_path)
    media = old / "media"
    original = b"synthetic media"
    edited = b"synthetic MEDIA"
    for name in ("one", "two"):
        upload = media / name
        upload.write_bytes(original)
        os.utime(upload, (1_600_000_000, 1_600_000_000))
    before = media.stat()
    reader = state_files.regular_reader
    copied_files = []

    @contextmanager
    def edit_earlier_file_during_copy(path, **kwargs):
        with reader(path, **kwargs) as stream:
            if copied_files:
                with copied_files[0].open("r+b") as writer:
                    writer.write(edited)
            yield stream
        copied_files.append(path)

    with monkeypatch.context() as patch:
        patch.setattr(state_files, "regular_reader", edit_earlier_file_during_copy)
        with pytest.raises(ImproperlyConfigured, match="media.*copy failed") as error:
            app_state.prepare_versioned_state(tmp_path, "2.0.0")

    assert "media file changed during copy" in str(error.value.__cause__)
    first, second = copied_files
    after = media.stat()
    assert (after.st_mtime_ns, after.st_ctime_ns) == (before.st_mtime_ns, before.st_ctime_ns)
    assert sorted(p.name for p in old.parent.iterdir()) == [".initialize.lock", "1.0.0"]
    assert app_state.prepare_versioned_state(tmp_path, "1.0.0") == old
    assert first.read_bytes() == edited
    assert second.read_bytes() == original

    copied = app_state.prepare_versioned_state(tmp_path, "2.0.0")
    assert (copied / "media" / first.name).read_bytes() == edited
    assert (copied / "media" / second.name).read_bytes() == original


@pytest.mark.parametrize("legacy", [False, True], ids=["versioned-media", "absent-legacy-media"])
def test_media_change_after_database_backup_refuses_publication(monkeypatch, tmp_path, legacy):
    if legacy:
        old = tmp_path
        with closing(sqlite3.connect(old / "app.sqlite3")) as connection, connection:
            connection.execute("CREATE TABLE sentinel (value TEXT)")
            connection.execute("INSERT INTO sentinel VALUES ('synthetic')")
    else:
        old = previous(tmp_path)
    upload = old / "media" / "upload"
    if not legacy:
        upload.write_bytes(b"synthetic")
        os.utime(upload, (1_600_000_000, 1_600_000_000))
    backup = app_state._copy_database

    def backup_then_commit_attachment_edit(source, destination):
        backup(source, destination)
        with closing(sqlite3.connect(old / "app.sqlite3")) as writer, writer:
            writer.execute("UPDATE sentinel SET value = 'SYNTHETIC'")
            upload.parent.mkdir(exist_ok=True)
            upload.write_bytes(b"SYNTHETIC")

    with monkeypatch.context() as patch:
        patch.setattr(app_state, "_copy_database", backup_then_commit_attachment_edit)
        with pytest.raises(ImproperlyConfigured, match="media"):
            app_state.prepare_versioned_state(tmp_path, "2.0.0")

    state_root = tmp_path / "state"
    assert not (state_root / "2.0.0").exists()
    assert not list(state_root.glob(".dds-stage-*"))
    assert upload.read_bytes() == b"SYNTHETIC"

    copied = app_state.prepare_versioned_state(tmp_path, "2.0.0")
    assert (copied / "media" / "upload").read_bytes() == b"SYNTHETIC"
    with closing(sqlite3.connect(copied / "app.sqlite3")) as reader:
        assert reader.execute("SELECT value FROM sentinel").fetchone() == ("SYNTHETIC",)


def test_valid_nested_media_copies_only_files_and_leaves_cache(tmp_path):
    old = previous(tmp_path)
    (old / "media" / "nested").mkdir()
    (old / "media" / "nested" / "file").write_bytes(b"synthetic\x00")
    (old / "cache" / "discard").write_text("cache")
    state = app_state.prepare_versioned_state(tmp_path, "2.0.0")
    assert (state / "media" / "nested" / "file").read_bytes() == b"synthetic\x00"
    assert list((state / "cache").iterdir()) == []


def test_state_root_swap_does_not_publish_or_clean_external_tree(monkeypatch, tmp_path):
    app = tmp_path / "app"
    previous(app)
    outside = tmp_path / "outside"
    outside.mkdir()
    copy = app_state._copy_state

    def swap_after_copy(source, destination):
        copy(source, destination)
        (app / "state").rename(tmp_path / "saved-state")
        (app / "state").symlink_to(outside, target_is_directory=True)
        # Even a same-name directory outside must never be treated as our stage.
        unrelated = outside / destination.name
        unrelated.mkdir()
        (unrelated / "sentinel").write_text("untouched")

    monkeypatch.setattr(app_state, "_copy_state", swap_after_copy)
    with pytest.raises(ImproperlyConfigured):
        app_state.prepare_versioned_state(app, "2.0.0")
    assert not (outside / "2.0.0").exists()
    sentinels = list(outside.glob("*/sentinel"))
    assert len(sentinels) == 1 and sentinels[0].read_text() == "untouched"


@pytest.mark.parametrize("kind", ["fifo", "hardlink"])
def test_media_special_entries_are_refused(tmp_path, kind):
    old = previous(tmp_path)
    path = old / "media" / "unsafe"
    if kind == "fifo":
        if not hasattr(os, "mkfifo"):
            pytest.skip("POSIX FIFO fixture")
        os.mkfifo(path)
    else:
        external = tmp_path / "synthetic-file"
        external.write_text("keep")
        os.link(external, path)
    with pytest.raises(ImproperlyConfigured, match="media"):
        app_state.prepare_versioned_state(tmp_path, "2.0.0")
    assert not (tmp_path / "state" / "2.0.0").exists()


@pytest.mark.parametrize("mutation", ["rewrite", "restore-mtime", "truncate", "grow", "replace"])
def test_changed_media_generation_never_publishes_and_stable_retry_succeeds(
    monkeypatch, tmp_path, mutation
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    if mutation == "restore-mtime" and os.name == "nt":
        pytest.skip("Windows stat ctime can report creation time rather than change time")

    old = previous(tmp_path)
    media = old / "media" / "upload"
    initial = b"A" * (2 * 1024**2)
    media.write_bytes(initial)
    before = media.stat()
    database_before = (old / "app.sqlite3").read_bytes()
    marker_before = (old / "state.json").read_bytes()
    first_read, changed = Event(), Event()
    read_sizes = []
    real_reader = state_files.regular_reader

    def mutate():
        assert first_read.wait(5), "copy did not reach the first-read barrier"
        try:
            if mutation == "replace":
                replacement = media.with_name("replacement")
                replacement.write_bytes(b"B" * len(initial))
                replacement.replace(media)
            else:
                with media.open("r+b") as writer:
                    if mutation == "truncate":
                        writer.truncate(1024**2)
                    elif mutation == "grow":
                        writer.seek(0, os.SEEK_END)
                        writer.write(b"B" * 1024**2)
                    else:
                        writer.write(b"B" * len(initial))
                if mutation == "restore-mtime":
                    os.utime(media, ns=(before.st_atime_ns, before.st_mtime_ns))
        finally:
            changed.set()

    class BarrierReader:
        def __init__(self, stream):
            self.stream = stream

        def fileno(self):
            return self.stream.fileno()

        def read(self, size):
            read_sizes.append(size)
            chunk = self.stream.read(size)
            if not first_read.is_set():
                first_read.set()
                assert changed.wait(5), "mutation did not finish"
            return chunk

    @contextmanager
    def hooked_reader(path, **kwargs):
        with real_reader(path, **kwargs) as stream:
            yield BarrierReader(stream) if path == media else stream

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(mutate)
        with monkeypatch.context() as patch:
            patch.setattr(state_files, "regular_reader", hooked_reader)
            with pytest.raises(ImproperlyConfigured, match="media"):
                app_state.prepare_versioned_state(tmp_path, "2.0.0")
        future.result(timeout=5)

    assert not (tmp_path / "state" / "2.0.0").exists()
    assert list((tmp_path / "state").glob(".dds-stage-*")) == []
    assert (old / "app.sqlite3").read_bytes() == database_before
    assert (old / "state.json").read_bytes() == marker_before
    assert sum(read_sizes) <= len(initial), "copy must stop at the initial size"
    stable_bytes = media.read_bytes()
    state = app_state.prepare_versioned_state(tmp_path, "2.0.0")
    assert (state / "media" / "upload").read_bytes() == stable_bytes
    assert media.read_bytes() == stable_bytes
