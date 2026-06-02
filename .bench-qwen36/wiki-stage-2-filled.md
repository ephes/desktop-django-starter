# Stage 2: Electron Adaptation Only (django-wiki)

You are running inside a target Django repo that has ALREADY had the deterministic
Stage 1 scaffold applied. The Electron skeleton is already copied into `electron/`
and the most fragile identity/path boilerplate is already rewritten. Deterministic
Django-side changes outside `electron/` (settings, urls, middleware, runtime helpers)
are EXPECTED Stage 1 output — ignore them in Stage 2.

Do not explore the whole repo. Do not re-create the `electron/` directory.

## Target facts

- Target repo: `django-wiki`
- Desktop manage.py path: `testproject/manage.py`
- Development Django settings module: `testproject.settings`
- Planned packaged settings module: `testproject.packaged_settings`
- App source directories packaged mode must account for: `testproject`, `src`
- Root URL behavior: `/` serves the wiki root article (HTTP 200)
- Theme/background direction: light background (`#ffffff`)

## Your task

Adapt only the Electron-side scaffold for this target repo. This stage is
verification-first and stop-early:

1. Run the narrow checks below first.
2. If all checks pass, STOP IMMEDIATELY and report a zero-edit Stage 2 success.
3. Only if a check fails may you read the minimum `electron/` files needed to diagnose.
4. Only edit a file if a concrete Electron-side mismatch remains.

Allowed writes: only files under `electron/`.
Forbidden writes: any file outside `electron/`.

Do NOT add Django settings, middleware, URLs, or templates in this stage.
Do NOT read extra `electron/` files after the verification bundle passes.

## Verification (run these with your bash tool, in order)

1. `git status --short`
2. `node --check electron/main.js`
3. `node --check electron/scripts/launch-electron.cjs`
4. `node --test electron/scripts/*.test.cjs`

If checks 1–4 pass, do not inspect any more files. Finalize immediately.

## Report at the end

1. Files changed (state "none" if zero-edit).
2. Any known deferred Django-side dependencies for Stage 3.
3. Which checks ran and whether they passed.
