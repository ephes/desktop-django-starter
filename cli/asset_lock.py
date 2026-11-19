"""Coordinate staged asset publication and build snapshots."""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


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
