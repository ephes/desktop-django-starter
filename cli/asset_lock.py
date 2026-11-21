"""Coordinate staged asset publication and build snapshots."""

import os
import re
import shutil
import stat
import sys
import warnings
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


def sync_descriptor(fd: int, path: Path) -> None:
    try:
        os.fsync(fd)
        if sys.platform == "darwin":
            import fcntl

            fcntl.fcntl(fd, fcntl.F_FULLFSYNC)
    except OSError as error:
        raise OSError(f"Cannot sync packaged asset path {path}: {error}") from error


def sync_directory(path: Path) -> None:
    if os.name == "nt":
        warnings.warn(
            "Packaged asset directory sync is unavailable on Windows. "
            "Power-loss recovery of directory renames is not guaranteed.",
            RuntimeWarning,
        )
        return
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        sync_descriptor(fd, path)
    finally:
        os.close(fd)


def sync_staged_assets(root: Path) -> None:
    """Flush the private staged tree from the files up to its root."""
    for path in root.iterdir():
        if path.is_dir():
            sync_staged_assets(path)
        elif os.name == "nt":
            # Windows needs a writable handle for fsync, but copy2 keeps the
            # read-only attribute of the source. Restore it after the flush.
            mode = stat.S_IMODE(path.stat().st_mode)
            if not mode & stat.S_IWRITE:
                path.chmod(mode | stat.S_IWRITE)
            try:
                with path.open("r+b") as handle:
                    sync_descriptor(handle.fileno(), path)
            finally:
                if not mode & stat.S_IWRITE:
                    path.chmod(mode)
        else:
            with path.open("rb") as handle:
                sync_descriptor(handle.fileno(), path)
    sync_directory(root)


def mark_asset_replacement(assets: Path, work: Path) -> None:
    """Record the two exact generations before moving either directory."""
    marker = work / "pending"
    record = (
        f"{work.name} {directory_identity(work)} {directory_identity(assets)} "
        f"{directory_identity(work / 'staged')}\n"
    )
    with marker.open("wb") as handle:
        handle.write(record.encode("ascii"))
        handle.flush()
        sync_descriptor(handle.fileno(), marker)
    marker.replace(assets.parent / ASSET_MARKER)


def retire_asset_replacement(assets: Path, work: Path) -> None:
    """Make the selected generation and then journal removal durable."""
    package = assets.parent
    sync_directory(package)
    sync_directory(work)
    (package / ASSET_MARKER).unlink()
    # If the unlink is lost on restart, recovery still needs the work tree.
    sync_directory(package)


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
    retire_asset_replacement(assets, work)
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
