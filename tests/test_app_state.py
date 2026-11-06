import json
import shutil
import sqlite3
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

from desktop_django_starter.app_state import (
    prepare_versioned_state,
    state_dir_name,
    version_sort_key,
)


def make_database(path: Path, value: str, *, keep_open: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE IF NOT EXISTS marker (value TEXT)")
    connection.execute("INSERT INTO marker VALUES (?)", (value,))
    connection.commit()
    if keep_open:
        return connection
    connection.close()
    return None


def read_markers(path: Path) -> list[str]:
    connection = sqlite3.connect(path)
    try:
        return [row[0] for row in connection.execute("SELECT value FROM marker")]
    finally:
        connection.close()


def metadata(state_dir: Path) -> dict:
    return json.loads((state_dir / "state.json").read_text())


def test_first_install_creates_empty_state(tmp_path: Path) -> None:
    state_dir = prepare_versioned_state(tmp_path, "0.2.0")

    assert state_dir == tmp_path / "state" / "0.2.0"
    assert (state_dir / "media").is_dir()
    assert (state_dir / "cache").is_dir()
    assert not (state_dir / "app.sqlite3").exists()
    assert metadata(state_dir)["copied_from"] is None


def test_upgrade_from_pre_versioning_layout_copies_legacy_database(tmp_path: Path) -> None:
    # An open connection keeps the latest row in the -wal file only.
    open_connection = make_database(tmp_path / "app.sqlite3", "legacy", keep_open=True)
    try:
        state_dir = prepare_versioned_state(tmp_path, "0.2.0")
    finally:
        open_connection.close()

    assert read_markers(state_dir / "app.sqlite3") == ["legacy"]
    assert metadata(state_dir)["copied_from"] == "legacy"
    # The legacy file stays so an older release can still use it.
    assert (tmp_path / "app.sqlite3").is_file()


def test_upgrade_copies_newest_older_version_and_leaves_it_untouched(tmp_path: Path) -> None:
    make_database(tmp_path / "state" / "0.1.9" / "app.sqlite3", "v0.1.9")
    make_database(tmp_path / "state" / "0.1.10" / "app.sqlite3", "v0.1.10")
    (tmp_path / "state" / "0.1.10" / "media").mkdir()
    (tmp_path / "state" / "0.1.10" / "media" / "upload.txt").write_text("file")
    make_database(tmp_path / "app.sqlite3", "legacy")

    state_dir = prepare_versioned_state(tmp_path, "0.2.0")

    assert read_markers(state_dir / "app.sqlite3") == ["v0.1.10"]
    assert (state_dir / "media" / "upload.txt").read_text() == "file"
    assert metadata(state_dir)["copied_from"] == "0.1.10"

    make_database(state_dir / "app.sqlite3", "written by 0.2.0")
    assert read_markers(tmp_path / "state" / "0.1.10" / "app.sqlite3") == ["v0.1.10"]


def test_existing_state_is_reused_without_copying_again(tmp_path: Path) -> None:
    make_database(tmp_path / "state" / "0.1.0" / "app.sqlite3", "old")
    first = prepare_versioned_state(tmp_path, "0.2.0")
    make_database(first / "app.sqlite3", "new data")

    second = prepare_versioned_state(tmp_path, "0.2.0")

    assert second == first
    assert read_markers(second / "app.sqlite3") == ["old", "new data"]


def test_rollback_never_imports_state_from_a_newer_version(tmp_path: Path) -> None:
    make_database(tmp_path / "state" / "0.3.0" / "app.sqlite3", "from the future")

    state_dir = prepare_versioned_state(tmp_path, "0.2.0")

    assert not (state_dir / "app.sqlite3").exists()
    assert metadata(state_dir)["copied_from"] is None


def test_rollback_reuses_the_older_versions_own_state(tmp_path: Path) -> None:
    older = prepare_versioned_state(tmp_path, "0.1.0")
    make_database(older / "app.sqlite3", "0.1.0 data")
    newer = prepare_versioned_state(tmp_path, "0.2.0")
    make_database(newer / "app.sqlite3", "0.2.0 data")

    rolled_back = prepare_versioned_state(tmp_path, "0.1.0")

    assert rolled_back == older
    assert read_markers(rolled_back / "app.sqlite3") == ["0.1.0 data"]


def test_version_names_are_sanitized_and_ordered_numerically() -> None:
    assert state_dir_name("1.2.3") == "1.2.3"
    assert state_dir_name("../evil") == "_evil"
    assert state_dir_name("") == "unversioned"
    assert version_sort_key("0.1.9") < version_sort_key("0.1.10")
    assert version_sort_key("0.1.10") < version_sort_key("0.2.0")


def test_stable_upgrade_inherits_latest_release_candidate(tmp_path: Path) -> None:
    make_database(tmp_path / "state" / "0.1.9" / "app.sqlite3", "old")
    make_database(tmp_path / "state" / "0.2.0-rc.2" / "app.sqlite3", "rc2")
    make_database(tmp_path / "state" / "0.2.0-rc.10" / "app.sqlite3", "rc10")
    state_dir = prepare_versioned_state(tmp_path, "0.2.0")
    assert read_markers(state_dir / "app.sqlite3") == ["rc10"]
    assert metadata(state_dir)["copied_from"] == "0.2.0-rc.10"


def test_prerelease_rollback_does_not_import_stable(tmp_path: Path) -> None:
    make_database(tmp_path / "state" / "0.2.0" / "app.sqlite3", "stable")
    state_dir = prepare_versioned_state(tmp_path, "0.2.0-rc.1")
    assert not (state_dir / "app.sqlite3").exists()


def test_unsupported_version_is_refused_before_creating_state(tmp_path: Path) -> None:
    with pytest.raises(ImproperlyConfigured, match="expected SemVer"):
        prepare_versioned_state(tmp_path, "../evil")
    assert not (tmp_path / "state").exists()


def test_locked_backup_has_deadline_and_can_retry(tmp_path: Path) -> None:
    import subprocess
    import sys

    source = tmp_path / "state" / "0.1.0" / "app.sqlite3"
    make_database(source, "locked")
    connection = sqlite3.connect(source)
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.execute("BEGIN EXCLUSIVE")
    script = """
import sys
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from desktop_django_starter import app_state
app_state.BACKUP_TIMEOUT_SECONDS = 0.1
try:
    app_state.prepare_versioned_state(Path(sys.argv[1]), '0.2.0')
except ImproperlyConfigured as error:
    assert 'retry' in str(error).lower()
else:
    raise AssertionError('Locked backup unexpectedly succeeded')
"""
    try:
        subprocess.run([sys.executable, "-c", script, str(tmp_path)], check=True, timeout=5)
        assert sorted(p.name for p in (tmp_path / "state").iterdir()) == ["0.1.0"]
    finally:
        connection.rollback()
        connection.close()
    state_dir = prepare_versioned_state(tmp_path, "0.2.0")
    assert read_markers(state_dir / "app.sqlite3") == ["locked"]


def test_unversioned_state_is_not_ordered_as_a_release(tmp_path: Path) -> None:
    make_database(tmp_path / "state" / "unversioned" / "app.sqlite3", "unversioned")
    stable = prepare_versioned_state(tmp_path, "0.2.0")
    assert not (stable / "app.sqlite3").exists()
    make_database(stable / "app.sqlite3", "stable")
    shutil.rmtree(tmp_path / "state" / "unversioned")
    unversioned = prepare_versioned_state(tmp_path, "unversioned")
    assert not (unversioned / "app.sqlite3").exists()


@pytest.mark.parametrize("version", ["1.0.0-1", "1.0.0-nightly.1", "1.0.0-alpha.beta"])
def test_semver_prereleases_are_older_than_stable(tmp_path: Path, version: str) -> None:
    make_database(tmp_path / "state" / version / "app.sqlite3", version)
    state = prepare_versioned_state(tmp_path, "1.0.0")
    assert read_markers(state / "app.sqlite3") == [version]
    assert version_sort_key(version) < version_sort_key("1.0.0")


def test_unsupported_candidate_has_recovery_diagnostic(tmp_path: Path) -> None:
    make_database(tmp_path / "state" / "unsupported" / "app.sqlite3", "untouched")
    with pytest.raises(ImproperlyConfigured, match="unsupported.*expected SemVer"):
        prepare_versioned_state(tmp_path, "1.0.0")
    assert sorted(p.name for p in (tmp_path / "state").iterdir()) == ["unsupported"]


@pytest.mark.parametrize("version", ["0.2.0a1", "0.2.0b2", "0.2.0rc10"])
def test_positron_prerelease_state_upgrades_to_stable(tmp_path: Path, version: str) -> None:
    make_database(tmp_path / "state" / version / "app.sqlite3", version)
    stable = prepare_versioned_state(tmp_path, "0.2.0")
    assert read_markers(stable / "app.sqlite3") == [version]
    assert version_sort_key("0.2.0a1") < version_sort_key("0.2.0b1")
    assert version_sort_key("0.2.0b1") < version_sort_key("0.2.0rc1")
    assert version_sort_key("0.2.0rc1") == version_sort_key("0.2.0-rc.1")


@pytest.mark.parametrize("version", ["0.2.0.dev1", "0.2.0.post1", "1!0.2.0", "0.2.0a01"])
def test_unsupported_python_version_forms_are_refused(tmp_path: Path, version: str) -> None:
    with pytest.raises(ImproperlyConfigured, match="Unsupported app state version"):
        prepare_versioned_state(tmp_path, version)
    assert not (tmp_path / "state").exists()


@pytest.mark.parametrize("names", [("0.2.0rc1", "0.2.0-rc.1"), ("0.2.0-rc.1", "0.2.0rc1")])
def test_equivalent_predecessors_have_deterministic_tie_break(tmp_path: Path, names) -> None:
    for name in names:
        make_database(tmp_path / "state" / name / "app.sqlite3", name)
    stable = prepare_versioned_state(tmp_path, "0.2.0")
    assert read_markers(stable / "app.sqlite3") == ["0.2.0rc1"]


def test_disappeared_source_is_not_recreated(monkeypatch, tmp_path: Path) -> None:
    from desktop_django_starter import app_state

    source = tmp_path / "state" / "0.1.0" / "app.sqlite3"
    make_database(source, "previous")
    real_copy = app_state._copy_state

    def remove_then_copy(source_dir, destination):
        source.unlink()
        real_copy(source_dir, destination)

    monkeypatch.setattr(app_state, "_copy_state", remove_then_copy)
    with pytest.raises(sqlite3.OperationalError):
        prepare_versioned_state(tmp_path, "0.2.0")
    assert not source.exists()
    assert sorted(p.name for p in (tmp_path / "state").iterdir()) == ["0.1.0"]


def test_invalid_source_publishes_nothing(tmp_path: Path) -> None:
    source = tmp_path / "state" / "0.1.0" / "app.sqlite3"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"invalid database")
    with pytest.raises(sqlite3.DatabaseError):
        prepare_versioned_state(tmp_path, "0.2.0")
    assert source.read_bytes() == b"invalid database"
    assert sorted(p.name for p in (tmp_path / "state").iterdir()) == ["0.1.0"]


