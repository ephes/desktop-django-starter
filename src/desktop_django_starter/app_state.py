"""Version-isolated local state for the packaged desktop runtime.

Each app version keeps its database, media and cache in its own directory:

    <app-data>/state/<version>/app.sqlite3
    <app-data>/state/<version>/media/
    <app-data>/state/<version>/cache/

When a version starts for the first time, its directory is created from the
newest *older* version's state (or from the pre-versioning ``app.sqlite3`` in
the app-data root), so an upgrade keeps the user's data and then runs its own
migrations on the copy. The previous version's directory is left untouched,
so rolling back to it finds its data and schema exactly as it left them. State
is never imported from a newer version, because its migrations are unknown to
the older code.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

STATE_DIRNAME = "state"
DATABASE_FILENAME = "app.sqlite3"
MEDIA_DIRNAME = "media"
CACHE_DIRNAME = "cache"
STATE_METADATA_FILENAME = "state.json"
LEGACY_DATABASE_FILENAME = "app.sqlite3"
UNVERSIONED = "unversioned"

_UNSAFE_VERSION_CHARACTERS = re.compile(r"[^0-9A-Za-z.+_-]")


def state_dir_name(version: str) -> str:
    """Return a filesystem-safe directory name for an app version."""
    cleaned = _UNSAFE_VERSION_CHARACTERS.sub("_", version.strip()).strip(".")
    return cleaned or UNVERSIONED


def version_sort_key(version: str) -> tuple[tuple[int, int | str], ...]:
    """Order versions like 0.1.9 < 0.1.10; non-numeric parts sort after numbers."""
    parts = re.split(r"[.+_-]", version)
    return tuple((0, int(part)) if part.isdigit() else (1, part) for part in parts if part)


def prepare_versioned_state(app_data_dir: Path, version: str) -> Path:
    """Return this version's state directory, creating it on first use."""
    state_root = app_data_dir / STATE_DIRNAME
    state_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    current_name = state_dir_name(version)
    state_dir = state_root / current_name
    if state_dir.is_dir():
        return state_dir

    source, source_label = _find_previous_state(app_data_dir, state_root, current_name)
    staging = Path(tempfile.mkdtemp(prefix=f".{current_name}-", dir=state_root))
    try:
        if source is not None:
            _copy_state(source, staging)
        (staging / MEDIA_DIRNAME).mkdir(exist_ok=True)
        (staging / CACHE_DIRNAME).mkdir(exist_ok=True)
        metadata = {
            "version": version,
            "created_at": datetime.now(UTC).isoformat(),
            "copied_from": source_label,
        }
        (staging / STATE_METADATA_FILENAME).write_text(json.dumps(metadata, indent=2) + "\n")
        try:
            staging.rename(state_dir)
        except OSError:
            # Another process created it first; use theirs.
            if not state_dir.is_dir():
                raise
            shutil.rmtree(staging, ignore_errors=True)
            return state_dir
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    if source_label is None:
        logger.info("Created empty app state for version %s at %s", version, state_dir)
    else:
        logger.info(
            "Created app state for version %s from %s at %s", version, source_label, state_dir
        )
    return state_dir


def _find_previous_state(
    app_data_dir: Path, state_root: Path, current_name: str
) -> tuple[Path | None, str | None]:
    current_key = version_sort_key(current_name)
    older = [
        entry
        for entry in state_root.iterdir()
        if entry.is_dir()
        and not entry.name.startswith(".")
        and entry.name != current_name
        and (entry / DATABASE_FILENAME).is_file()
        and version_sort_key(entry.name) < current_key
    ]
    if older:
        newest = max(older, key=lambda entry: version_sort_key(entry.name))
        return newest, newest.name

    legacy_database = app_data_dir / LEGACY_DATABASE_FILENAME
    if legacy_database.is_file():
        return app_data_dir, "legacy"

    newer = [
        entry.name
        for entry in state_root.iterdir()
        if entry.is_dir() and not entry.name.startswith(".")
    ]
    if newer:
        logger.warning(
            "No state from an older version found; starting version %s empty. "
            "State of newer versions (%s) is kept but not imported.",
            current_name,
            ", ".join(sorted(newer)),
        )
    return None, None


def _copy_state(source: Path, destination: Path) -> None:
    # The backup API copies a consistent snapshot, including pages that are
    # still only in the -wal file after an unclean shutdown.
    source_database = sqlite3.connect(source / DATABASE_FILENAME)
    try:
        target_database = sqlite3.connect(destination / DATABASE_FILENAME)
        try:
            source_database.backup(target_database)
        finally:
            target_database.close()
    finally:
        source_database.close()

    source_media = source / MEDIA_DIRNAME
    if source_media.is_dir():
        shutil.copytree(source_media, destination / MEDIA_DIRNAME)
    # The cache is not copied: it is disposable and may hold version-specific data.
    if os.name != "nt":
        destination.chmod(0o700)
