# Architecture Notes

Status: intended implementation shape, with the runnable development slice, staged bundled-runtime contract, and sign/notarization-aware packaging workflow now in place

## Runtime Model

The expected runtime is intentionally simple:

```{mermaid}
flowchart TD
    A[Electron main process]
    B[Launcher script]
    C[Django app on 127.0.0.1:<random-port>]
    D[SQLite in writable app-data path]
    E[Health endpoint returns 200]
    F[Electron BrowserWindow loads local URL]

    A -->|starts bundled Python runtime| B
    B -->|starts Django| C
    C --> D
    C --> E
    E -->|readiness confirmed| F
```

Key expectations:

- Electron owns process startup and shutdown
- Django is treated as a local backend, not as a remote service
- the renderer loads normal Django pages over localhost
- SQLite lives in a writable per-user app-data directory

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

1. Electron chooses an open localhost port.
2. Electron starts Django using either the bundled runtime or a local development interpreter.
3. Django exposes a dedicated health endpoint.
4. Electron polls that endpoint until it succeeds or times out.
5. Electron loads the app window only after Django is ready.
6. Closing the desktop app shuts down the Django child process cleanly.

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

Current staged backend contract:

- `backend/manage.py` stays at the bundle root
- `backend/src/` keeps the normal source layout
- `backend/python/` contains the bundled interpreter and installed dependencies
- `backend/staticfiles/` contains collected assets for `DEBUG=False`
- `backend/runtime-manifest.json` records the interpreter path and launcher metadata

Current launcher contract:

- Electron packaged mode resolves the interpreter from `backend/runtime-manifest.json`
- Electron then runs `manage.py` from `backend/`
- packaged settings still rely on runtime environment variables for writable app data, bundle dir, localhost host/port, secret key, and unbuffered Python output

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

- macOS and Linux can usually terminate the child process with normal process signals
- Windows needs explicit handling because process-tree shutdown is less predictable
- the implementation should document whether shutdown uses child-process tree termination, a dedicated local shutdown path, or another narrow mechanism
- because Windows is a required proof point, reliable shutdown is part of the starter contract

## Deferred Areas

These are expected later if needed, but not part of the first implementation:

- background-task runner integration
- connected auto-update automation
- multiple windows
- richer native integrations
