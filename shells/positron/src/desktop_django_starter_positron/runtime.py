from __future__ import annotations

import importlib.metadata
import os
import sys
from contextlib import suppress
from pathlib import Path
from typing import BinaryIO

from django.core.files import locks

HOST = "127.0.0.1"
POSITRON_RUNTIME_MODE = "packaged"
POSITRON_DJANGO_SETTINGS_MODULE = "desktop_django_starter.settings.packaged"
POSITRON_INSTANCE_LOCK_FILENAME = "desktop-django-starter-positron.lock"
WORKER_ID = "desktop-django-starter-positron"
POSITRON_DISTRIBUTION_NAME = "desktop-django-starter-positron"


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
    acquired = False
    try:
        acquired = locks.lock(lock_file, locks.LOCK_EX | locks.LOCK_NB)
        if not acquired:
            lock_file.close()
            return None

        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(f"{os.getpid()}\n".encode("ascii"))
        lock_file.flush()
        return lock_file
    except BaseException:
        # Cleanup must not replace the acquisition/initialization failure.
        with suppress(BaseException):
            if acquired:
                release_instance_lock(lock_file)
            else:
                lock_file.close()
        raise


def release_instance_lock(lock_file: BinaryIO | None) -> None:
    if lock_file is None:
        return

    try:
        locks.unlock(lock_file)
    except BaseException:
        # Closing releases the OS lock even when explicit unlock fails.
        with suppress(BaseException):
            lock_file.close()
        raise
    else:
        lock_file.close()


def positron_app_version(toga_version: str | None = None) -> str | None:
    """Return the app version used to pick the versioned state directory.

    Toga derives its metadata lookup from the app ID's last segment
    ("positron"), which is not the distribution name, so ``App.version`` is
    usually empty; fall back to the installed distribution's version.
    """
    if toga_version:
        return toga_version
    try:
        return importlib.metadata.version(POSITRON_DISTRIBUTION_NAME)
    except importlib.metadata.PackageNotFoundError:
        return None


def exit_confirmation_message(counts: dict[str, int]) -> str | None:
    """Return the quit warning for running/queued background tasks, if any."""
    running = counts.get("running_tasks", 0)
    queued = counts.get("queued_tasks", 0)
    if running + queued == 0:
        return None
    # Running tasks are interrupted by quitting; queued tasks stay in the
    # database and start when the app runs again.
    def plural(count: int, noun: str) -> str:
        return f"{count} {noun}{'' if count == 1 else 's'}"

    parts = []
    if running:
        parts.append(f"Quitting now stops {plural(running, 'running background task')}.")
    if queued:
        parts.append(f"{plural(queued, 'queued task')} will start the next time the app runs.")
    return " ".join(parts) + "\n\nQuit anyway?"


def django_environment(
    *,
    app_data_dir: Path,
    bundle_dir: Path,
    port: int | None = None,
    auth_token: str | None = None,
    app_version: str | None = None,
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
        "PYTHONUNBUFFERED": "1",
    }
    if port is not None:
        environment["DESKTOP_DJANGO_PORT"] = str(port)
    if auth_token is not None:
        environment["DESKTOP_DJANGO_AUTH_TOKEN"] = auth_token
    if app_version:
        # Packaged settings keep database, media and cache per app version
        # under <app-data>/state/<version>/ (desktop_django_starter.app_state).
        environment["DESKTOP_DJANGO_APP_VERSION"] = app_version

    return environment
