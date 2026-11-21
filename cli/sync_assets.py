#!/usr/bin/env python3
"""Stage canonical repo files into cli/src/dds/_assets/ for wheel builds.

Run from the repo root:  python cli/sync_assets.py
Or via just:             just cli-sync-assets
"""

from __future__ import annotations

import hashlib
import shutil
import stat
import tempfile
from contextlib import ExitStack
from pathlib import Path

from asset_inventory import CANONICAL_ASSETS
from asset_lock import (
    ASSET_MARKER,
    asset_lock,
    mark_asset_replacement,
    recover_asset_replacement,
    retire_asset_replacement,
    sync_directory,
    sync_staged_assets,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = Path(__file__).resolve().parent / "src" / "dds" / "_assets"


def source_identity(rel: str) -> tuple[int, ...] | None:
    try:
        info = (REPO_ROOT / rel).stat()
    except (FileNotFoundError, NotADirectoryError):
        return None
    if not stat.S_ISREG(info.st_mode):
        return None
    return info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def check_source(rel: str, expected: tuple[int, ...]) -> None:
    if source_identity(rel) != expected:
        raise RuntimeError(f"Canonical asset changed: {rel}. Retry after edits finish.")


def file_digest(path: Path) -> bytes:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.digest()


def check_source_content(rel: str, expected: tuple[int, ...], staged: Path) -> None:
    """Compare bytes too: same-size edits can keep coarse timestamps unchanged."""
    check_source(rel, expected)
    if file_digest(REPO_ROOT / rel) != file_digest(staged / rel):
        raise RuntimeError(f"Canonical asset changed: {rel}. Retry after edits finish.")
    check_source(rel, expected)


def sync() -> None:
    marker = ASSETS_DIR.parent / ASSET_MARKER
    if marker.exists() or marker.is_symlink():
        with asset_lock(ASSETS_DIR.parent):
            recover_asset_replacement(ASSETS_DIR)

    sources = {}
    missing = []
    for rel in CANONICAL_ASSETS:
        identity = source_identity(rel)
        if identity is None:
            missing.append(rel)
        else:
            sources[rel] = identity
    if missing:
        print(f"warning: {len(missing)} canonical file(s) not found:")
        for rel in missing:
            print(f"  {rel}")
        raise SystemExit(1)

    ASSETS_DIR.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".assets-sync-", dir=ASSETS_DIR.parent))
    staged = work / "staged"
    backup = work / "previous"
    # Keep the publication lock through rollback and its cleanup. A later
    # process may take ownership of the work directory as soon as we unlock.
    with ExitStack() as lock:
        journaled = False
        try:
            staged.mkdir()
            for rel, expected in sources.items():
                dst = staged / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                check_source(rel, expected)
                shutil.copy2(REPO_ROOT / rel, dst)
                check_source(rel, expected)
            # Catch edits to assets that were copied before later entries,
            # including same-size edits within one timestamp tick.
            for rel, expected in sources.items():
                check_source_content(rel, expected, staged)
            lock.enter_context(asset_lock(ASSETS_DIR.parent))
            recover_asset_replacement(ASSETS_DIR)
            # Preserve the repository placeholder, including its bytes, if present.
            placeholder = ASSETS_DIR / ".gitkeep"
            if placeholder.is_file():
                shutil.copy2(placeholder, staged / ".gitkeep")
            sync_staged_assets(staged)
            if ASSETS_DIR.exists() or ASSETS_DIR.is_symlink():
                # Keep the recorded work directory even if a journal barrier fails.
                try:
                    mark_asset_replacement(ASSETS_DIR, work)
                finally:
                    journaled = marker.exists()
                sync_directory(work)
                sync_directory(ASSETS_DIR.parent)

                ASSETS_DIR.rename(backup)

            try:
                if journaled:
                    # Make the predecessor reachable from its recovery path before
                    # promotion. A failed barrier restores it like a failed rename.
                    sync_directory(work)
                    sync_directory(ASSETS_DIR.parent)
                staged.rename(ASSETS_DIR)
            except BaseException as publish_error:
                if journaled:
                    try:
                        recover_asset_replacement(ASSETS_DIR)
                    except BaseException as restore_error:
                        recovery = RuntimeError(
                            f"Asset recovery incomplete. Inspect {marker} and {work}. "
                            f"Previous assets may be at {backup}."
                        )
                        recovery.__cause__ = restore_error
                        raise publish_error from recovery
                raise
            if journaled:
                retire_asset_replacement(ASSETS_DIR, work)
            else:
                sync_directory(ASSETS_DIR.parent)
        except BaseException as primary:
            try:
                if not journaled:
                    shutil.rmtree(work)
                elif backup.exists():
                    print(f"Previous assets retained at {backup}")
            except BaseException as cleanup_error:
                # Keep recovery diagnostics under the primary error.
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
