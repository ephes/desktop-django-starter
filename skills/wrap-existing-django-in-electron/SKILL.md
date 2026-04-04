---
name: wrap-existing-django-in-electron
description: Use this skill when a user wants to add an Electron shell around an existing Django project, especially from a different repository. It provides the workflow, guardrails, and key integration points for adapting a server-rendered Django app into a local desktop app with a bundled Python runtime.
---

# Wrap Existing Django In Electron

Use this skill when the user already has a Django project and wants to run it inside Electron without turning it into a different product.

## Read First

If you are using this skill from another Django repository, first locate this
`desktop-django-starter` repository or its published documentation. Resolve the
following paths against the starter repo, not the target repo you are changing.

Load only what you need from the starter repo:

- `docs/specification.md` for scope boundaries and non-goals
- `docs/architecture.md` for runtime contract and shutdown/update expectations
- `docs/decisions.md` for repo-specific tradeoffs
- `docs/agent-use.md` for agent guardrails

If source files are unavailable, use the published docs and `llms.txt` as the fallback context.

## Strategy: Copy and Adapt

When working from a sibling checkout of this starter (e.g., in a lab workspace), copy
reference files rather than writing from scratch.
See the Required Output Shape section below for the complete target layout.

1. Copy the starter's `shells/electron/` contents into the target's `electron/` directory.
2. Copy the starter's `scripts/` helpers (stage-backend.cjs, bundled-python.cjs,
   materialize-symlinks.cjs, prune-bundled-python-runtime.cjs) into `electron/scripts/`.
