"""Shared Django settings for the desktop starter."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]
PROJECT_PACKAGE_DIR = Path(__file__).resolve().parents[1]


def _allowed_hosts() -> list[str]:
    host = os.environ.get("DESKTOP_DJANGO_HOST", "127.0.0.1")
    return [host, "localhost"]


INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.messages",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "django_tasks_db",
    "desktop_django_starter",
    "example_app",
    "tasks_demo",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "desktop_django_starter.middleware.DesktopAuthTokenMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "desktop_django_starter.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [PROJECT_PACKAGE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "desktop_django_starter.wsgi.application"
ASGI_APPLICATION = "desktop_django_starter.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

TASKS = {
    "default": {
        "BACKEND": "django_tasks_db.DatabaseBackend",
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "desktop-django-starter-development-secret-key",
)

DEBUG = False
ALLOWED_HOSTS = _allowed_hosts()
DESKTOP_DJANGO_AUTH_TOKEN = os.environ.get("DESKTOP_DJANGO_AUTH_TOKEN", "")
# When True, requests are refused if no shell token was configured, so a shell
# that forgets to pass the token fails closed. Packaged settings turn this on.
DESKTOP_DJANGO_REQUIRE_AUTH_TOKEN = False

# Same request log as Django's default `django.server` config, plus a filter
# that keeps the auth bootstrap token out of the log.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "redact_desktop_auth_token": {
            "()": "desktop_django_starter.log_filters.RedactDesktopAuthToken",
        },
    },
    "formatters": {
        "django.server": {
            "()": "django.utils.log.ServerFormatter",
            "format": "[{server_time}] {message}",
            "style": "{",
        },
    },
    "handlers": {
        "django.server": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "django.server",
            "filters": ["redact_desktop_auth_token"],
        },
    },
    "loggers": {
        "django.server": {
            "handlers": ["django.server"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
