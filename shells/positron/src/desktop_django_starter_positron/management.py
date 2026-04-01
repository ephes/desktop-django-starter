from __future__ import annotations

import os
import sys

from .runtime import ensure_project_imports


def main(argv: list[str] | None = None) -> int:
    ensure_project_imports()
    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE",
        "desktop_django_starter.settings.local",
    )

    from django.core.management import execute_from_command_line

    execute_from_command_line(argv or sys.argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
