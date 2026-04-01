# Architecture Notes

Status: intended implementation shape, with the runnable development slice, staged bundled-runtime contract, and sign/notarization-aware packaging workflow now in place

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
- the renderer loads normal Django pages over localhost
- SQLite lives in a writable per-user app-data directory and stores both app data and task queue rows

## Draft Repo Shape

This structure is intentionally small and close to normal Django conventions:

```text
desktop-django-starter/
├── README.md
├── docs/
│   ├── specification.md
│   ├── architecture.md
│   └── decisions.md
├── electron/
│   ├── main.js
│   ├── preload.cjs
│   └── package.json
├── manage.py
├── pyproject.toml
├── src/
│   ├── desktop_django_starter/   # Django project package
│   └── example_app/
└── tests/
```

Notes:

- script names are illustrative; the startup and packaging behavior matters more than exact filenames
- staged packaged-backend helper scripts now live under `electron/scripts/`
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
9. Closing the desktop app shuts down both child processes cleanly.

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
- the example app base template loads the Play font from Google Fonts via an external stylesheet link; in packaged or air-gapped mode the request will silently fail and the CSS font stack falls back to Helvetica Neue / Arial / sans-serif

Current staged backend contract:

- `backend/manage.py` stays at the bundle root
- `backend/src/` keeps the normal source layout
- `backend/python/` contains the bundled interpreter and installed dependencies
- `backend/staticfiles/` contains collected assets for `DEBUG=False`
- `backend/runtime-manifest.json` records the interpreter path and launcher metadata

Current launcher contract:

- Electron packaged mode resolves the interpreter from `backend/runtime-manifest.json`
- Electron then runs `manage.py` from `backend/` for both `runserver` and `db_worker`
- packaged settings still rely on runtime environment variables for writable app data, bundle dir, localhost host/port, secret key, and unbuffered Python output
- the `/tasks/` demo uses the same SQLite database file as the web app, via the `django_tasks_db` backend tables

## Release and Update Model

The first implementation does not need a full auto-update system, but it does need a credible release and update story.

- connected environments should be able to replace the app using signed release artifacts from a normal release channel
- air-gapped environments should be able to move signed artifacts through an approved offline transfer path and install them manually
- update docs should describe what artifact an operator moves, how they verify it, and what local state should survive the reinstall
- local packaging should still work without release credentials, producing unsigned artifacts for teaching and local validation
- the GitHub Actions packaging workflow should consume signing credentials only when they are present, rather than making secrets a baseline requirement for every build

For connected auto-update work after v1, the expected direction is an Electron-compatible update feed. For air-gapped environments, the baseline is manual signed artifact replacement rather than background update services.

## Native Surface Area

The desktop integration should stay narrow:

- one preload bridge or application-menu action is enough for v1
- the first native action should be simple and generic, such as revealing the app-data folder
- no wide IPC API should be exposed to page code

## Shutdown Notes

Shutdown handling must be treated as a cross-platform lifecycle concern, not as a best-effort cleanup step.

- macOS and Linux can usually terminate the Django and task worker child processes with normal process signals
- Windows needs explicit handling because process-tree shutdown is less predictable
- the implementation should document whether shutdown uses child-process tree termination, a dedicated local shutdown path, or another narrow mechanism
- because Windows is a required proof point, reliable shutdown is part of the starter contract

## Deferred Areas

These are expected later if needed, but not part of the first implementation:

- production-grade task orchestration beyond the single supervised `db_worker` process used by `tasks_demo`
- connected auto-update automation
- multiple windows
- richer native integrations
