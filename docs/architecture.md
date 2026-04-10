# Architecture Notes

Status: intended implementation shape, with the runnable development slice, staged bundled-runtime contract, sign/notarization-aware Electron packaging workflow, minimal Electron connected updater path, and experimental Tauri plus Positron shells now in place

## Runtime Model

The expected runtime is intentionally simple:

```{mermaid}
flowchart TD
    A[Electron main process]
    B[Launcher script]
    C[Django app on 127.0.0.1:<random-port>]
    D[Task runner process]
    E[SQLite in writable app-data path]
    F[Health endpoint returns 200]
    G[Electron BrowserWindow loads local URL]

    A -->|starts bundled Python runtime| B
    B -->|starts Django| C
    B -->|starts db_worker| D
    C --> E
    D --> E
    C --> F
    F -->|readiness confirmed| G
```

Key expectations:

- Electron owns process startup and shutdown
- Django and the task worker are treated as local backend processes, not as remote services
- Electron binds Django to `127.0.0.1` on a random port before opening the renderer
- the renderer loads normal Django pages over localhost
- Electron now adds a per-session shell-to-Django auth token on top of the localhost bind: the main process passes `DESKTOP_DJANGO_AUTH_TOKEN` to Django and injects `X-Desktop-Django-Token` only for the exact local Django origin
- Tauri and Positron use the same Django token setting but acquire an HttpOnly same-origin cookie by first loading `/desktop-auth/bootstrap/?token=...&next=/`; Django validates the token, sets the cookie, and redirects to the app URL without the token
- the shell token is a channel check for localhost requests, not a CSRF replacement and not a value exposed through preload, a shell bridge, or normal page JavaScript
- Tauri and Positron use the bootstrap cookie flow because their current web view paths do not have an Electron-equivalent external-localhost per-request header injection path
- SQLite lives in a writable per-user app-data directory and stores both app data and task queue rows

Current shell split note:

- Electron remains the baseline shell and the most complete release-oriented packaging lane
- Tauri now also has an experimental GitHub-hosted artifact lane, while keeping the same staged-backend subprocess model
- Tauri keeps the same staged-backend subprocess model locally
- Positron keeps shell-local ownership of an in-process Django server plus an in-process worker thread

## Draft Repo Shape

This structure is intentionally small and close to normal Django conventions:

```text
desktop-django-starter/
├── README.md
├── assets/
│   └── brand/
├── docs/
│   ├── specification.md
│   ├── architecture.md
│   └── decisions.md
├── scripts/
│   ├── bundled-python.cjs
│   └── stage-backend.cjs
├── shells/
│   ├── electron/
│   │   ├── assets/icons/
│   │   ├── main.js
│   │   ├── preload.cjs
│   │   └── package.json
│   ├── tauri/
│   │   ├── package.json
│   │   ├── scripts/
│   │   ├── src/
│   │   └── src-tauri/
│   └── positron/
│       ├── pyproject.toml
│       ├── scripts/
│       ├── resources/
│       └── src/
├── manage.py
├── pyproject.toml
├── src/
│   ├── desktop_django_starter/   # Django project package
│   └── example_app/
└── tests/
```

Notes:

- script names are illustrative; the startup and packaging behavior matters more than exact filenames
- staged packaged-backend helper scripts now live under `scripts/`
- `src/` is preferred over a flatter package layout because it maps cleanly to packaging and later app replacement
- `src/` layout means the launcher and packaging scripts must set import paths deliberately rather than relying on the current working directory
- the starter should keep Electron and Django code visibly separate

## Startup Contract

The eventual implementation should follow this sequence:

1. Electron creates a local splash window immediately after `app.whenReady()`.
2. Electron chooses an open localhost port.
3. Electron runs migrations using either the bundled runtime or a local development interpreter.
4. Electron starts Django.
5. Django exposes a dedicated health endpoint.
6. Electron polls that endpoint until it succeeds or times out.
7. Electron starts the single `db_worker` process only after Django is healthy.
8. Electron loads the main app window only after both backend processes have started cleanly, then closes the splash window once the main window is ready to show.
9. Closing the desktop app shuts down both child processes; on Windows, the current Electron implementation does this with explicit forced process-tree termination rather than a graceful drain.

Single-instance expectation:

- packaged mode should behave as a single-instance desktop app
- a second launch should focus the existing window instead of starting a second backend bootstrap path
- this avoids concurrent startup work against the same per-user SQLite database, including migration races during app launch

Health endpoint expectation:

- use a dedicated route such as `/health/`
- return HTTP 200 once Django startup is complete
- keep the response simple and stable

## Runtime Modes

The implementation should document the distinction between:

- development mode, where Electron may start Django with the developer's local Python environment
- packaged mode, where Electron starts Django from the bundled runtime with production-like local settings

The settings split should make these differences explicit:

- development can optimize for debug ergonomics
- packaged mode should assume `DEBUG=False`
- packaged mode should use writable per-user data paths
- packaged mode should rely on collected static assets rather than Django development conveniences

## Data and Files

Expected persistence rules:

