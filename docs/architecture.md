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

Shell authentication runs before CSRF validation. Both header and cookie
credentials still require a valid Django CSRF token for mutations. When the
browser sends an Origin header, it must match an allowed origin. On plain HTTP,
Django also accepts token-valid requests without an Origin header. Integration tests use `Client(enforce_csrf_checks=True)` to exercise
item deletion/clearing and task creation/clearing: missing or invalid CSRF and
foreign origins leave both application rows and queue rows unchanged, valid
same-origin requests succeed, and requests without shell credentials are denied.

The credential-bearing bootstrap route sets `Cache-Control: private, no-store`
and `Referrer-Policy: no-referrer` on success and failure, including when no
launch token is configured. Safe relative redirects and the HttpOnly,
`SameSite=Strict` cookie still apply. These headers govern response storage and
referrer forwarding; they do not promise to erase web view navigation history.

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
- predecessor selection uses public SemVer parsing plus the narrow Positron a/b/rc mapping described in [the release guide](release.md#upgrades-and-rollbacks): `0.2.0-rc.2 < 0.2.0-rc.10 < 0.2.0`; unsupported current or candidate versions stop startup with recovery guidance
- SQLite sources open through an escaped read-only URI; a disappeared or invalid source fails initialization without recreating it or publishing state
- SQLite backup has a total monotonic 30-second startup budget, including busy retries and page copying; failure closes connections and removes only unpublished staging
- the `unversioned` build/local fallback has no release ordering and only imports legacy root state

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
- builds use an owned private `.stage/.backend-build-*` tree and build-only app data; copying, downloads, installs, collectstatic and validation finish before publication
- publication renames the previous backend aside and restores it if replacement fails; `.stage/runtime-data/` and unrelated staging entries are preserved
- runtime symlinks are copied and chmodded in private sibling entries before replacement; copy/chmod failures retain the original link and target
- `backend/manage.py` stays at the bundle root
- `backend/src/` keeps the normal source layout
- `backend/python/` contains the bundled interpreter and installed dependencies
- `backend/staticfiles/` contains collected assets for `DEBUG=False`
- `backend/runtime-manifest.json` records the interpreter path and launcher metadata
- Electron/shared Node helpers and Tauri accept only a regular, non-symlink
  manifest of at most 64 KiB with `schemaVersion: 1`, string Python version,
  `python.root: "python"`, executable/purelib/scripts paths inside that runtime,
  and the generated launcher field types. Paths use portable relative components
  (no absolute/drive paths, backslashes, empty components, `.` or `..`).
  The interpreter must resolve to a regular usable file inside the real
  `backend/python/`; that runtime root cannot redirect elsewhere. Internal
  interpreter symlinks remain valid. Present invalid/future manifests refuse
  launch with an `Invalid runtime manifest` diagnostic; only absence enables
  legacy discovery, subject to the same interpreter checks.
- Runtime materialization and the initial downloaded-runtime copy first walk
  the expanded source graph by real directory identities. Cycles, directory
  targets outside the runtime and special files refuse before copying. File
  links (including external interpreter/library files) remain supported.
  Default limits are 200,000 expanded entries, 2 GiB summed file bytes and 256
  directory levels; repeated links count for each expansion. Builds use private
  source trees; concurrent mutation of a runtime during staging is unsupported.
- A materialization error preserves the original copy/publication exception and
  appends cleanup diagnostics (`cleanupErrors`, `temporaryRoot`). After successful
  replacement, cleanup failure reports `committed: true`; do not retry as though
  publication failed. Failed rollback reports `rollbackError` and `originalPath`
  and retains that temporary tree. Inspect the reported paths and restore the
  saved original before manual cleanup. Successful rollback retains the original
  link and never changes its source target. Whole-backend publication still
  protects the last successful staged backend when preflight refuses.

Current launcher contract:

- Electron and Tauri packaged mode resolve the interpreter from `backend/runtime-manifest.json`
- Electron and Tauri then run `manage.py` from `backend/` for both `runserver` and `db_worker`
- packaged settings still rely on runtime environment variables for writable app data, bundle dir, localhost host/port, an optional secret-key override, and unbuffered Python output
- existing secret keys are read once through a descriptor, with final symlinks/reparse points refused, regular-file and size checks (4096 bytes maximum), and POSIX ownership and descriptor permission checks; Windows uses `CreateFileW` with `FILE_FLAG_OPEN_REPARSE_POINT` and relies on app-data ACLs
- no shell injects a `DJANGO_SECRET_KEY`; when the environment does not provide one, packaged settings generate a per-install `DJANGO_SECRET_KEY` in the app-data directory (`secret_key`, created once with `secrets.token_urlsafe(50)` and owner-only `0600` permissions on POSIX) and reuse it on later starts, so every install signs sessions, CSRF tokens, and password-reset links with its own key; an explicit `DJANGO_SECRET_KEY` environment variable still wins
- packaged Django settings keep SQLite in per-user app data and now add desktop-oriented SQLite tuning with `transaction_mode=IMMEDIATE`, a 20-second timeout, `PRAGMA journal_mode=WAL;`, `PRAGMA synchronous=NORMAL;`, and modest cache/mmap settings
- the `/tasks/` demo uses the same SQLite database file as the web app, via the `django_tasks_db` backend tables
- both the task page and polling endpoint show all pending/running rows and at
  most 100 terminal rows, selected by newest completion time (then creation time
  and ID). Active queue results are loaded with the backend's public
  `DBTaskResult` model and `task_result` property in parameter-safe bulk batches,
  preserving task-function matching and the existing reconciliation guards.
  Fresh completions enter history in the same response. This is a visibility
  limit, not automatic deletion: older terminal rows remain until Clear Finished
  Routines deletes them; history pagination is outside this teaching demo.
- successful backend payloads must contain a `DONE`/`FAILED` status, string result,
  finite nonnegative numeric duration (no booleans), and timezone-aware ISO
  completion timestamp. Invalid payloads become a failed demo row through the
  same conditional update. A duplicate's active-state snapshot is a no-op.
- workers finalize only a still-running row with the backend ID they claimed;
  a retired or deleted row is never overwritten or recreated. Missing queue
  metadata fails pending rows, but leaves running claims alone because a live
  worker may still finish. Startup reconciliation retires abandoned claims.
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

Electron updater lifecycle: one check owns its available-update prompt and download
transition. An updater error retires that ownership, so an older dialog response
cannot start work. Downloaded events and menu checks share one install prompt and
preparation task; Later or failed preparation releases it for retry. After
`quitAndInstall` succeeds, later events cannot prepare or install again.

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

## First-run Demo Content

First-run demo seeding uses a unique `DemoContentState` marker as its first
transactional write, before checking for existing user content. This serializes
concurrent SQLite command callers under both development's deferred transactions
and packaged `IMMEDIATE` transactions. The marker and all three ponies commit
together; failure rolls them all back. Existing user content skips the seed
without recording a marker. Call the helper before doing reads in a caller-owned
SQLite transaction; it cannot upgrade a caller's pre-existing read snapshot.

## Deferred Areas

These are expected later if needed, but not part of the first implementation:

- production-grade task orchestration beyond the single supervised `db_worker` process used by `tasks_demo`
- Positron hosted release-lane and connected-updater work beyond the current manual-only strategy
- Tauri release publication and stronger updater hosting defaults
- multiple windows
- richer native integrations

### State generation admission

`state.json` is the completion marker for both newly created and reopened
versions. Its version, timestamp and predecessor are validated along with direct
`media/` and `cache/` directories. A copied generation must contain a regular
single-link database. An empty first-use generation (`copied_from: null`) may
lack the database until migrations run. This preserves the original marker
format; it does not claim that migrations have completed or inspect DB schema.
Malformed/missing markers and incomplete restored layouts stop startup without
replacing the generation. Predecessors undergo the same validation.

The per-user app-data root, state root, version directories and SQLite leaves
(including existing sidecars) reject symlinks/reparse points; POSIX ownership is
checked. POSIX directory descriptors pin identities and media children open
relative to their admitted parent. Windows uses direct-entry/reparse checks and
name/identity rechecks, with ACLs as the authority boundary. SQLite's public
backup API still opens a filename, and settings ultimately return writable
paths: concurrent hostile mutation by the same account is outside this contract.
Directory identity changes detected during initialization refuse publication.
System parent aliases such as macOS `/tmp` are allowed.

Media copies stream a direct tree and refuse all links (including internal
links), special files and hard-linked files. Limits count both directories and
files, actual copied bytes and depth (root is zero). Cache is disposable and
never copied. Refusal removes only the private unpublished stage and preserves
the predecessor. See the release guide for configurable limits and recovery.

### Interrupted and competing state initialization

A persistent `state/.initialize.lock` uses POSIX `flock` or Windows byte-range
locking with a 30-second admission deadline. It serializes all versions through
recovery, backup, media copy and publication. This protects state initialization;
it does not serialize later Django migrations or replace shell single-instance
ownership. The lock inode is never removed. Process death releases the OS lock.

Each private `.dds-stage-<32 hex digits>` has a bounded `.stage-owner.json`
record bound to its exact name and initialization kind. The next lock holder
scans at most 1024 root entries and 16 stage candidates, validating at most
100,016 cleanup entries and 65 directory levels per stage. Only direct owned
regular trees with the exact owner record and known top-level entries qualify
for deletion. Live cooperating initializers cannot be collected because they
hold the same lock. Ambiguous stages remain with bounded warnings. Old-style
hidden stages without ownership evidence are never automatically removed.

Owner metadata is flushed before copying. After SQLite closes its backup target,
all payload files are flushed, child directories then parent directories are
synced, the completion marker is written/flushed, and the stage directory is
synced before rename. POSIX syncs the state root after rename; macOS additionally
uses `F_FULLFSYNC` for files. A prepublication error retains the predecessor;
post-rename sync failure retains the visible complete generation and explicitly
reports uncertain durability. No cleanup restores old bytes over it.

This establishes process-crash recovery and requests available filesystem/device
barriers for initialization. Power-loss persistence still depends on local
filesystem/hardware behavior. Windows flushes files but Python offers no portable
directory-sync primitive here, so rename persistence across power loss is not
guaranteed. These barriers do not change the running database's existing
`synchronous=NORMAL` policy or make promises about later writes. Tests use real
SQLite/WAL/media, deterministic process barriers, kill/restart and injected sync
and rename failures; they do not simulate hardware power loss.
