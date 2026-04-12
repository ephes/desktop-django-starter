# Positron Shell

Experimental shell-local Positron app for `desktop-django-starter`.

This shell keeps Django and the optional `tasks_demo` worker in-process while reusing the shared backend code under `../../src` and the shared brand source under `../../assets/brand/`.

Current runtime notes:

- Positron enforces a single running instance per app-data directory with a lock file.
- Local shell runs intentionally use `desktop_django_starter.settings.packaged` so the desktop-style SQLite and staticfiles path stays exercised.
- Startup refreshes collected static files without clearing the cache-backed bundle directory on every launch.

Local commands:

- `just positron-install`
- `just positron-check`
- `just positron-start`
- `just positron-smoke`
- `just positron-icons`
- `just positron-create`
- `just positron-build`
- `just positron-package-dmg`
