"""Project metadata package for tooling and documentation scaffolding."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version

try:
    __version__ = package_version("desktop-django-starter")
except PackageNotFoundError:  # pragma: no cover - fallback for editable local use
    __version__ = "0.1.0"
