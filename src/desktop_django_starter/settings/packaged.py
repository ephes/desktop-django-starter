"""Settings for the packaged desktop runtime."""

from __future__ import annotations

import os
from pathlib import Path

from desktop_django_starter.app_state import (
    CACHE_DIRNAME,
    DATABASE_FILENAME,
    MEDIA_DIRNAME,
    UNVERSIONED,
    prepare_versioned_state,
)
from desktop_django_starter.runtime_secret import load_or_create_secret_key

from . import base as base_settings
from .base import *  # noqa: F403

DEBUG = False
DESKTOP_DJANGO_REQUIRE_AUTH_TOKEN = True

# These rely on Django 5.1+ SQLite support for `transaction_mode`
# and `init_command`, which matches the repo's current Django 6.x baseline.
PACKAGED_SQLITE_OPTIONS = {
    "transaction_mode": "IMMEDIATE",
    "timeout": 20,
    "init_command": "\n".join(
        [
            "PRAGMA journal_mode=WAL;",
            "PRAGMA synchronous=NORMAL;",
            "PRAGMA cache_size=-20000;",
            "PRAGMA mmap_size=134217728;",
        ]
    ),
}

bundle_dir = Path(os.environ.get("DESKTOP_DJANGO_BUNDLE_DIR", BASE_DIR))  # noqa: F405
app_data_dir = Path(os.environ.get("DESKTOP_DJANGO_APP_DATA_DIR", BASE_DIR / "var"))  # noqa: F405
# The database and secret key live here, so keep the directory owner-only.
app_data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
if os.name != "nt":
    app_data_dir.chmod(0o700)

# An explicit DJANGO_SECRET_KEY wins. Otherwise each install generates its own
# random key once and keeps it, owner-only, in the app-data directory.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or load_or_create_secret_key(app_data_dir)
# Database, media and cache live in a per-version directory so an upgrade or a
# rollback never runs one version's code against another version's migrations.
# A new version starts from a copy of the newest older version's state; see
# desktop_django_starter.app_state. The secret key stays in the app-data root.
app_version = os.environ.get("DESKTOP_DJANGO_APP_VERSION", "").strip() or UNVERSIONED
state_dir = prepare_versioned_state(app_data_dir, app_version)

DATABASES = {  # noqa: F405
    **base_settings.DATABASES,
    "default": {
        **base_settings.DATABASES["default"],
        "NAME": state_dir / DATABASE_FILENAME,
        "OPTIONS": {
            **base_settings.DATABASES["default"].get("OPTIONS", {}),  # type: ignore[dict-item]
            **PACKAGED_SQLITE_OPTIONS,
        },
    },
}
STATIC_ROOT = bundle_dir / "staticfiles"  # noqa: F405
MEDIA_ROOT = state_dir / MEDIA_DIRNAME
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": state_dir / CACHE_DIRNAME,
    }
}
