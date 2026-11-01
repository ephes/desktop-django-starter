"""The staged wrap skill pins checksums of the starter templates it rewrites.

If a template changes without updating the pin, Stage 1 of the staged wrap
workflow refuses to run. This test catches that in the starter's own checks.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAFFOLD = (
    ROOT
    / "skills"
    / "wrap-existing-django-in-electron-staged"
    / "scripts"
    / "prepare-electron-scaffold.cjs"
)

# Paths in the copied `electron/` scaffold, mapped to their starter sources.
TEMPLATE_SOURCES = {
    "main.js": "shells/electron/main.js",
    "scripts/electron-builder-config.cjs": "shells/electron/scripts/electron-builder-config.cjs",
    "scripts/launch-electron.cjs": "shells/electron/scripts/launch-electron.cjs",
    "scripts/stage-backend.cjs": "scripts/stage-backend.cjs",
    "scripts/bundled-python.cjs": "scripts/bundled-python.cjs",
}


def test_staged_scaffold_checksums_match_starter_templates() -> None:
    source = SCAFFOLD.read_text()
    block = re.search(r"STARTER_TEMPLATE_CHECKSUMS = \{(.*?)\};", source, re.S)
    assert block, "STARTER_TEMPLATE_CHECKSUMS not found"
    pinned = dict(re.findall(r'"([^"]+)":\s*"([0-9a-f]{64})"', block.group(1)))

    assert set(pinned) == set(TEMPLATE_SOURCES)
    for scaffold_path, starter_path in TEMPLATE_SOURCES.items():
        actual = hashlib.sha256((ROOT / starter_path).read_bytes()).hexdigest()
        assert pinned[scaffold_path] == actual, (
            f"{starter_path} changed; update its checksum and rewrite logic in {SCAFFOLD.name}"
        )
