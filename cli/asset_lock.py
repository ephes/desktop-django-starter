"""Coordinate staged asset publication and build snapshots."""

import os
import re
import shutil
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

ASSET_MARKER = ".assets-sync-pending"


def directory_identity(path: Path) -> str | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISDIR(info.st_mode) or (
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    ):
        raise RuntimeError(f"Expected an asset directory at {path}")
    return f"{info.st_dev}:{info.st_ino}"


def mark_asset_replacement(assets: Path, work: Path) -> None:
    """Record the two exact generations before moving either directory."""
    marker = work / "pending"
    record = (
        f"{work.name} {directory_identity(work)} {directory_identity(assets)} "
        f"{directory_identity(work / 'staged')}\n"
    )
    marker.write_bytes(record.encode("ascii"))
    marker.replace(assets.parent / ASSET_MARKER)


def recover_asset_replacement(assets: Path) -> None:
    """Reconcile a pending publication while the caller holds the asset lock."""
    marker = assets.parent / ASSET_MARKER
    try:
        info = marker.lstat()
    except FileNotFoundError:
        return
    error = f"Cannot reconcile pending asset replacement. Inspect {marker} with builds stopped."
    if not stat.S_ISREG(info.st_mode) or (
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    ):
        raise RuntimeError(error)
    with marker.open("rb") as pending:
        record = pending.read(256)
    match = re.fullmatch(
        rb"(\.assets-sync-[a-z0-9_]{8,32}) ([0-9]+:[0-9]+) ([0-9]+:[0-9]+) ([0-9]+:[0-9]+)\n",
        record,
    )
    if match is None or len(record) == 256:
        raise RuntimeError(error)
    work_name, work_id, previous_id, staged_id = (group.decode("ascii") for group in match.groups())
    work = assets.parent / work_name
    if directory_identity(work) != work_id or directory_identity(work / "staged") not in (
        None,
        staged_id,
    ):
        raise RuntimeError(error)
    backup = work / "previous"
    backup_id = directory_identity(backup)
    current_id = directory_identity(assets)
    if backup_id == previous_id and current_id is None:
        backup.rename(assets)
    elif (backup_id, current_id) not in {(None, previous_id), (previous_id, staged_id)}:
        raise RuntimeError(error)
    marker.unlink()
    shutil.rmtree(work)


@contextmanager
def asset_lock(package_dir: Path) -> Iterator[None]:
    # Keep the same lock file across runs, including while a publisher waits.
    # On POSIX, closing the handle releases the lock. Windows unlocks explicitly
    # because the CRT may release leftover locks only after a delay.
    with (package_dir / ".assets-sync-lock").open("a+b") as lock:
        if os.name == "nt":
            import msvcrt

            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            yield
