import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

project = "desktop-django-starter"
author = "Jochen Wersdoerfer"
copyright = "2026, Jochen Wersdoerfer"

try:
    release = package_version("desktop-django-starter")
except PackageNotFoundError:
    release = "0.1.0"

version = release

extensions = [
    "myst_parser",
    "sphinxcontrib.mermaid",
]

source_suffix = {
    ".md": "markdown",
    ".rst": "restructuredtext",
}

root_doc = "index"
templates_path = []
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
html_extra_path = ["llms.txt"]

myst_enable_extensions = [
    "colon_fence",
]

html_theme = "furo"
html_title = "desktop-django-starter"
html_static_path = []

mermaid_version = "11.12.0"
