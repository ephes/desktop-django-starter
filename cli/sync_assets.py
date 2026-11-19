#!/usr/bin/env python3
"""Stage canonical repo files into cli/src/dds/_assets/ for wheel builds.

Run from the repo root:  python cli/sync_assets.py
Or via just:             just cli-sync-assets
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from asset_inventory import CANONICAL_ASSETS

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = Path(__file__).resolve().parent / "src" / "dds" / "_assets"


@contextmanager
def publication_lock() -> Iterator[None]:
    # Keep the same lock file across runs, including while a publisher waits.
    # Closing the handle releases the operating system lock.
    with (ASSETS_DIR.parent / ".assets-sync-lock").open("a+b") as lock:
        if os.name == "nt":
            import msvcrt

            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        yield


def sync() -> None:
    missing = [rel for rel in CANONICAL_ASSETS if not (REPO_ROOT / rel).is_file()]
    if missing:
        print(f"warning: {len(missing)} canonical file(s) not found:")
        for rel in missing:
            print(f"  {rel}")
        raise SystemExit(1)

    ASSETS_DIR.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".assets-sync-", dir=ASSETS_DIR.parent))
    staged = work / "staged"
    backup = work / "previous"
    try:
        staged.mkdir()
        for rel in CANONICAL_ASSETS:
            dst = staged / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / rel, dst)
        with publication_lock():
            # Preserve the repository placeholder, including its bytes, if present.
            placeholder = ASSETS_DIR / ".gitkeep"
            if placeholder.is_file():
                shutil.copy2(placeholder, staged / ".gitkeep")

            if ASSETS_DIR.exists():
                ASSETS_DIR.rename(backup)
            try:
                staged.rename(ASSETS_DIR)
            except BaseException as publish_error:
                try:
                    if backup.exists():
                        backup.rename(ASSETS_DIR)
                except BaseException as restore_error:
                    recovery = RuntimeError(f"Previous assets retained at {backup}")
                    recovery.__cause__ = restore_error
                    raise publish_error from recovery
                raise
    except BaseException as primary:
        try:
            if backup.exists():
                print(f"Previous assets retained at {backup}")
                if staged.exists():
                    shutil.rmtree(staged)
            else:
                shutil.rmtree(work)
        except BaseException as cleanup_error:
            # Keep any rollback diagnostics in the chain under the primary error.
            cleanup_error.__cause__ = primary.__cause__
            raise primary from cleanup_error
        raise

    try:
        shutil.rmtree(work)
    except OSError:
        print(f"Old asset cleanup incomplete at {work}")
        raise

    print(f"Synced {len(CANONICAL_ASSETS)} assets to {ASSETS_DIR}")


if __name__ == "__main__":
    sync()
