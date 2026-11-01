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

## Current Repo Shape

This structure stays intentionally small, but it now includes the extra shell, docs, and wrapping support files that make the current starter usable as both a teaching repo and an adaptation workflow:

```text
desktop-django-starter/
├── README.md
├── assets/
│   └── brand/
├── cli/
│   ├── src/dds/
│   └── tests/
├── docs/
│   ├── shells/
│   ├── architecture.md
│   ├── release.md
│   ├── design-guide.md
│   └── specification.md
├── scripts/
│   ├── bundled-python.cjs
│   └── stage-backend.cjs
├── shells/
│   ├── electron/
│   │   ├── assets/icons/
│   │   ├── scripts/
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
├── skills/
│   └── wrap-existing-django-in-electron/
├── manage.py
├── pyproject.toml
├── src/
│   ├── desktop_django_starter/   # Django project package
│   ├── example_app/
│   └── tasks_demo/
└── tests/
```

Notes:

- script names are illustrative; the startup and packaging behavior matters more than exact filenames
- staged packaged-backend helper scripts now live under `scripts/`
- `src/` is preferred over a flatter package layout because it maps cleanly to packaging and later app replacement
- `src/` layout means the launcher and packaging scripts must set import paths deliberately rather than relying on the current working directory
- the starter should keep Electron and Django code visibly separate

## Startup Contract

The current implementation follows this sequence:

1. Electron takes the single-instance lock; a second launch only focuses the running window and never reaches the steps below.
2. Electron chooses an open localhost port and creates a local splash window.
3. Electron reads `desktop-shell-session.json` in the app-data directory. If the previous run never marked itself finished (a crash, a force quit, power loss), Electron stops backend processes that run left behind: every backend process carries this install's random app key on its command line, so they can be found without touching other apps.
4. Electron runs migrations using either the bundled runtime or a local development interpreter. In packaged mode, the first start of a new app version prepares that version's state directory first (see Data and Files).
5. Electron starts Django.
6. Django exposes a dedicated health endpoint.
7. Electron polls that endpoint until it succeeds or times out (15 seconds).
8. Electron starts the single `db_worker` process only after Django is healthy.
9. Electron loads the main app window, then closes the splash window once the main window is ready to show.
10. When the user closes the window or quits while background tasks are running or queued (`/desktop/activity/`), Electron asks first. Quitting then stops both child processes; on Windows with explicit forced process-tree termination (`taskkill /t /f`) rather than a graceful drain. Electron marks the session finished once the children are stopped.

Every backend process (`migrate`, `seed_demo_content`, `runserver`, `db_worker`) is started through `desktop_process_guard.py`, a small standard-library launcher staged next to `manage.py`. It runs `manage.py` in the same process and adds two safety nets for the case where the shell dies without cleaning up:

- the shell keeps an open pipe on the child's stdin; when the shell process ends for any reason, the operating system closes it and the guard exits the backend process
- on Windows the guard puts the backend into a Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, so anything the backend starts dies with it

Single-instance expectation:

