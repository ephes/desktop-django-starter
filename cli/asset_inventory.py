"""Load the packaged asset manifest for sync and Hatch without CLI imports."""

from pathlib import Path

# Paths are relative to the repo root and retain that layout under _assets.
MANIFEST = Path(__file__).resolve().parent / "src" / "dds" / "asset_inventory.txt"
CANONICAL_ASSETS = MANIFEST.read_text(encoding="utf-8").splitlines()
if not CANONICAL_ASSETS:
    raise RuntimeError(f"Empty asset inventory: {MANIFEST}")
