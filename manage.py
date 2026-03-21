#!/usr/bin/env python
"""Django management entrypoint for the desktop starter."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE",
        "desktop_django_starter.settings.local",
    )

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
