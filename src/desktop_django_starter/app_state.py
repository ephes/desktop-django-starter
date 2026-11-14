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
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePath
from urllib.parse import quote

from django.core.exceptions import ImproperlyConfigured
from packaging.version import Version as PythonVersion
from semver import Version

from .state_files import (
    admit,
    copy_media,
    directory_guard,
    identity,
    optional_file,
    regular_reader,
    state_error,
)
from .state_staging import (
    OWNER_FILENAME,
    STAGE_PREFIX,
    initialization_lock,
    recover_stages,
    sync_directory,
    sync_file,
    sync_tree,
)

logger = logging.getLogger(__name__)

STATE_DIRNAME = "state"
DATABASE_FILENAME = "app.sqlite3"
MEDIA_DIRNAME = "media"
CACHE_DIRNAME = "cache"
STATE_METADATA_FILENAME = "state.json"
LEGACY_DATABASE_FILENAME = "app.sqlite3"
UNVERSIONED = "unversioned"
BACKUP_TIMEOUT_SECONDS = 30.0

_UNSAFE_VERSION_CHARACTERS = re.compile(r"[^0-9A-Za-z.+_-]")


def state_dir_name(version: str) -> str:
    """Return a filesystem-safe directory name for an app version."""
    cleaned = _UNSAFE_VERSION_CHARACTERS.sub("_", version.strip()).strip(".")
    return cleaned or UNVERSIONED


def version_sort_key(version: str) -> Version:
    """Parse release ordering separately from filesystem directory naming.

    Unsupported versions stop startup rather than guessing a predecessor.
    """
    try:
        return Version.parse(version)
    except ValueError as error:
        # Positron metadata normalizes prereleases to canonical PEP 440 spelling.
        # Allow only the three release-prerelease forms with direct SemVer peers.
        if re.fullmatch(
            r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:a|b|rc)(?:0|[1-9][0-9]*)",
            version,
        ):
            parsed = PythonVersion(version)
            assert parsed.pre is not None
            label, number = parsed.pre
            prerelease = f"{dict(a='alpha', b='beta', rc='rc')[label]}.{number}"
            return Version(parsed.major, parsed.minor, parsed.micro, prerelease=prerelease)
        raise ImproperlyConfigured(
            f"Unsupported app state version {version!r}; expected SemVer "
            "or a canonical Python a/b/rc prerelease. "
            "Check the build version or move the unsupported state directory aside "
            "while the app is closed, keeping a backup."
        ) from error


def _validate_state(state_dir: Path, version: str) -> None:
    """Admit the existing marker format, including deliberately empty first use."""
    try:
        with directory_guard(state_dir):
            with regular_reader(state_dir / STATE_METADATA_FILENAME) as stream:
                raw = stream.read(16_385)
            if len(raw) > 16_384:
                raise ValueError("marker exceeds 16 KiB")
            metadata = json.loads(raw)
            if not isinstance(metadata, dict) or metadata.get("version") != version:
                raise ValueError("marker version mismatch")
            created = datetime.fromisoformat(metadata["created_at"])
            if created.tzinfo is None or "copied_from" not in metadata:
                raise ValueError("incomplete marker")
            copied = metadata["copied_from"]
            if copied is not None and (
                not isinstance(copied, str)
                or (copied != "legacy" and version_sort_key(copied) >= version_sort_key(version))
            ):
                raise ValueError("invalid predecessor")
            for name in (MEDIA_DIRNAME, CACHE_DIRNAME):
                admit(state_dir / name, directory=True)
            has_database = optional_file(state_dir / DATABASE_FILENAME)
            if copied is not None and not has_database:
                raise ValueError("copied database missing")
            for suffix in ("-wal", "-shm", "-journal"):
                optional_file(state_dir / (DATABASE_FILENAME + suffix))
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as error:
        raise state_error("invalid state completion marker or layout") from error


def prepare_versioned_state(app_data_dir: Path, version: str) -> Path:
    """Return only an admitted complete generation, preserving failed restores."""
    if version != UNVERSIONED:
        version_sort_key(version)
    app_data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        with directory_guard(app_data_dir):
            state_root = app_data_dir / STATE_DIRNAME
            state_root.mkdir(mode=0o700, exist_ok=True)
            with directory_guard(state_root), initialization_lock(state_root):
                roots = [
                    (path, identity(admit(path, directory=True)))
                    for path in (app_data_dir, state_root)
                ]
                recover_stages(state_root)
                return _prepare_state(app_data_dir, state_root, version, roots)
    except OSError as error:
        raise state_error("state path admission or initialization failed") from error


