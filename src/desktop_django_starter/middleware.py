"""Middleware for desktop shell request authentication."""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden

logger = logging.getLogger(__name__)

DESKTOP_AUTH_HEADER = "X-Desktop-Django-Token"


class DesktopAuthTokenMiddleware:
    """Require the Electron shell token when configured."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        expected_token = getattr(settings, "DESKTOP_DJANGO_AUTH_TOKEN", "")
        if not expected_token:
            return self.get_response(request)

        request_token = request.headers.get(DESKTOP_AUTH_HEADER, "")
        if secrets.compare_digest(request_token, expected_token):
            return self.get_response(request)

        logger.warning(
            "Rejected desktop Django request with missing or invalid auth token: %s",
            request.path,
        )
        return HttpResponseForbidden("Forbidden")