- SQLite is the only database in starter v1
- packaged apps write the database under the platform user-data directory, not inside a read-only app bundle
- static files are collected as part of packaging, not generated on end-user machines
- packaged mode needs an explicit static-file strategy that works when `DEBUG=False`

Current expected direction:

- use Django-side static file serving in the simplest acceptable form for v1, rather than introducing an additional asset-serving layer in Electron unless it proves necessary
- the staged local bundle now mirrors the future packaged layout by keeping the backend payload together and staging the interpreter under `backend/python/`
- app icon source-of-truth now lives under `assets/brand/`, with generated Electron outputs written into `shells/electron/assets/icons/`, generated Tauri outputs written into `shells/tauri/src-tauri/icons/`, and generated Positron outputs written into `shells/positron/resources/`
- the example app base template loads the Play font from Google Fonts via an external stylesheet link; in packaged or air-gapped mode the request will silently fail and the CSS font stack falls back to Helvetica Neue / Arial / sans-serif

Current staged backend contract:

- the shared staged backend is materialized under `.stage/backend/` at the repo root during local packaged-like builds
- `backend/manage.py` stays at the bundle root
- `backend/src/` keeps the normal source layout
- `backend/python/` contains the bundled interpreter and installed dependencies
- `backend/staticfiles/` contains collected assets for `DEBUG=False`
- `backend/runtime-manifest.json` records the interpreter path and launcher metadata

Current launcher contract:

- Electron and Tauri packaged mode resolve the interpreter from `backend/runtime-manifest.json`
- Electron and Tauri then run `manage.py` from `backend/` for both `runserver` and `db_worker`
- packaged settings still rely on runtime environment variables for writable app data, bundle dir, localhost host/port, secret key, and unbuffered Python output
- Electron, Tauri, and Positron all use the same fallback `DJANGO_SECRET_KEY` only when the environment does not provide one, so local packaged-like startup stays simple without claiming that the fallback value is a release-grade secret
- packaged Django settings keep SQLite in per-user app data and now add desktop-oriented SQLite tuning with `transaction_mode=IMMEDIATE`, a 20-second timeout, `PRAGMA journal_mode=WAL;`, `PRAGMA synchronous=NORMAL;`, and modest cache/mmap settings
- the `/tasks/` demo uses the same SQLite database file as the web app, via the `django_tasks_db` backend tables
- shell-local wrappers such as `shells/electron/scripts/bundled-python.cjs` are allowed to resolve shared helpers from two locations: a packaged-app copy first, then a repo-relative source path for local development
- the Tauri shell keeps its subprocess supervision in Rust under `shells/tauri/src-tauri/src/lib.rs` instead of forcing a cross-shell launcher abstraction
- the Tauri shell now also owns its own shell-local splash window under `shells/tauri/src/splash.html`, shown while backend startup runs on a background thread
- the Positron shell keeps its runtime under `shells/positron/src/desktop_django_starter_positron/`, imports the shared Django code from repo `src/`, and starts the optional task worker in-process instead of using the Electron/Tauri subprocess contract
- Positron does not claim packaged splashscreen parity on macOS and does not add a GitHub Actions artifact lane in this slice

## Release and Update Model

The first implementation does not need a full auto-update system, but it does need a credible release and update story.

- connected environments should be able to replace the app using signed release artifacts from a normal release channel
- air-gapped environments should be able to move signed artifacts through an approved offline transfer path and install them manually
- update docs should describe what artifact an operator moves, how they verify it, and what local state should survive the reinstall
- local packaging should still work without release credentials, producing unsigned artifacts for teaching and local validation
- the GitHub Actions packaging workflow should consume signing credentials only when they are present, rather than making secrets a baseline requirement for every build

The current Electron connected updater path uses `electron-updater`, an `electron-builder` publish config, generated updater metadata, and a `Help > Check for Updates...` menu action in the Electron main process. It does not add a Django localhost update API or broaden the preload bridge. Tauri and Positron connected auto-update remain deferred. For air-gapped environments, the baseline is still manual signed artifact replacement rather than background update services.

## Native Surface Area

The desktop integration should stay narrow:

- one preload bridge or application-menu action is enough for v1
- the first native action should be simple and generic, such as revealing the app-data folder
- no wide IPC API should be exposed to page code

## Shutdown Notes

Shutdown handling must be treated as a cross-platform lifecycle concern, not as a best-effort cleanup step.

- macOS and Linux can usually terminate the Django and task worker child processes with normal process signals
- Windows needs explicit handling because process-tree shutdown is less predictable
- the current Electron implementation on Windows uses explicit forced child-process tree termination via `taskkill /t /f`
- that forced tree kill is acceptable for this starter, but it is not the same as a graceful drain, a dedicated local shutdown endpoint, or a Job Object-based production approach
- because Windows is a required proof point, reliable shutdown is part of the starter contract

## Deferred Areas

These are expected later if needed, but not part of the first implementation:

- production-grade task orchestration beyond the single supervised `db_worker` process used by `tasks_demo`
- Tauri and Positron connected auto-update automation
- multiple windows
- richer native integrations
