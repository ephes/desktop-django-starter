#!/usr/bin/env python3
"""Stage canonical repo files into cli/src/dds/_assets/ for wheel builds.

Run from the repo root:  python cli/sync_assets.py
Or via just:             just cli-sync-assets
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from asset_inventory import CANONICAL_ASSETS

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = Path(__file__).resolve().parent / "src" / "dds" / "_assets"



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
    staged.mkdir()
    published = False
    try:
        for rel in CANONICAL_ASSETS:
            dst = staged / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / rel, dst)
        # Preserve the repository placeholder, including its bytes, if present.
        placeholder = ASSETS_DIR / ".gitkeep"
        if placeholder.is_file():
            shutil.copy2(placeholder, staged / ".gitkeep")

        if ASSETS_DIR.exists():
            ASSETS_DIR.rename(backup)
        try:
            staged.rename(ASSETS_DIR)
        except BaseException:
            if backup.exists():
                backup.rename(ASSETS_DIR)
            raise
        published = True
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        # Retain recovery data if restoration or old-tree cleanup failed.
        if backup.exists():
            label = "Old asset cleanup incomplete" if published else "Previous assets retained"
            print(f"{label} at {backup}")
            if staged.exists():
                shutil.rmtree(staged, ignore_errors=True)
        else:
            shutil.rmtree(work)

    print(f"Synced {len(CANONICAL_ASSETS)} assets to {ASSETS_DIR}")


if __name__ == "__main__":
    sync()
