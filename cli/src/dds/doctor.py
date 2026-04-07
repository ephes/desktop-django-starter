"""Check prerequisites for wrapping a Django project."""

from __future__ import annotations

import shutil
import sys
from importlib.resources import files
from pathlib import Path

from dds import __version__

# Tools that must be present for wrapping to succeed.
REQUIRED_TOOLS = {
    "node": "Required for Electron",
    "npm": "Required for Electron dependencies",
    "just": "Required for justfile targets",
    "git": "Version control",
}

# Tools that are useful but not strictly required.
OPTIONAL_TOOLS = {
    "claude": "AI agent (default)",
    "pi": "AI agent (alternative)",
    "codex": "AI agent (alternative)",
    "uv": "Python package manager",
}


def run_doctor() -> None:
    assets_path = Path(str(files("dds") / "_assets"))
    errors = 0

    print(f"dds {__version__}")
    print()

    # Check bundled assets
    skill = assets_path / "skills" / "wrap-existing-django-in-electron" / "SKILL.md"
    prompt = assets_path / "skills" / "wrap-existing-django-in-electron" / "prompt.md"
    electron_main = assets_path / "shells" / "electron" / "main.js"

    for label, path in [
        ("SKILL.md", skill),
        ("prompt.md", prompt),
        ("electron/main.js", electron_main),
    ]:
        if path.is_file():
            print(f"  ok asset: {label}")
        else:
            print(f"  x  asset missing: {label} ({path})", file=sys.stderr)
            errors += 1

    print(f"  ok assets root: {assets_path}")
    print()

    # Check required tools
    for tool, description in REQUIRED_TOOLS.items():
        found = shutil.which(tool)
        if found:
            print(f"  ok {tool}: {found}")
        else:
            print(f"  x  {tool}: not found ({description})", file=sys.stderr)
            errors += 1

    # Check optional tools
    for tool, description in OPTIONAL_TOOLS.items():
        found = shutil.which(tool)
        if found:
            print(f"  ok {tool}: {found}")
        else:
            print(f"  -  {tool}: not found ({description})")

    print()
    if errors:
        print(f"Issues found: {errors}")
        sys.exit(1)
    else:
        print("All checks passed.")
