"""Developer-friendly settings."""

from __future__ import annotations

from .base import *  # noqa: F403

DEBUG = True

INSTALLED_APPS += ["django_browser_reload"]  # noqa: F405

MIDDLEWARE += ["django_browser_reload.middleware.BrowserReloadMiddleware"]  # noqa: F405
