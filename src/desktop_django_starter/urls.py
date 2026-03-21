"""URL routing for the desktop Django starter."""

from __future__ import annotations

from django.http import JsonResponse
from django.urls import include, path


def health_view(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("health/", health_view, name="health"),
    path("", include("example_app.urls")),
]
