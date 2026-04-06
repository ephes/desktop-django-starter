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
3. For cross-platform packaging CI, use the starter's `.github/workflows/desktop-packages.yml`
   as a starting point and adapt it to the target project's triggers, artifact names,
   signing inputs, and path layout.
4. Adapt every copied file to the target project:
   - Settings module paths (e.g., `desktop_django_starter.settings.packaged`
     → the target's packaged settings module)
   - Project structure (e.g., `src/` layout → the target's actual layout)
   - App identity (appId, productName, secret key placeholders)
   - BrowserWindow `backgroundColor` in `main.js` — the starter uses a dark theme
     (`#222121`). Check the target app's actual color scheme and match it. A light-themed
     app needs a light background (e.g., `#ffffff`), otherwise the window flashes dark
     before the page loads.
   - Relative path references (the starter has `scripts/` at repo root and
     `shells/electron/` two levels deep; wrapped projects have `electron/` one level deep).
     Concrete example: electron-builder resolves `extraResources.from` relative to the
     project directory (where `package.json` lives), not relative to the script that
     generates the config. The starter's `shells/electron/` is two levels from `.stage/`,
     so the path is `../../.stage/backend`; a wrapped project's `electron/` is one level
     from `.stage/`, so it becomes `../.stage/backend`
   - The proxy wrapper scripts in `shells/electron/scripts/` (bundled-python.cjs,
     materialize-symlinks.cjs) — which just resolve a shared helper from two possible
     locations — should be replaced with the full implementations from `scripts/`,
     since wrapped projects don't need the two-location resolution.

This strategy is more reliable than writing from scratch because the starter's files are
tested and production-ready. The adaptation is where intelligence adds value.

Common adaptation decisions (resolve these during step 1 inspection):

| Situation | Approach |
|-----------|----------|
| `manage.py` at repo root | `cwd` in the manage invocation is the repo root |
| `manage.py` in a subdirectory (e.g., `example/`) | `cwd` must point to that subdirectory; adjust backend root accordingly. Note: `uv run` walks up to find `pyproject.toml`, so it works even when cwd differs from the project root |
| Existing root URL handler or redirect | Preserve it; do not add a competing view at `/` |
| No root URL handler | Either load the app's main URL in `main.js` directly, or add a redirect view |
| Login-gated views, single-user local app | Add auto-auth middleware gated by env var (see step 3) |
| Public views, no auth required | No auto-auth needed |
| Committed `db.sqlite3` with seed data | Treat as immutable input; copy to writable app-data path on first run (see step 3) |
| No committed database (SQLite-backed desktop app) | Migrations create it at the writable app-data path |
| Installable library with separate example project (e.g., `src/` + `example/`) | Dev mode works because the package is already installed in the venv. But `stage-backend.cjs` must build and install a wheel into the bundled Python — copying `src/` alone won't make the package importable in packaged mode |
| Existing settings as a package (`settings/` directory) | Place flat desktop settings files as siblings to the package directory. Import from the package's base module directly (e.g., `from myproject.settings.base import *`), bypassing the package's `__init__.py` |

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

Also assess navigation assumptions and browser-dependent affordances:

- Does the app have persistent in-app navigation (navbar, sidebar, breadcrumbs)?
- Do important user flows depend on browser back/forward to reach prior pages?
- Can the root URL or login redirect strand the user on a page with no way out?
- Do any links open new tabs/windows (`target="_blank"` or JavaScript `window.open`)?
- What would a user lose if the browser chrome disappeared entirely?

Record the findings — they inform the native surface decisions in step 4.

After inspecting, record these values — they drive the most error-prone
adaptations in `main.js` and the settings split:

- Path to the app's `manage.py` relative to repo root (may not be at root, e.g., `example/manage.py`).
  Some repos have multiple `manage.py` files (e.g., one at root for tests, one in a subdirectory
  for the actual project) — identify which one the desktop app should launch
- Source directories that contain Django app code (e.g., `src/`, `example/`)
- Django settings module for development (e.g., `example.settings`)
- Name for the packaged settings module you will create (e.g., `example.packaged_settings`)
- App directories that must exist in the staged backend bundle so packaged startup validation passes
- Whether the repo has a committed `db.sqlite3` or other seed data

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
  Gate the middleware with an environment variable (e.g., `DESKTOP_AUTO_LOGIN_ENABLED=1`)
  rather than making it always-on. Have `main.js` set this variable in the Django
  environment so the middleware only activates when launched from the desktop shell —
  never when running the Django app standalone or in tests.
  Verify that the chosen user can actually perform the app's primary authenticated
  workflow, not just load the landing page. For content apps with seeded roles,
  fixtures, or object-level locks, confirm the user is both authenticated and
  authorized for the intended desktop use case (e.g., a wiki user who can edit,
  not just view).
- **seed data**: if the target repo has a committed `db.sqlite3` or media files,
  treat them as immutable inputs. In packaged settings, copy the seed database to
  the writable app-data directory on first run or when the writable copy is missing,
  rather than writing to the committed file. This prevents smoke tests and desktop-dev
  runs from dirtying the working tree. If the project uses fixtures (JSON/YAML via
  `manage.py loaddata`) instead of a committed database, treat them the same way —
  load them into the writable app-data database on first run or initialization, not
  on every startup.

4. Add the smallest native surface.

Prefer:

- one preload bridge or one menu action
- simple native affordances such as opening the app-data folder
- the starter's splash screen is optional — skip it for small apps where startup is fast enough
  that the window appears quickly on its own

Using the navigation assessment from step 1, restore only the missing
affordances the app actually needs. The right fix depends on the target app:

- **Nothing** — if the app already has persistent navigation and no flows
  depend on browser back/forward.
- **Electron application menu** — add a Go or Navigation menu with Back,
  Forward, and an entry to the app's primary app URL. Use platform-standard
  shortcuts (macOS: Cmd+[ and Cmd+], Windows/Linux: Alt+Left and
  Alt+Right). Appropriate when the app has some navigation but users need
  native back/forward affordances to move between views.
- **Django-side navigation element** — add a minimal nav bar, breadcrumb, or
  home link via base template extension or template override. Appropriate
  when the app has no persistent navigation at all and an Electron menu
  alone wouldn't make it usable.
- **Combination** — menu shortcuts for back/forward plus a Django-side nav
  element. Appropriate when neither alone is sufficient.

The agent decides which approach fits based on the inspection findings. The
goal is minimum intervention that makes the wrapped app navigable.

For links that open new tabs or windows (`target="_blank"`, `window.open`),
decide whether they should stay inside the main window or open in the system
browser. Managed secondary Electron windows are intentionally out of scope
for the wrapping skill — the choice is in-app or system browser, not a
custom popup. Make that decision explicitly in Electron's main process,
typically with `setWindowOpenHandler` and related navigation guards, rather
than relying on default behavior. Prefer handling new-window and
external-navigation policy in Electron's main process. Only change Django
templates when the app's internal navigation structure itself needs repair.

If an application menu is added and existing preload actions (like "reveal
app data") aren't referenced in the app's templates, the agent may
consolidate them into the menu.

If navigation code is added, add a focused smoke check or Node test where
practical.

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
- root URL handling: if the project already has a root handler or redirect, preserve it;
  if not, either configure `main.js` to load the app's main URL directly or add a
  simple redirect view at `/`
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
   test client using the URL Electron loads, e.g., `Client().get("/", follow=True)`
   should end at status 200. If ALLOWED_HOSTS rejects the test client's default
   `testserver` hostname, add it to the desktop settings.
   If desktop auto-auth is enabled, also verify one representative authenticated
   action that matches the app's primary purpose — e.g., confirm the auto-auth user
   can reach an edit or create page, not just view the landing page.
4. Run `npm --prefix electron test` to confirm the Node-side test harness passes.
5. If any check fails, report what failed and do not continue past the failed step.

Packaged-mode verification (`just desktop-smoke`) is a separate concern — do not
attempt it in the same unattended run unless explicitly requested.
