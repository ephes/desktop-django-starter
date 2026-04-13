"""Check prerequisites for wrapping a Django project."""

from __future__ import annotations

import shutil
import sys
from importlib.resources import files
from pathlib import Path

from dds import __version__
from dds.config import (
    SUPPORTED_HARNESSES,
    ConfigError,
    default_config_path,
    detect_installed_harnesses,
    load_wrapper_config,
)

# Tools that must be present for wrapping to succeed.
REQUIRED_TOOLS = {
    "node": "Required for Electron",
    "npm": "Required for Electron dependencies",
    "just": "Required for justfile targets",
    "git": "Version control",
}

# Tools that are useful but not strictly required.
OPTIONAL_TOOLS = {
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
    wrap_needs_attention = _print_wrapper_setup_summary()

    print()
    if errors:
        print(f"Issues found: {errors}")
        sys.exit(1)
    if wrap_needs_attention:
        print("Core checks passed, but `dds wrap --run` still needs setup attention.")
    else:
        print("All checks passed.")


def _print_wrapper_setup_summary() -> bool:
    config_path = default_config_path()
    config_error: ConfigError | None = None
    try:
        config = load_wrapper_config(config_path)
    except ConfigError as exc:
        config = None
        config_error = exc

    installed = detect_installed_harnesses()
    print("Wrapper setup")
    if config_error is not None:
        print(f"  ! config: invalid ({config_path})")
        print(f"    {config_error}")
    elif config is None:
        print(f"  -  config: not found ({config_path})")
    else:
        print(f"  ok config: {config_path}")
        print(f"  ok default harness: {config.harness}")
        if config.model:
            print(f"  ok default model: {config.model}")
        else:
            print("  -  default model: harness default")

    for harness in SUPPORTED_HARNESSES:
        found = installed.get(harness)
        if found:
            print(f"  ok harness {harness}: {found}")
        else:
            print(f"  -  harness {harness}: not found")

    print()
    print("Wrap resolution")
    if config_error is not None:
        print("  ! saved wrapper config is invalid; run `dds init` to rewrite it.")
        return True

    if config is not None:
        if config.harness in installed:
            print(
                f"  ok `dds wrap --run` will use saved default harness `{config.harness}` "
                "unless you pass `--harness` or `--agent`."
            )
            return False
        print(
            f"  ! saved default harness `{config.harness}` is not on PATH; "
            "run `dds init` or pass `--harness` explicitly."
        )
        return True

    if len(installed) == 1:
        harness = next(iter(installed))
        print(
            f"  ok `dds wrap --run` will auto-select `{harness}` because it is the "
            "only supported harness on PATH."
        )
        return False

    if len(installed) > 1:
        names = ", ".join(installed)
        print(
            "  -  multiple supported harnesses are installed "
            f"({names}); interactive terminals will prompt on first run, and "
            "non-interactive runs need `dds init` or `--harness`."
        )
        return True

    print(
        "  ! no supported harness CLI is installed yet; install `claude`, `pi`, or "
        "`codex`, then run `dds init`."
    )
    return True