def test_source_uri_escapes_path_and_keeps_wal(tmp_path: Path) -> None:
    # Use names legal on every OS; '?' escaping is covered by PureWindowsPath fixtures.
    app_data = tmp_path / "space # % unicode-é"
    source = app_data / "state" / "0.1.0" / "app.sqlite3"
    connection = make_database(source, "wal", keep_open=True)
    try:
        state = prepare_versioned_state(app_data, "0.2.0")
    finally:
        connection.close()
    assert read_markers(state / "app.sqlite3") == ["wal"]
    assert read_markers(source) == ["wal"]


@pytest.mark.parametrize(
    ("pathname", "expected"),
    [
        (
            r"C:\Users\synthetic user\a?#%.sqlite3",
            "file:///C:/Users/synthetic%20user/a%3F%23%25.sqlite3?mode=ro",
        ),
        (
            r"\\server\share\synthetic user\app.sqlite3",
            "file:////server/share/synthetic%20user/app.sqlite3?mode=ro",
        ),
        (r"\\?\UNC\server\share\app.sqlite3", "file:////server/share/app.sqlite3?mode=ro"),
        (r"\\?\C:\synthetic user\app.sqlite3", "file:///C:/synthetic%20user/app.sqlite3?mode=ro"),
    ],
)
def test_readonly_uri_handles_windows_paths_on_every_platform(pathname, expected) -> None:
    from pathlib import PureWindowsPath

    from desktop_django_starter.app_state import _readonly_database_uri

    assert _readonly_database_uri(PureWindowsPath(pathname)) == expected


def test_readonly_uri_handles_lowercase_extended_unc() -> None:
    from pathlib import PureWindowsPath

    from desktop_django_starter.app_state import _readonly_database_uri

    assert _readonly_database_uri(PureWindowsPath(r"\\?\unc\server\share\app.sqlite3")) == (
        "file:////server/share/app.sqlite3?mode=ro"
    )
