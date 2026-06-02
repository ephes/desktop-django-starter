# Stage 3: Django Integration Only (django-resume)

You are running inside the same target repo after Stage 2. The deterministic Stage 1
scaffold already created the Django desktop baseline: packaged settings
(`example/example/packaged_settings.py`), desktop middleware
(`example/example/desktop_middleware.py`), runtime helpers
(`example/example/desktop_runtime.py`), health + packaged static/media URL wiring in
`example/example/urls.py`, desktop auto-login defaults, seed DB/media bootstrap, and a
"Back to all resumes" link in the headwind `resume_detail.html` and `resume_cv.html`
templates. Facts are recorded in `electron/wrap-target.json`.

Do not rediscover facts already present in `electron/wrap-target.json`.

## Target facts

- Target repo: `django-resume`
- Desktop manage.py path: `example/manage.py`
- Packaged manage.py path: `example/manage.py`
- Development settings module: `example.settings`
- Packaged settings module: `example.packaged_settings`
- Root URL behavior: `/` redirects to `/resume/`
- Auth behavior desktop mode must avoid: never land on a login page; desktop
  auto-login is enabled by default (single-user fallback).
- Seed data/media: seed DB at `example/db.sqlite3`, seed media at `example/media`.

## Your task

Adapt only the Django-side integration for desktop mode. This stage is
verification-first and stop-early:

1. Run the narrow verification commands below first.
2. If all checks pass, STOP IMMEDIATELY and report a zero-edit Stage 3 success.
3. Only if a check fails may you read the minimum Django files needed to diagnose.
4. Only adjust a proven pattern when a failed check shows the scaffold is still wrong.

Forbidden writes: `electron/**` (unless a tiny unavoidable compatibility fix, explained).
Do NOT create new user accounts. Preserve existing auth data.
Do NOT read extra files after the verification bundle passes.

## Verification (run these with your bash tool, in order)

1. `git status --short`
2. `uv run python example/manage.py check --settings example.settings`
3. `node electron/scripts/stage-backend.cjs`
4. `DJANGO_SECRET_KEY=stage-secret DESKTOP_DJANGO_BUNDLE_DIR="$PWD/.stage/backend" DESKTOP_DJANGO_APP_DATA_DIR="$PWD/.stage/runtime-data" uv run python example/manage.py check --settings example.packaged_settings`
5. `npm --prefix electron run smoke:packaged` — this proves `/health/`, the
   authenticated app root (`/` → `/resume/`), packaged static serving, and seed media
   all work through the packaged backend. Confirm the log shows `GET /health/` 200,
   `GET /` 302, and `GET /resume/` 200.

If checks 1–5 pass, do not inspect any more files. Finalize immediately.

## Report at the end

1. Files changed (state "none" if zero-edit).
2. Any remaining Electron-side dependencies that still block full smoke testing.
3. Which checks ran and whether they passed.
4. Whether Stage 3 completed with verification only or required Django-side edits.
