#!/usr/bin/env python3
"""Stage canonical repo files into cli/src/dds/_assets/ for wheel builds.

Run from the repo root:  python cli/sync_assets.py
Or via just:             just cli-sync-assets
"""

from __future__ import annotations

import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = Path(__file__).resolve().parent / "src" / "dds" / "_assets"

# Repo-relative paths to bundle.  The _assets layout mirrors the repo structure
# so prompt.md path substitution (replacing "../desktop-django-starter" with the
# assets root) works unchanged.
CANONICAL_ASSETS: list[str] = [
    # Electron shell
    "shells/electron/main.js",
    "shells/electron/preload.cjs",
    "shells/electron/package.json",
    "shells/electron/electron-builder.config.cjs",
    "shells/electron/scripts/launch-electron.cjs",
    "shells/electron/scripts/bundled-python.cjs",
    "shells/electron/scripts/electron-builder-config.cjs",
    "shells/electron/scripts/auth-token.cjs",
    "shells/electron/scripts/materialize-symlinks.cjs",
    "shells/electron/scripts/bundled-python.test.cjs",
    "shells/electron/scripts/electron-builder-config.test.cjs",
    "shells/electron/scripts/auth-token.test.cjs",
    "shells/electron/scripts/materialize-symlinks.test.cjs",
    # Signing entitlements
    "shells/electron/signing/entitlements.mac.plist",
    "shells/electron/signing/entitlements.mac.inherit.plist",
    # Icon assets
    "shells/electron/assets/icons/app-icon.png",
    "shells/electron/assets/icons/app-icon.icns",
    # Shared packaging scripts
    "scripts/stage-backend.cjs",
    "scripts/bundled-python.cjs",
    "scripts/materialize-symlinks.cjs",
    "scripts/prune-bundled-python-runtime.cjs",
    # Wrapping skill and prompt
    "skills/wrap-existing-django-in-electron/SKILL.md",
    "skills/wrap-existing-django-in-electron/prompt.md",
    # Documentation
    "docs/architecture.md",
    "docs/specification.md",
    "docs/decisions.md",
    "docs/agent-use.md",
    "llms.txt",
    # CI workflow template
    ".github/workflows/desktop-packages.yml",
]


def sync() -> None:
    # Clean previous assets (except .gitkeep)
    if ASSETS_DIR.exists():
        for child in ASSETS_DIR.iterdir():
            if child.name == ".gitkeep":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    copied = 0
    missing = []

    for rel_path in CANONICAL_ASSETS:
        src = REPO_ROOT / rel_path
        dst = ASSETS_DIR / rel_path

        if not src.is_file():
            missing.append(rel_path)
            continue

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1

    if missing:
        print(f"warning: {len(missing)} canonical file(s) not found:")
        for m in missing:
            print(f"  {m}")
        raise SystemExit(1)

    print(f"Synced {copied} assets to {ASSETS_DIR}")


if __name__ == "__main__":
    sync()