def _prepare_state(
    app_data_dir: Path,
    state_root: Path,
    version: str,
    roots: list[tuple[Path, tuple[int, int]]],
) -> Path:
    current_name = state_dir_name(version)
    state_dir = state_root / current_name
    if os.path.lexists(state_dir):
        _validate_state(state_dir, version)
        return state_dir

    source, source_label = _find_previous_state(app_data_dir, state_root, current_name)
    staging = state_root / (STAGE_PREFIX + uuid.uuid4().hex)
    _check_roots(roots)
    staging.mkdir(mode=0o700)
    staging_identity = identity(admit(staging, directory=True))
    published = False
    try:
        (staging / OWNER_FILENAME).write_text(
            json.dumps(
                {
                    "schema": 1,
                    "stage": staging.name,
                    "kind": "dds-state-initialization",
                }
            )
        )
        sync_file(staging / OWNER_FILENAME)
        sync_directory(staging)
        sync_directory(state_root)
        if source is not None:
            _copy_state(source, staging)
        (staging / MEDIA_DIRNAME).mkdir(exist_ok=True)
        (staging / CACHE_DIRNAME).mkdir(exist_ok=True)
        metadata = {
            "version": version,
            "created_at": datetime.now(UTC).isoformat(),
            "copied_from": source_label,
        }
        _check_roots(roots)
        sync_tree(staging)
        (staging / STATE_METADATA_FILENAME).write_text(json.dumps(metadata, indent=2) + "\n")
        sync_file(staging / STATE_METADATA_FILENAME)
        sync_directory(staging)
        _check_roots(roots)
        # Cooperating callers hold the same persistent lock; no winner can be replaced.
        if os.path.lexists(state_dir):
            raise state_error("unexpected concurrent version directory; retained for repair")
        staging.rename(state_dir)
        published = True
        try:
            sync_directory(state_root)
        except OSError as error:
            raise state_error(
                "publication is visible but durability is uncertain; retain both generations"
            ) from error
        _validate_state(state_dir, version)
    except BaseException:
        if not published:
            try:
                _check_roots(roots)
                if identity(admit(staging, directory=True)) != staging_identity:
                    raise state_error("staging directory changed before cleanup")
                shutil.rmtree(staging)
            except (OSError, ImproperlyConfigured):
                logger.warning("Unpublished state stage retained for safe recovery")
        raise
    logger.info("Created app state for version %s from %s", version, source_label)
    return state_dir


def _check_roots(roots: list[tuple[Path, tuple[int, int]]]) -> None:
    for path, expected in roots:
        if identity(admit(path, directory=True)) != expected:
            raise state_error("state root changed before publication")


def _find_previous_state(
    app_data_dir: Path, state_root: Path, current_name: str
) -> tuple[Path | None, str | None]:
    current_key = None if current_name == UNVERSIONED else version_sort_key(current_name)
    older = []
    for entry in state_root.iterdir():
        if entry.name.startswith(".") or entry.name in {current_name, UNVERSIONED}:
            continue
        # Do not let a link disguise itself as either a release or its database.
        admit(entry, directory=True)
        if current_key is None:
            continue
        key = version_sort_key(entry.name)
        if key < current_key:
            _validate_state(entry, entry.name)
            if optional_file(entry / DATABASE_FILENAME):
                older.append(entry)

    if older:
        newest = max(older, key=lambda entry: (version_sort_key(entry.name), entry.name))
        return newest, newest.name

    legacy_database = app_data_dir / LEGACY_DATABASE_FILENAME
    if optional_file(legacy_database):
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


def _readonly_database_uri(database: PurePath) -> str:
    """Encode local/UNC paths without a SQLite URI hostname authority."""
    pathname = database.as_posix()
    if pathname[:8].upper() == "//?/UNC/":
        pathname = "//" + pathname[8:]
    elif pathname.startswith("//?/"):
        pathname = pathname[4:]
    prefix = "file://" if pathname.startswith("//") else "file:///"
    encoded = quote(pathname if pathname.startswith("//") else pathname.lstrip("/"), safe="/:")
    return prefix + encoded + "?mode=ro"


def _copy_state(source: Path, destination: Path) -> None:
    with directory_guard(source), directory_guard(destination):
        with regular_reader(source / DATABASE_FILENAME):
            for suffix in ("-wal", "-shm", "-journal"):
                optional_file(source / (DATABASE_FILENAME + suffix))
            _copy_database(source, destination)
        source_media = source / MEDIA_DIRNAME
        if os.path.lexists(source_media):
            copy_media(source_media, destination / MEDIA_DIRNAME)


def _copy_database(source: Path, destination: Path) -> None:
    # The backup API copies a consistent snapshot, including pages that are
    # still only in the -wal file after an unclean shutdown.
    deadline = time.monotonic() + BACKUP_TIMEOUT_SECONDS

    def check_deadline(status: int, remaining: int, total: int) -> None:
        if time.monotonic() >= deadline:
            raise ImproperlyConfigured(
                "Timed out copying the previous app database within the startup budget. "
                "Close other app processes and retry startup; the previous state has been "
                "kept. If the copy is too large or slow, seek support to increase the "
                "backup budget before retrying."
            )

    source_uri = _readonly_database_uri((source / DATABASE_FILENAME).absolute())
    source_database = sqlite3.connect(source_uri, uri=True, timeout=0.1)
    try:
        target_database = sqlite3.connect(destination / DATABASE_FILENAME)
        try:
            source_database.backup(target_database, pages=128, progress=check_deadline, sleep=0.05)
        finally:
            target_database.close()
    finally:
        source_database.close()
