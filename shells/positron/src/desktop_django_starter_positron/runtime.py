from __future__ import annotations

import os
import sys
from pathlib import Path

HOST = "127.0.0.1"
PACKAGED_RUNTIME_SECRET_KEY = "desktop-django-starter-packaged-runtime-secret"
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


def django_environment(
    *,
    app_data_dir: Path,
    bundle_dir: Path,
    port: int | None = None,
) -> dict[str, str]:
    app_data_dir.mkdir(parents=True, exist_ok=True)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    environment = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "desktop_django_starter.settings.packaged",
        "DESKTOP_DJANGO_APP_DATA_DIR": str(app_data_dir),
        "DESKTOP_DJANGO_BUNDLE_DIR": str(bundle_dir),
        "DESKTOP_DJANGO_HOST": HOST,
        "DJANGO_SECRET_KEY": os.environ.get("DJANGO_SECRET_KEY", PACKAGED_RUNTIME_SECRET_KEY),
        "PYTHONUNBUFFERED": "1",
    }
    if port is not None:
        environment["DESKTOP_DJANGO_PORT"] = str(port)

    return environment
