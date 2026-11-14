"""Serialized initialization, bounded abandoned-stage recovery and sync barriers."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import stat
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .state_files import admit, directory_guard, identity, regular_reader, state_error

logger = logging.getLogger(__name__)
LOCK_FILENAME = ".initialize.lock"
STAGE_PREFIX = ".dds-stage-"
OWNER_FILENAME = ".stage-owner.json"
STAGE_PATTERN = re.compile(r"\.dds-stage-[0-9a-f]{32}\Z")
LOCK_TIMEOUT_SECONDS = 30.0
MAX_DISCOVERY_ENTRIES = 1024
MAX_RECOVERY_STAGES = 16
MAX_RECOVERY_ENTRIES = 100_016
MAX_RECOVERY_DEPTH = 65


@contextmanager
def initialization_lock(root: Path) -> Iterator[None]:
    """A persistent inode, held throughout recovery/copy/publication on all versions."""
    path = root / LOCK_FILENAME
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    # Refuse existing reparse points before the Windows conservative open.
    if os.path.lexists(path):
        admit(path)
    descriptor = os.open(path, flags, 0o600)
    locked = False
    try:
        before = admit(path)
        if identity(before) != identity(os.fstat(descriptor)):
            raise state_error("initialization lock changed")
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
                else:
                    import fcntl

                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except (BlockingIOError, PermissionError):
                if time.monotonic() >= deadline:
                    raise state_error("initialization busy; close other app processes and retry")
                time.sleep(0.05)
        if identity(admit(path)) != identity(before):
            raise state_error("initialization lock replaced while waiting")
        # Windows permits byte-range locks beyond EOF. Initialize the persistent
        # byte only after locking, so two first-open callers cannot race a write.
        if os.fstat(descriptor).st_size == 0:
            os.lseek(descriptor, 0, os.SEEK_SET)
            os.write(descriptor, b"0")
        yield
    finally:
        if locked:
            if os.name == "nt":
                import msvcrt

                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def sync_file(path: Path) -> None:
    if os.name == "nt":
        before = admit(path)
        descriptor = os.open(path, os.O_RDWR | getattr(os, "O_BINARY", 0))
        try:
            if identity(os.fstat(descriptor)) != identity(before):
                raise state_error("owned sync file changed")
            os.fsync(descriptor)
            if identity(admit(path)) != identity(before):
                raise state_error("owned sync file changed")
        finally:
            os.close(descriptor)
        return
    with regular_reader(path) as stream:
        os.fsync(stream.fileno())
        # macOS additionally asks the device to flush its write cache.
        if sys.platform == "darwin":
            import fcntl

            fcntl.fcntl(stream.fileno(), fcntl.F_FULLFSYNC)


def sync_directory(path: Path) -> None:
    # Python exposes no portable Windows directory FlushFileBuffers handle.
    if os.name != "nt":
        with directory_guard(path) as descriptor:
            assert descriptor is not None
            os.fsync(descriptor)


def sync_tree(root: Path) -> None:
    """Owned, already bounded payload; sync directories after their children."""
    with directory_guard(root):
        with os.scandir(root) as entries:
            for entry in entries:
                path = root / entry.name
                if stat.S_ISDIR(path.lstat().st_mode):
                    sync_tree(path)
                else:
                    sync_file(path)
        sync_directory(root)


def _validate_cleanup_tree(root: Path) -> None:
    count = 0

    def walk(path: Path, depth: int) -> None:
        nonlocal count
        if depth > MAX_RECOVERY_DEPTH:
            raise state_error("abandoned stage depth exceeds recovery budget")
        with directory_guard(path):
            with os.scandir(path) as entries:
                for entry in entries:
                    count += 1
                    if count > MAX_RECOVERY_ENTRIES:
                        raise state_error("abandoned stage exceeds recovery entry budget")
                    child = path / entry.name
                    if stat.S_ISDIR(child.lstat().st_mode):
                        walk(child, depth + 1)
                    else:
                        admit(child)

    walk(root, 0)


def recover_stages(root: Path) -> None:
    """Only under the persistent global lock; a live initializer cannot own a stage."""
    candidates = []
    with os.scandir(root) as entries:
        for count, entry in enumerate(entries, 1):
            if count > MAX_DISCOVERY_ENTRIES:
                raise state_error("state discovery exceeds 1024 entries; inspect retained stages")
            if STAGE_PATTERN.fullmatch(entry.name):
                candidates.append(root / entry.name)
                if len(candidates) > MAX_RECOVERY_STAGES:
                    raise state_error("more than 16 stages; inspect retained stages before retry")
    ambiguous = 0
    for stage in candidates:
        try:
            with directory_guard(stage):
                with regular_reader(stage / OWNER_FILENAME) as stream:
                    raw = stream.read(4097)
                owner = json.loads(raw)
                if (
                    len(raw) > 4096
                    or not isinstance(owner, dict)
                    or type(owner.get("schema")) is not int
                    or owner
                    != {"schema": 1, "stage": stage.name, "kind": "dds-state-initialization"}
                ):
                    raise ValueError("unknown owner")
                if any(
                    child.name
                    not in {
                        OWNER_FILENAME,
                        "app.sqlite3",
                        "app.sqlite3-journal",
                        "app.sqlite3-wal",
                        "app.sqlite3-shm",
                        "media",
                        "cache",
                        "state.json",
                    }
                    for child in stage.iterdir()
                ):
                    raise ValueError("unknown stage contents")
                _validate_cleanup_tree(stage)
            shutil.rmtree(stage)
        except (OSError, ValueError, TypeError, RecursionError, ImproperlyConfigured) as error:
            # Refuse to guess ownership; keep ambiguous bytes for manual inspection.
            logger.warning("Retained ambiguous abandoned state stage (%s)", type(error).__name__)
            ambiguous += 1
    if ambiguous:
        logger.warning("Retained %d ambiguous stages; inspect while the app is closed", ambiguous)
    if candidates:
        sync_directory(root)
