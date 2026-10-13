"""User-level config helpers for wrapper defaults."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# The standalone CLI supports Python 3.10, below the root project floor.
if sys.version_info >= (3, 11):  # noqa: UP036
    import tomllib
else:
    import tomli as tomllib

SUPPORTED_HARNESSES = ("claude", "pi", "codex")
_WRAP_SECTION = "wrap"
# Windows refuses to replace a file while another process or thread is replacing
# or reading it, and refuses to open one that is being replaced, so a concurrent
# save or load sees a short-lived PermissionError there. Elsewhere a
# PermissionError is a real permission problem and is not retried.
_SHARING_RETRY_DELAYS: tuple[float, ...] = (0.01, 0.02, 0.05, 0.1, 0.2) if os.name == "nt" else ()


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
        content: str = _retry_sharing_violation(lambda: resolved_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        raise ConfigError(f"Could not read {resolved_path}: {exc}") from exc

    return _parse_wrapper_config(content, resolved_path)


def _retry_sharing_violation(operation: Callable[[], Any]) -> Any:
    """Run a file operation, waiting out transient sharing violations."""
    for delay in _SHARING_RETRY_DELAYS:
        try:
            return operation()
        except PermissionError:
            time.sleep(delay)
    return operation()


def save_wrapper_config(config: WrapperConfig, path: Path | None = None) -> Path:
    """Persist wrapper defaults to disk."""
    if config.harness not in SUPPORTED_HARNESSES:
        supported = ", ".join(SUPPORTED_HARNESSES)
        raise ConfigError(f"Unsupported harness {config.harness!r}. Expected one of: {supported}.")

    resolved_path = path or default_config_path()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"[{_WRAP_SECTION}]",
        f"harness = {json.dumps(config.harness, ensure_ascii=False)}",
    ]
    if config.model:
        lines.append(f"model = {json.dumps(config.model, ensure_ascii=False)}")
    content = ("\n".join(lines) + "\n").replace("\x7f", "\\u007f")

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=resolved_path.parent,
            prefix=f"{resolved_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temp_path = Path(stream.name)
            stream.write(content)
        _retry_sharing_violation(lambda: temp_path.replace(resolved_path))
    except (OSError, UnicodeError) as exc:
        raise ConfigError(f"Could not write {resolved_path}: {exc}") from exc
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    return resolved_path


def _parse_wrapper_config(content: str, source: Path) -> WrapperConfig:
    try:
        document = tomllib.loads(content)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{source}: invalid TOML: {exc}") from exc

    if _WRAP_SECTION not in document:
        raise ConfigError(f"{source}: missing [{_WRAP_SECTION}] section")
    wrap_values = document[_WRAP_SECTION]
    if not isinstance(wrap_values, dict):
        raise ConfigError(f"{source}: expected wrap to be a table")

    harness = wrap_values.get("harness")
    if not isinstance(harness, str) or harness not in SUPPORTED_HARNESSES:
        supported = ", ".join(SUPPORTED_HARNESSES)
        raise ConfigError(f"{source}: expected wrap.harness to be one of: {supported}")

    model = wrap_values.get("model")
    if "model" in wrap_values and not isinstance(model, str):
        raise ConfigError(f"{source}: expected wrap.model to be a string")
    return WrapperConfig(harness=harness, model=model or None)
