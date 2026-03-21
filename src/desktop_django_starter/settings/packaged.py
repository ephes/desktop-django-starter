"""Settings for a future packaged desktop runtime."""

from __future__ import annotations

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from . import base as base_settings
from .base import *  # noqa: F403

DEBUG = False

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
    },
}
STATIC_ROOT = app_data_dir / "staticfiles"  # noqa: F405
