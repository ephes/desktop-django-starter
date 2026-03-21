"""ASGI config for the desktop Django starter."""

from __future__ import annotations

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "desktop_django_starter.settings.local")

application = get_asgi_application()
