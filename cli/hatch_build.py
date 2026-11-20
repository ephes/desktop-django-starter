"""Validate staged CLI assets and give Hatch a private archive input."""

from __future__ import annotations

import runpy
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class AssetGuardHook(BuildHookInterface):
    PLUGIN_NAME = "asset-guard"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        root = Path(self.root)
        relative_assets = Path("src/dds/_assets")
        assets_dir = root / relative_assets
        # Hatch loads hooks by file path. Load the standalone helpers without
        # importing the CLI or relying on the caller's sys.path.
        required = runpy.run_path(str(root / "asset_inventory.py"))["CANONICAL_ASSETS"]
        helpers = runpy.run_path(str(root / "asset_lock.py"))
        with helpers["asset_lock"](assets_dir.parent):
            helpers["recover_asset_replacement"](assets_dir)
            missing = [rel for rel in required if not (assets_dir / rel).is_file()]
            if missing:
                listed = ", ".join(missing[:8])
                remaining = f" (+{len(missing) - 8} more)" if len(missing) > 8 else ""
                raise RuntimeError(
                    f"Staged assets incomplete: {len(missing)} required file(s) missing: "
                    f"{listed}{remaining}. Run 'just cli-sync-assets' before building."
                )
            if version == "editable":
                # Editable installs resolve resources in the source package.
                return

            snapshot = TemporaryDirectory(prefix="dds-build-assets-")
            snapshot_dir = Path(snapshot.name)
            try:
                members = (
                    [*required, ".gitkeep"] if (assets_dir / ".gitkeep").is_file() else required
                )
                for rel in members:
                    dst = snapshot_dir / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(assets_dir / rel, dst)
            except BaseException:
                snapshot.cleanup()
                raise

        # The live tree is excluded from discovery. Hatch applies the target's
        # source mapping to this archive path for both wheels and sdists.
        build_data["force_include"][snapshot.name] = relative_assets.as_posix()
        # Keep the snapshot alive until Hatch finishes reading it. The
        # TemporaryDirectory finalizer also handles failed builds.
        build_data["asset_snapshot"] = snapshot

    def finalize(self, version: str, build_data: dict[str, Any], artifact_path: str) -> None:
        snapshot = build_data.pop("asset_snapshot", None)
        if snapshot is not None:
            snapshot.cleanup()
