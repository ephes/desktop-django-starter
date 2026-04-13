"""User-level config helpers for wrapper defaults."""

from __future__ import annotations

import ast
import json
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_HARNESSES = ("claude", "pi", "codex")
_WRAP_SECTION = "wrap"


class ConfigError(RuntimeError):
    """Raised when the user config cannot be read or parsed."""


@dataclass(frozen=True)
class WrapperConfig:
    """Persisted wrapper defaults."""

    harness: str
    model: str | None = None


def default_config_path() -> Path:
    """Return the user config location for wrapper defaults."""
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    else:
        xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg_config_home) if xdg_config_home else Path.home() / ".config"
    return base / "dds" / "config.toml"


def detect_installed_harnesses(
    which: Callable[[str], str | None] = shutil.which,
) -> dict[str, str]:
    """Return supported harnesses found on PATH, in display order."""
    found: dict[str, str] = {}
    for harness in SUPPORTED_HARNESSES:
        resolved = which(harness)
        if resolved:
            found[harness] = resolved
    return found


def load_wrapper_config(path: Path | None = None) -> WrapperConfig | None:
    """Load wrapper defaults from disk, if present."""
    resolved_path = path or default_config_path()
    if not resolved_path.exists():
        return None

    try:
        content = resolved_path.read_text()
    except OSError as exc:
        raise ConfigError(f"Could not read {resolved_path}: {exc}") from exc

    return _parse_wrapper_config(content, resolved_path)


def save_wrapper_config(config: WrapperConfig, path: Path | None = None) -> Path:
    """Persist wrapper defaults to disk."""
    if config.harness not in SUPPORTED_HARNESSES:
        supported = ", ".join(SUPPORTED_HARNESSES)
        raise ConfigError(f"Unsupported harness {config.harness!r}. Expected one of: {supported}.")

    resolved_path = path or default_config_path()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"[{_WRAP_SECTION}]",
        f"harness = {json.dumps(config.harness)}",
    ]
    if config.model:
        lines.append(f"model = {json.dumps(config.model)}")
    content = "\n".join(lines) + "\n"

    temp_path = resolved_path.with_suffix(f"{resolved_path.suffix}.tmp")
    try:
        temp_path.write_text(content)
        temp_path.replace(resolved_path)
    except OSError as exc:
        raise ConfigError(f"Could not write {resolved_path}: {exc}") from exc

    return resolved_path


def _parse_wrapper_config(content: str, source: Path) -> WrapperConfig:
    section: str | None = None
    wrap_values: dict[str, str] = {}
    saw_wrap_section = False

    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip()
            saw_wrap_section = saw_wrap_section or section == _WRAP_SECTION
            continue

        if "=" not in raw_line:
            raise ConfigError(f"{source}:{line_number}: expected key = value")

        if section != _WRAP_SECTION:
            continue

        key, raw_value = raw_line.split("=", 1)
        key = key.strip()
        raw_value = raw_value.strip()

        try:
            parsed_value = ast.literal_eval(raw_value)
        except (SyntaxError, ValueError) as exc:
            raise ConfigError(
                f"{source}:{line_number}: expected a quoted string for {key!r}"
            ) from exc

        if not isinstance(parsed_value, str):
            raise ConfigError(f"{source}:{line_number}: expected {key!r} to be a string")

        if key in {"harness", "model"}:
            wrap_values[key] = parsed_value

    if not saw_wrap_section:
        raise ConfigError(f"{source}: missing [{_WRAP_SECTION}] section")

    harness = wrap_values.get("harness")
    if harness not in SUPPORTED_HARNESSES:
        supported = ", ".join(SUPPORTED_HARNESSES)
        raise ConfigError(f"{source}: expected wrap.harness to be one of: {supported}")

    model = wrap_values.get("model") or None
    return WrapperConfig(harness=harness, model=model)
