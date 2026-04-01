"""URL routing for the desktop Django starter."""

from __future__ import annotations

from django.conf import settings
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.urls import include, path, re_path
from django.views.static import serve as static_serve


def health_view(_request):
    return JsonResponse({"status": "ok"})


def packaged_static_view(request, path):
    # Packaged mode serves from collected assets under STATIC_ROOT. Development
    # keeps using Django's normal DEBUG=True static handling instead.
    if settings.DEBUG:
        raise Http404("Static files are served by Django only in packaged mode.")

    return static_serve(request, path, document_root=settings.STATIC_ROOT)


def splash_view(request):
    return render(request, "splash.html")


urlpatterns = [
    path("splash/", splash_view, name="splash"),
    path("health/", health_view, name="health"),
    path("", include("example_app.urls")),
    path("tasks/", include("tasks_demo.urls")),
    re_path(r"^static/(?P<path>.*)$", packaged_static_view, name="packaged-static"),
]

if settings.DEBUG:
    urlpatterns.insert(0, path("__reload__/", include("django_browser_reload.urls")))

