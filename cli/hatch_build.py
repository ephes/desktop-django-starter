"""Hatch build hook: fail the build if staged assets are missing."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class AssetGuardHook(BuildHookInterface):
    PLUGIN_NAME = "asset-guard"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        assets_dir = Path(self.root) / "src" / "dds" / "_assets"
        # Load a standalone inventory without importing the interactive CLI or
        # depending on the caller's sys.path (Hatch loads hooks by file path).
        inventory = runpy.run_path(str(Path(self.root) / "asset_inventory.py"))
        missing = [rel for rel in inventory["CANONICAL_ASSETS"] if not (assets_dir / rel).is_file()]
        if missing:
            listed = ", ".join(missing[:8])
            remaining = f" (+{len(missing) - 8} more)" if len(missing) > 8 else ""
            raise RuntimeError(
                f"Staged assets incomplete: {len(missing)} required file(s) missing: "
                f"{listed}{remaining}. Run 'just cli-sync-assets' before building."
            )
