"""Hatch build hook: fail the build if staged assets are missing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class AssetGuardHook(BuildHookInterface):
    PLUGIN_NAME = "asset-guard"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        assets_dir = Path(self.root) / "src" / "dds" / "_assets"
        skill = (
            assets_dir
            / "skills"
            / "wrap-existing-django-in-electron"
            / "SKILL.md"
        )
        if not skill.is_file():
            msg = (
                "Staged assets not found. "
                "Run 'just cli-sync-assets' before building. "
                f"Expected: {skill}"
            )
            raise RuntimeError(msg)
