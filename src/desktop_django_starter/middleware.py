"""Middleware for desktop shell request authentication."""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable
from urllib.parse import urlsplit

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, HttpResponseRedirect

logger = logging.getLogger(__name__)

DESKTOP_AUTH_HEADER = "X-Desktop-Django-Token"
DESKTOP_AUTH_COOKIE = "desktop_django_auth_token"
DESKTOP_AUTH_BOOTSTRAP_PATH = "/desktop-auth/bootstrap/"


class DesktopAuthTokenMiddleware:
    """Require the desktop shell token when configured."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        expected_token = getattr(settings, "DESKTOP_DJANGO_AUTH_TOKEN", "")
        if not expected_token:
            return self.get_response(request)

        if request.path == DESKTOP_AUTH_BOOTSTRAP_PATH:
            return self._bootstrap(request, expected_token)

        request_token = request.headers.get(DESKTOP_AUTH_HEADER, "")
        if secrets.compare_digest(request_token, expected_token):
            return self.get_response(request)

        cookie_token = request.COOKIES.get(DESKTOP_AUTH_COOKIE, "")
        if secrets.compare_digest(cookie_token, expected_token):
            return self.get_response(request)

        logger.warning(
            "Rejected desktop Django request with missing or invalid auth token: %s",
            request.path,
        )
        return HttpResponseForbidden("Forbidden")

    def _bootstrap(self, request: HttpRequest, expected_token: str) -> HttpResponse:
        request_token = request.GET.get("token", "")
        if not secrets.compare_digest(request_token, expected_token):
            logger.warning(
                "Rejected desktop Django auth bootstrap with missing or invalid token."
            )
            return HttpResponseForbidden("Forbidden")

        next_path = request.GET.get("next", "/")
        if not _is_safe_relative_redirect(next_path):
            logger.warning("Rejected desktop Django auth bootstrap with unsafe next path.")
            return HttpResponseForbidden("Forbidden")

        response = HttpResponseRedirect(next_path)
        response.set_cookie(
            DESKTOP_AUTH_COOKIE,
            expected_token,
            httponly=True,
            path="/",
            samesite="Strict",
        )
        return response


def _is_safe_relative_redirect(next_path: str) -> bool:
    if not next_path or next_path.startswith(("//", "\\")):
        return False
    if "\\" in next_path:
        return False
    if any(ord(character) < 32 for character in next_path):
        return False

    parsed = urlsplit(next_path)
    if parsed.scheme or parsed.netloc:
        return False

    return next_path.startswith("/")