3. Adapt every copied file to the target project:
   - Settings module paths (e.g., `desktop_django_starter.settings.packaged`
     → the target's packaged settings module)
   - Project structure (e.g., `src/` layout → the target's actual layout)
   - App identity (appId, productName, secret key placeholders)
   - Relative path references (the starter has `scripts/` at repo root and
     `shells/electron/` two levels deep; wrapped projects have `electron/` one level deep)
   - The proxy wrapper scripts in `shells/electron/scripts/` (bundled-python.cjs,
     materialize-symlinks.cjs) — which just resolve a shared helper from two possible
     locations — should be replaced with the full implementations from `scripts/`,
     since wrapped projects don't need the two-location resolution.

This strategy is more reliable than writing from scratch because the starter's files are
tested and production-ready. The adaptation is where intelligence adds value.

If the starter is not available as a sibling directory, write the files from scratch
following the patterns in the starter's docs (especially `architecture.md` and `agent-use.md`) and `llms.txt`.

## Goal

Adapt the target Django repo so Electron becomes a thin desktop shell around the existing app.

Preserve:

- the Django app's existing server-rendered behavior where possible
- the existing domain model and app structure
- a narrow native integration surface

Avoid:

- rewriting the app as a SPA
- importing `djdesk` code wholesale
- adding product-level complexity that is not required for the target repo

## Workflow

1. Inspect the target Django repo.

Look for:

- `manage.py`
- settings layout
- static file handling
- SQLite or other database assumptions
- startup command and local dev commands
- whether the app already has a natural readiness URL

2. Define the Electron boundary.

Minimum boundary:

- Electron main process starts Django
- Django binds to `127.0.0.1` on a random port
- Electron waits on a health endpoint before loading the window
- Electron owns shutdown behavior

3. Make the Django runtime desktop-safe.

Check for:

- explicit development vs packaged settings
- writable database and app-data paths
- static files that still work with `DEBUG=False`
- host validation and CSRF assumptions
- **existing auth and data**: preserve existing user accounts, seed data, login URLs,
  and root redirects. Do not create new user accounts.
- **desktop auto-auth**: if the target app's useful UI is gated by auth and the desktop
  deployment is intentionally single-user/local, add desktop-only auto-auth middleware
  that logs in a configured existing user. Add this middleware to all desktop runtime
  settings (both dev and packaged), not just packaged settings — otherwise `desktop-dev`
  will still land on a login page. Do not patch `AnonymousUser` or disable
  `login_required`. Do not use this pattern for multi-user, security-sensitive, or
  network-exposed deployments. Prefer configuring the user by username or user ID
  rather than blindly picking "first user" — fall back to first existing user only
  when the target repo is clearly a single-user local demo and document that assumption.

4. Add the smallest native surface.

Prefer:

- one preload bridge or one menu action
- simple native affordances such as opening the app-data folder

5. Plan packaging and release behavior early.

Minimum concerns:

- bundled Python runtime
- Windows process behavior and writable paths
- macOS signing and notarization expectations
- manual updates for air-gapped installs

6. Add CI expectations.

At minimum:

- validate on Linux, macOS, and Windows runners
- make Windows part of the normal feedback loop, not a late-stage check

## Required Output Shape

Wrapped projects use `electron/` at the repo root. (The starter uses `shells/electron/`
because it supports multiple shells; that convention does not apply to wrapped projects.)

File layout for the target repo:

```text
target-project/
├── electron/
│   ├── main.js                              # Electron main process
│   ├── preload.cjs                          # IPC bridge (app-data folder)
│   ├── package.json                         # Electron deps and npm scripts
│   ├── electron-builder.config.cjs          # top-level builder config
│   └── scripts/
│       ├── launch-electron.cjs              # CLI launcher with env setup
│       ├── bundled-python.cjs               # Python runtime manifest/resolution
│       ├── stage-backend.cjs                # backend staging for packaged mode
│       ├── electron-builder-config.cjs      # builder config details
│       ├── materialize-symlinks.cjs         # portability: symlinks → copies
│       └── prune-bundled-python-runtime.cjs # strip tkinter/idle from bundle
├── .stage/                                  # (gitignored) staged backend
└── .github/workflows/
    └── desktop-packages.yml                 # cross-platform packaging CI
```

Django-side additions (paths depend on the target project's layout):

- `base_settings.py` — shared settings with `DEBUG=False` defaults
- modified `settings.py` — imports from `base_settings`, adds dev overrides
- `packaged_settings.py` — imports from `base_settings`, adds packaged runtime config
- `runtime.py` — desktop runtime helpers (bundle dir, app data dir, host/port)
- health endpoint view at `/health/`
- desktop home view at `/` that redirects to the app's main URL (or configure Electron
  to load the app's main URL directly in `main.js`)
- URL wiring for new views
- `STATIC_ROOT`, `STATICFILES_DIRS` in base settings
- **Packaged static/media serving in URLs.** In packaged mode (`DEBUG=False`), Django's
  `staticfiles` app does not serve files automatically. The URLconf must explicitly
  serve `STATIC_URL` and `MEDIA_URL` using `django.views.static.serve` when
  `DESKTOP_PACKAGED_RUNTIME` is set. Without this, all CSS/JS/images return 404
  in the packaged app. Example:
  ```python
  if settings.DEBUG:
      urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
  elif getattr(settings, "DESKTOP_PACKAGED_RUNTIME", False):
      urlpatterns += [
          re_path(r"^static/(?P<path>.*)$", serve, {"document_root": settings.STATIC_ROOT}),
          re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
      ]
  ```

**Settings split — use flat files, not a package.** Create `base_settings.py` and
`packaged_settings.py` as sibling files next to the existing `settings.py`. Do NOT
convert `settings.py` into a Python package (`settings/__init__.py`). A package layout
causes import side effects: packaged mode imports `packaged_settings.py` which may
trigger `settings/__init__.py`, pulling in dev-only dependencies like `django_extensions`
that are not available in the bundled runtime. The flat file approach avoids this:

```python
# base_settings.py — shared, DEBUG=False, no dev-only deps
# settings.py — from .base_settings import *; DEBUG=True; add dev deps
# packaged_settings.py — from .base_settings import *; packaged runtime config
```

**Root URL — the Electron window must load actual app content.** Check if the
target project already has a root URL handler, login configuration, or redirect
logic. If it does, preserve it — do not replace it with new views or auth flows.

If the project does not have a root handler, either:
1. Configure `main.js` to load the app's main URL directly
2. Add a simple redirect view at `/`

If auth-gated views block access (see desktop auto-auth guidance in the workflow
section above), the auto-auth middleware handles this — do not add login templates
or alternative auth flows. The existing users and seed data (e.g., in a committed
`db.sqlite3`) should work as-is in the desktop shell.

The full redirect chain must terminate at a 200, not a 404 at any step.

Verify by following the full redirect chain: the final response must be 200.

**Node test harness.** Copy and adapt the starter's `shells/electron/scripts/*.test.cjs`
files. The `electron/package.json` must include a `test` script (`node --test ./scripts/*.test.cjs`).
These tests validate the bundled-python manifest logic and builder config, catching
adaptation errors before runtime. When adapting tests, update assertions to match the
target project's values — especially `settingsModule` (e.g., `example.packaged_settings`),
`appId`, `productName`, and `sourceRoot`. A test that still asserts the starter's values
passes but does not catch regressions in the adapted code.

Build/dev justfile targets:

- `desktop-dev` — start Electron with Django in development mode
- `desktop-dev-smoke` — boot dev mode, verify `/health/` responds 200, exit
- `desktop-stage` — stage backend with bundled Python
- `desktop-smoke` — boot packaged mode, verify, exit
- `desktop-dist` — build distributable installer
- `desktop-dist-dir` — build unpacked distributable

`.gitignore` additions: `.stage/`, `electron/dist/`, `electron/node_modules/`

## Validation Checklist

- Django starts on a random localhost port
- Electron waits for readiness instead of racing page load
- packaged mode does not assume `DEBUG=True`
- shutdown works on Windows as well as macOS/Linux
- update docs include connected and air-gapped/manual paths
- CI exercises Windows, macOS, and Linux

## Self-Verification (for unattended runs)

When running unattended, verify your own work before finishing. All checks must be
bounded — no long-running processes.

1. Run the target project's existing test suite. It must still pass.
2. Run `just desktop-dev-smoke`. This boots the Electron shell, confirms `/health/`
   responds 200, and exits. If this target is missing or fails, report it as a failure.
3. Verify the desktop window lands on real content. Follow the full redirect chain
   from the URL that Electron loads (either `/` or the app's main URL). Every step
   must resolve — the final response must be 200, not 404. Check this with Django's
   test client: `Client().get("/resume/", follow=True)` should end at status 200.
4. Run `npm --prefix electron test` to confirm the Node-side test harness passes.
5. If any check fails, report what failed and do not continue past the failed step.

Packaged-mode verification (`just desktop-smoke`) is a separate concern — do not
attempt it in the same unattended run unless explicitly requested.
