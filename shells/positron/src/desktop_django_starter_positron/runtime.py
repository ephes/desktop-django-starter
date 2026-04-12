from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import BinaryIO

from django.core.files import locks

HOST = "127.0.0.1"
PACKAGED_RUNTIME_SECRET_KEY = "desktop-django-starter-packaged-runtime-secret"
POSITRON_RUNTIME_MODE = "packaged"
POSITRON_DJANGO_SETTINGS_MODULE = "desktop_django_starter.settings.packaged"
POSITRON_INSTANCE_LOCK_FILENAME = "desktop-django-starter-positron.lock"
WORKER_ID = "desktop-django-starter-positron"


def bundled_app_root(module_file: str | Path | None = None) -> Path:
    source = Path(module_file or __file__).resolve()
    return source.parents[1]


def bundled_django_src(module_file: str | Path | None = None) -> Path:
    return bundled_app_root(module_file) / "src"


def development_repo_root(module_file: str | Path | None = None) -> Path:
    source = Path(module_file or __file__).resolve()
    return source.parents[4]


def development_repo_src(module_file: str | Path | None = None) -> Path:
    return development_repo_root(module_file) / "src"


def shared_brand_icon(module_file: str | Path | None = None) -> Path:
    return development_repo_root(module_file) / "assets" / "brand" / "flying-stable-app-icon.svg"


def resolve_django_source_root(module_file: str | Path | None = None) -> Path:
    expected_packages = ("desktop_django_starter", "example_app", "tasks_demo")
    candidates = [
        bundled_django_src(module_file),
        development_repo_src(module_file),
    ]

    for candidate in candidates:
        if not candidate.exists():
            continue
        if all((candidate / package).exists() for package in expected_packages):
            return candidate

    expected_locations = ", ".join(str(candidate) for candidate in candidates)
    raise RuntimeError(
        "Could not locate the shared Django source tree. "
        f"Expected {expected_locations} to contain {', '.join(expected_packages)}."
    )


def ensure_project_imports(module_file: str | Path | None = None) -> None:
    candidates = [
        bundled_app_root(module_file),
        resolve_django_source_root(module_file),
    ]
    for candidate in candidates:
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))


def positron_runtime_mode() -> str:
    return POSITRON_RUNTIME_MODE


def positron_settings_module() -> str:
    return POSITRON_DJANGO_SETTINGS_MODULE


def instance_lock_path(app_data_dir: Path) -> Path:
    return app_data_dir / POSITRON_INSTANCE_LOCK_FILENAME


def acquire_instance_lock(app_data_dir: Path) -> BinaryIO | None:
    app_data_dir.mkdir(parents=True, exist_ok=True)
    lock_file = instance_lock_path(app_data_dir).open("a+b")
    if not locks.lock(lock_file, locks.LOCK_EX | locks.LOCK_NB):
        lock_file.close()
        return None

    lock_file.seek(0)
    lock_file.truncate()
    lock_file.write(f"{os.getpid()}\n".encode("ascii"))
    lock_file.flush()
    return lock_file


def release_instance_lock(lock_file: BinaryIO | None) -> None:
    if lock_file is None:
        return

    locks.unlock(lock_file)
    lock_file.close()


def django_environment(
    *,
    app_data_dir: Path,
    bundle_dir: Path,
    port: int | None = None,
    auth_token: str | None = None,
) -> dict[str, str]:
    app_data_dir.mkdir(parents=True, exist_ok=True)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    environment = {
        **os.environ,
        "DESKTOP_DJANGO_RUNTIME_MODE": positron_runtime_mode(),
        "DJANGO_SETTINGS_MODULE": positron_settings_module(),
        "DESKTOP_DJANGO_APP_DATA_DIR": str(app_data_dir),
        "DESKTOP_DJANGO_BUNDLE_DIR": str(bundle_dir),
        "DESKTOP_DJANGO_HOST": HOST,
        "DJANGO_SECRET_KEY": os.environ.get("DJANGO_SECRET_KEY", PACKAGED_RUNTIME_SECRET_KEY),
        "PYTHONUNBUFFERED": "1",
    }
    if port is not None:
        environment["DESKTOP_DJANGO_PORT"] = str(port)
    if auth_token is not None:
        environment["DESKTOP_DJANGO_AUTH_TOKEN"] = auth_token

    return environment
