import json
import sqlite3
from pathlib import Path

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
