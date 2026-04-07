"""Verify that all bundled assets exist in the canonical repo locations.

This catches drift: if a canonical file is renamed or removed, this test fails
before a broken wheel is published.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add cli/ to path so we can import the sync script's asset list
CLI_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CLI_DIR))

from sync_assets import CANONICAL_ASSETS  # noqa: E402

REPO_ROOT = CLI_DIR.parent


@pytest.mark.parametrize("rel_path", CANONICAL_ASSETS)
def test_canonical_asset_exists(rel_path: str) -> None:
    full = REPO_ROOT / rel_path
    assert full.is_file(), f"canonical asset missing: {full}"
