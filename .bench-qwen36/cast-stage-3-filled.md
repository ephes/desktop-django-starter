# Stage 3: Django Integration Only (django-cast)

You are running inside the same target repo after Stage 2. The deterministic Stage 1
scaffold already created the Django desktop baseline: packaged settings
(`example/example_site/packaged_settings.py`), desktop middleware
(`example/example_site/desktop_middleware.py`), runtime helpers
(`example/example_site/desktop_runtime.py`, which on first run migrates an empty
desktop database; Wagtail's post-migrate then creates the default root page and
site), health + packaged static/media URL wiring in
`example/example_site/urls.py`, and desktop auto-login. Facts are recorded in
`electron/wrap-target.json`.

Do not rediscover facts already present in `electron/wrap-target.json`.

## Target facts

- Target repo: `django-cast` (a Wagtail-based podcast/blog CMS)
- Desktop manage.py path: `example/manage.py`
- Packaged manage.py path: `example/manage.py`
- Development settings module: `example_site.settings.dev`
- Packaged settings module: `example_site.packaged_settings`
- Root URL behavior: `/` serves the Wagtail root page (HTTP 200) once the runtime
  bootstrap has migrated the database and Wagtail has created its default root page.
- Auth behavior desktop mode must avoid: never block the app behind a login page;
  desktop auto-login is enabled by default.
- Seed data: no committed database; the runtime bootstrap migrates the empty desktop
  database on first request and Wagtail seeds its default root page via post-migrate.
- Note: a benign `django_vite.W001` warning about a missing Vite manifest for app
  `default` is expected and does NOT block the Wagtail root page or the smoke; it only
  affects deeper cast blog/podcast templates, which are out of scope for this stage.

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
2. `uv run python example/manage.py check --settings example_site.settings.dev`
3. `node electron/scripts/stage-backend.cjs`
4. `DJANGO_SECRET_KEY=stage-secret DESKTOP_DJANGO_BUNDLE_DIR="$PWD/.stage/backend" DESKTOP_DJANGO_APP_DATA_DIR="$PWD/.stage/runtime-data" uv run python example/manage.py check --settings example_site.packaged_settings`
5. `npm --prefix electron run smoke:packaged` — this proves `/health/` and the Wagtail
   root work through the packaged backend. Confirm the log shows `GET /health/` 200
   and `GET /` 200.

If checks 1–5 pass, do not inspect any more files. Finalize immediately.

## Report at the end

1. Files changed (state "none" if zero-edit).
2. Any remaining Electron-side dependencies that still block full smoke testing.
3. Which checks ran and whether they passed.
4. Whether Stage 3 completed with verification only or required Django-side edits.
