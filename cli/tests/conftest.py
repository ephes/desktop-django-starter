from __future__ import annotations

from pathlib import Path

import pytest

# Environment variables that decide where per-user config, data, and cache
# files live on Linux, macOS, and Windows. Tests must never touch the real
# locations, so every test gets its own throwaway directories.
_USER_DIR_ENV_VARS = {
    "HOME": "home",
    "USERPROFILE": "home",
    "XDG_CONFIG_HOME": "config",
    "XDG_DATA_HOME": "data",
    "XDG_CACHE_HOME": "cache",
    "XDG_STATE_HOME": "state",
    "APPDATA": "appdata-roaming",
    "LOCALAPPDATA": "appdata-local",
}


@pytest.fixture(autouse=True)
def isolated_user_dirs(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Point every per-user config/data directory at a temporary location."""
    root = tmp_path_factory.mktemp("user-dirs")
    for name, subdir in _USER_DIR_ENV_VARS.items():
        path = root / subdir
        path.mkdir(exist_ok=True)
        monkeypatch.setenv(name, str(path))
    return root
