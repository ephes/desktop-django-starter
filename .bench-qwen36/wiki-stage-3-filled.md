# Stage 3: Django Integration Only (django-wiki)

You are running inside the same target repo after Stage 2. The deterministic Stage 1
scaffold already created the Django desktop baseline: packaged settings
(`testproject/testproject/packaged_settings.py`), desktop middleware
(`testproject/testproject/desktop_middleware.py`), runtime helpers
(`testproject/testproject/desktop_runtime.py`, which on first run migrates an empty
desktop database and seeds a desktop superuser plus the django-wiki root article),
health + packaged static/media URL wiring in `testproject/testproject/urls.py`, and
desktop auto-login. Facts are recorded in `electron/wrap-target.json`.

Do not rediscover facts already present in `electron/wrap-target.json`.

## Target facts

- Target repo: `django-wiki`
- Desktop manage.py path: `testproject/manage.py`
- Packaged manage.py path: `testproject/manage.py`
- Development settings module: `testproject.settings`
- Packaged settings module: `testproject.packaged_settings`
- Root URL behavior: `/` serves the wiki root article (HTTP 200) once the runtime
  bootstrap has created it.
- Auth behavior desktop mode must avoid: never block the app behind a login page;
  desktop auto-login is enabled by default.
- Seed data: no committed database; the runtime bootstrap migrates and seeds the
  superuser + wiki root article on first request.

## Your task

Adapt only the Django-side integration for desktop mode. This stage is
verification-first and stop-early:

1. Run the narrow verification commands below first.
2. If all checks pass, STOP IMMEDIATELY and report a zero-edit Stage 3 success.
3. Only if a check fails may you read the minimum Django files needed to diagnose.
4. Only adjust a proven pattern when a failed check shows the scaffold is still wrong.

Forbidden writes: `electron/**` (unless a tiny unavoidable compatibility fix, explained).
Do NOT create additional user accounts beyond what the bootstrap already seeds.
Do NOT read extra files after the verification bundle passes.

## Verification (run these with your bash tool, in order)

1. `git status --short`
2. `uv run python testproject/manage.py check --settings testproject.settings`
3. `node electron/scripts/stage-backend.cjs`
4. `DJANGO_SECRET_KEY=stage-secret DESKTOP_DJANGO_BUNDLE_DIR="$PWD/.stage/backend" DESKTOP_DJANGO_APP_DATA_DIR="$PWD/.stage/runtime-data" uv run python testproject/manage.py check --settings testproject.packaged_settings`
5. `npm --prefix electron run smoke:packaged` — this proves `/health/` and the wiki
   root work through the packaged backend. Confirm the log shows `GET /health/` 200
   and `GET /` 200.

If checks 1–5 pass, do not inspect any more files. Finalize immediately.

## Report at the end

1. Files changed (state "none" if zero-edit).
2. Any remaining Electron-side dependencies that still block full smoke testing.
3. Which checks ran and whether they passed.
4. Whether Stage 3 completed with verification only or required Django-side edits.
