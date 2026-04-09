"""Settings for the packaged desktop runtime."""

from __future__ import annotations

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from . import base as base_settings
from .base import *  # noqa: F403

DEBUG = False

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
app_data_dir.mkdir(parents=True, exist_ok=True)

secret_key = os.environ.get("DJANGO_SECRET_KEY")
if not secret_key:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set for packaged settings.")

SECRET_KEY = secret_key
DATABASES = {  # noqa: F405
    **base_settings.DATABASES,
    "default": {
        **base_settings.DATABASES["default"],
        "NAME": app_data_dir / "app.sqlite3",
        "OPTIONS": {
            **base_settings.DATABASES["default"].get("OPTIONS", {}),
            **PACKAGED_SQLITE_OPTIONS,
        },
    },
}
STATIC_ROOT = bundle_dir / "staticfiles"  # noqa: F405