- packaged mode should behave as a single-instance desktop app
- Electron and Tauri currently focus the existing window instead of starting a second backend bootstrap path
- Positron now enforces the same single-instance boundary with an app-data lock file, but currently exits the second launch instead of focusing the existing window
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
- packaged state is version-isolated: the database, media and file cache live in `<app-data>/state/<app version>/` (`app.sqlite3`, `media/`, `cache/`), so an upgrade or a rollback never runs one version's code against another version's migrations or files
- the first start of a new version creates its state directory from a copy of the newest older version's state, or from the pre-versioning `<app-data>/app.sqlite3`, then runs its migrations on the copy; the SQLite copy uses the backup API, so data still in the `-wal` file after an unclean shutdown is included, and the directory appears atomically (staged, then renamed)
- older state directories are kept for rollback: going back to an older version reopens that version's own directory with its data as that version left it; changes made in the newer version do not travel back. State from a newer version is never imported into an older one, so a rollback to a version that never ran on this machine starts empty and logs a warning
- old state directories are not pruned automatically; the secret key (`secret_key`) and the shell session file stay in the app-data root
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
- packaged settings still rely on runtime environment variables for writable app data, bundle dir, localhost host/port, an optional secret-key override, and unbuffered Python output
- no shell injects a `DJANGO_SECRET_KEY`; when the environment does not provide one, packaged settings generate a per-install `DJANGO_SECRET_KEY` in the app-data directory (`secret_key`, created once with `secrets.token_urlsafe(50)` and owner-only `0600` permissions on POSIX) and reuse it on later starts, so every install signs sessions, CSRF tokens, and password-reset links with its own key; an explicit `DJANGO_SECRET_KEY` environment variable still wins
- packaged Django settings keep SQLite in per-user app data and now add desktop-oriented SQLite tuning with `transaction_mode=IMMEDIATE`, a 20-second timeout, `PRAGMA journal_mode=WAL;`, `PRAGMA synchronous=NORMAL;`, and modest cache/mmap settings
- the `/tasks/` demo uses the same SQLite database file as the web app, via the `django_tasks_db` backend tables
- task polling reconciles backend outcomes only while the current demo row is pending or running; if the worker has already finalized it, polling reloads that row and preserves its status, result, duration, and completion time, including when the backend result is missing
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

The current Electron connected updater path uses `electron-updater`, an `electron-builder` publish config, generated updater metadata, and a `Help > Check for Updates...` menu action in the Electron main process. It does not add a Django localhost update API or broaden the preload bridge. The release-readiness claim stays intentionally narrower than the implementation: the repo now records a real signed/notarized macOS packaged update dry run performed on April 12, 2026, from installed `0.1.2` to published `v0.1.4`, proving detection, download, restart/install, and `app.sqlite3` persistence, but Electron still needs a real Windows NSIS update dry run before it can be called a release-validated updater lane. Tauri now also has an experimental `tauri-plugin-updater` path that checks a configured HTTPS endpoint after the first packaged main-window load and relies on signed updater payloads rather than the Django localhost app. Positron currently stays manual-only: the repo documents local macOS DMG replacement rather than a connected updater, because there is no hosted artifact, checksum, or release-publication lane for that shell yet. For air-gapped environments, the baseline is still manual signed artifact replacement rather than background update services.

## Native Surface Area

The desktop integration should stay narrow:

- one preload bridge or application-menu action is enough for v1
- the first native action should be simple and generic, such as revealing the app-data folder
- no wide IPC API should be exposed to page code

## Shutdown Notes

Shutdown handling must be treated as a cross-platform lifecycle concern, not as a best-effort cleanup step.

- macOS and Linux can usually terminate the Django and task worker child processes with normal process signals
- Windows needs explicit handling because process-tree shutdown is less predictable
- the current Electron implementation on Windows uses explicit forced child-process tree termination via `taskkill /t /f` (from `%SystemRoot%\System32`, falling back to a plain kill if it fails)
- that forced tree kill is not a graceful drain: a running task is interrupted, which is why the shells ask before quitting while tasks are running; queued tasks stay in the database and run on the next start
- for the cases normal shutdown cannot cover, every backend process runs under `desktop_process_guard.py`: it exits when the shell's stdin pipe closes, and on Windows it holds a kill-on-close Job Object for its process tree; a later start also stops leftovers it finds by app key
- the Job Object is created by the backend process for itself and its descendants, not by Electron for its children (Node.js has no Job Object API); the stdin pipe is what ties the backend to the shell
- verified on macOS: `kill -9` of the Electron main process ends `runserver` and `db_worker` within three seconds, and a planted leftover is stopped on the next start. The Windows paths (Job Object, `taskkill`, PowerShell process listing) are implemented but not yet validated on a live Windows machine

## Deferred Areas

These are expected later if needed, but not part of the first implementation:

- production-grade task orchestration beyond the single supervised `db_worker` process used by `tasks_demo`
- Positron hosted release-lane and connected-updater work beyond the current manual-only strategy
- Tauri release publication and stronger updater hosting defaults
- multiple windows
- richer native integrations
