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
When a shell token is configured or required, the middleware applies
`Cache-Control: private, no-store` to every response (including GET/HEAD, forms,
task JSON, packaged-mode static assets, CSRF refusals, retired-token refusals and a missing
required-token configuration). It overrides downstream `public` caching. Local
development without shell authentication keeps its existing cache behavior,
except for the always-private bootstrap route. Token and CSRF admission rules
are unchanged; these headers do not erase copies cached by older app versions.
In development with `DEBUG=True`, `runserver`'s static-files handler answers
`/static/` before any middleware, so those assets keep Django's default headers.

Django's request-log filter redacts every bootstrap query member whose decoded
name is `token`, including percent-encoded aliases and duplicate members. It
formats positional or mapping-style arguments before redaction, preserves safe
URL structure and also recognizes percent-encoded bootstrap paths and repeated
leading slashes (which `http.server` routes as a single `/`). The query runs to
the end of the raw request target, so members after a raw `#` or quote are still
redacted; only a closing quote of the logged request line stays outside. A record whose
arguments cannot be formatted keeps only its redacted template instead of raising
at the logging call site. Credentials must stay out of terminal/system logs even
when Django accepts a nonliteral key.

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
3. Electron admits a regular session marker of at most 4096 bytes in the app-data directory, preserving and refusing unreadable/unsafe markers. If the previous run never marked itself finished (a crash, a force quit, power loss), Electron stops backend processes that run left behind: every backend process carries this install's random app key on its command line, so they can be found without touching other apps.
4. Electron runs migrations using either the bundled runtime or a local development interpreter. In packaged mode, the first start of a new app version prepares that version's state directory first (see Data and Files).
5. Electron completes any pending first-run demo seed, runs `recover_stale_routines`, then starts Django.
6. Django exposes a dedicated health endpoint.
7. Electron polls that endpoint until it succeeds or times out (15 seconds). If that Django child exits, Electron cancels the pending request or retry delay and reports the exit as a startup failure.
8. Electron starts the single `db_worker` process only after Django is healthy.
9. Electron loads the main app window, then closes the splash window once the main window is ready to show.
10. When the user closes the window or quits while background tasks are running or queued (`/desktop/activity/`), Electron asks first. Quitting then stops both child processes; on Windows with explicit forced process-tree termination (`taskkill /t /f`) rather than a graceful drain. Electron marks the session finished only after confirmed child exit and confirmed orphan recovery; uncertainty retains dirty evidence.

Every backend process (`migrate`, `seed_demo_content`, `recover_stale_routines`, `runserver`, `db_worker`) is started through `desktop_process_guard.py`, a small standard-library launcher staged next to `manage.py`. It runs `manage.py` in the same process and adds ownership safety nets for the case where the shell dies without cleaning up:

- the shell keeps an open pipe on the child's stdin; when the shell process ends for any reason, the operating system closes it and the guard forcibly retires its owned backend tree
- on POSIX the guard establishes a dedicated group before Django runs, including when invoked from a shared caller group. Stdin loss kills only that owned group with SIGKILL. SIGTERM and SIGINT do the same only until the managed command installs its own handlers: `db_worker` replaces them with its graceful shutdown, so a shell that only signals the leader cannot rely on them. Group admission failure refuses startup before Django runs
- on Windows the guard puts the backend into a Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, so anything the backend starts dies with it. Creation, configuration or assignment failure closes any newly created handle and refuses startup before Django runs, using a fixed diagnostic without host details

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
- predecessor selection uses public SemVer parsing plus the narrow Positron a/b/rc mapping described in {ref}`the release guide <upgrades-and-rollbacks>`: `0.2.0-rc.2 < 0.2.0-rc.10 < 0.2.0`; unsupported current or candidate versions stop startup with recovery guidance
- SQLite sources open through an escaped read-only URI; a disappeared or invalid source fails initialization without recreating it or publishing state
- SQLite backup has a total monotonic 30-second startup budget, including busy retries and page copying. Startup attempts to close both connections, preserves the first failure, and removes only unpublished staging on failure.
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
  manifest of at most 64 KiB encoded as UTF-8 without a byte-order mark, with
  `schemaVersion: 1`, string Python version,
  `python.root: "python"`, executable/purelib/scripts paths inside that runtime,
  and the generated launcher field types. Paths use portable relative components
  (no absolute/drive paths, backslashes, empty components, `.` or `..`).
  The interpreter must resolve to a regular usable file inside the real
  `backend/python/`; that runtime root cannot redirect elsewhere. Internal
  interpreter symlinks remain valid. Present invalid/future manifests refuse
  launch with an `Invalid runtime manifest` diagnostic; only absence enables
  legacy discovery, subject to the same interpreter checks.
  Both readers use one open file handle and verify the exact byte count and
  that the file and its path still match the admitted generation before parsing.
  If the manifest changes while staging overlaps startup, wait for staging to
  finish and retry the launch.
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
- existing secret keys are read through one descriptor, with final symlinks/reparse points refused, regular-file and size checks (4096 bytes maximum), and POSIX ownership and descriptor permission checks; Windows uses `CreateFileW` with `FILE_FLAG_OPEN_REPARSE_POINT` and relies on app-data ACLs
- the key read must match the admitted byte count and the descriptor's identity,
  size, mtime and ctime must agree before and after reading. When only ctime
  changes as the link count drops from two to one, a concurrent creator may
  have removed its temporary link. A single bounded reread must return the
  same bytes with stable metadata. POSIX permission repair runs on the
  verified descriptor after these checks.
- no shell injects a `DJANGO_SECRET_KEY`; when the environment does not provide one, packaged settings generate a per-install `DJANGO_SECRET_KEY` in the app-data directory (`secret_key`, created once with `secrets.token_urlsafe(50)` and owner-only `0600` permissions on POSIX) and reuse it on later starts, so every install signs sessions, CSRF tokens, and password-reset links with its own key; an explicit `DJANGO_SECRET_KEY` environment variable still wins
- packaged Django settings keep SQLite in per-user app data and now add desktop-oriented SQLite tuning with `transaction_mode=IMMEDIATE`, a 20-second timeout, `PRAGMA journal_mode=WAL;`, `PRAGMA synchronous=NORMAL;`, and modest cache/mmap settings
- My Ponies uses 20-row database pages, ordered by update time, creation time
  and primary key (descending) so timestamp ties cannot omit rows. Native page
  links and create/edit/delete navigation retain the displayed page. Cancel
  links and success redirects accept only positive page numbers written with up
  to 19 ASCII digits. Missing or invalid values return to the first page.
  Accepted values clamp to the current last page, using the new count after a
  successful mutation. If the count fails after a pony is saved during creation,
  the success redirect opens the first page. The release modal follows its
  success redirect, and Release All Ponies returns to the first page.
- Edit and release requests carry a signed digest of the displayed pony's ID,
  editable content and update timestamp. SQLite's writer lock is acquired before
  reloading and comparing that revision, and is held through save/delete. Missing,
  forged or stale tokens return HTTP 409 without changing the item; edit conflicts
  keep the submitted input and original token. Reload current pony opens a fresh
  form/confirmation. Invalid forms also retain their original revision. CSRF and
  shell authentication still apply independently. No schema migration is needed.
- The single-pony release route allows GET and HEAD for the confirmation, OPTIONS
  for method discovery, and POST for revision-checked removal. Other methods
  receive Django's HTTP 405 when the request passes CSRF validation.
- The list's release modal submits the row's displayed revision and keeps conflicts
  visible with a link to the current confirmation page. That page shows the full
  current personality/status before a fresh release. Release All Ponies opens an
  explicit confirmation for the total stable count, including other pages. Its
  signed inventory generation, count and page rows come from one deferred SQLite
  read snapshot. The list reads one generation row alongside the count and page
  query. Even under packaged `IMMEDIATE` transactions the deferred read avoids the
  writer lock. SQLite triggers assign a fresh generation on item inserts, updates
  and deletes in the same transaction, including bulk writes. Confirmation takes
  SQLite's writer lock before comparing the generation and deleting. An older
  form, including one with a pre-upgrade digest, returns HTTP 409 and links to a
  fresh stable view. Clearing a nonempty stable advances its generation, so the
  same confirmation cannot clear it again. Run `just migrate` to install the
  generation table and triggers locally. Packaged startup applies the migration.
  Future SQLite migrations that rebuild the item table must recreate its triggers.
- Start Routine admits at most 16 pending/running demo rows globally. A no-op
  UPDATE on the existing routine table takes SQLite's writer lock before the
  count; admission and both demo/backend inserts share that transaction, including
  in local mode with deferred transactions. A full queue returns HTTP 503 with
  `Retry-After: 1` and creates neither row; the page shows the refusal message
  next to Start Routine. Terminal history does not consume slots.
  This contract relies on the starter's SQLite-only database and shared DB queue.
- the `/tasks/` demo uses the same SQLite database file as the web app, via the `django_tasks_db` backend tables
- both the task page and polling endpoint show all pending/running rows and at
  most 100 terminal rows, selected by newest completion time (then creation time
  and ID). Active queue results are loaded with the backend's public
  `DBTaskResult` model and `task_result` property in parameter-safe bulk batches.
  Before constructing a task result, bulk polling checks the stored task path,
  backend, and queue against the configured routine task. Single-result
  reconciliation uses Django's task lookup. Both paths require the routine's
  integer ID as the sole positional argument, as written by Start Routine.
  Bulk polling also checks the stored status and the argument container before
  constructing the result. A malformed status or argument container makes only
  that result unavailable. Missing results and identity or argument mismatches
  can fail a routine only while it is still pending. A worker claim made
  during the poll is preserved. Database errors still surface to the caller.
  Fresh completions enter history in the same response. If reconciliation
  reloads a routine that was completed and cleared in the meantime, the
  response omits it; a routine whose backend result still reports it queued or
  running keeps its polled snapshot until the next poll.
  Older terminal rows remain until Clear Finished Routines deletes them.
  Clearing uses batches of up to 100 routine rows in primary-key order.
  The clear first snapshots the IDs of routines that are terminal under the
  writer lock, including legacy rows without a completion timestamp. Every batch
  selects and deletes only from that snapshot. A routine whose completion commits
  after the snapshot stays for a later clear, whatever completion time its worker
  recorded.
  Each batch commits its history deletion and verified backend deletions in the
  same SQLite transaction. A backend result qualifies if it has terminal status,
  matches the demo task path, backend and queue, carries the routine's integer
  ID as its sole argument, and has a single routine reference. UUID spellings
  are normalized when checking for sharing, and references found shared stay
  protected across batches within the clear. Active jobs and unrecognized
  results remain in the queue database.
  History pagination is outside this teaching demo.
  SQLite partial indexes cover active creation ordering and terminal completion,
  creation and ID ordering. The ORM uses OR equality predicates matching those
  indexes: a bound `IN` predicate cannot imply a literal partial-index `IN`
  condition in SQLite. Routine polling therefore visits active rows and the
  bounded history window without sorting or scanning all retained history.
- Shell activity counts queued and running tasks served by the shell worker
  in one conditional aggregate on the database alias Django routes task
  writes to. A READY-to-RUNNING transition cannot fall between two counter
  reads and falsely report idle. The worker and the count on the default
  task backend share `DESKTOP_DJANGO_WORKER_QUEUES` (default `default`, comma
  separated, or `*` for all queues). The ordinary
  `dds_backend_activity_idx` index covers status, backend and queue, keeping
  terminal history and unserved queues out of the aggregate. Apps without
  the backend report zero without a database query. The HTTP activity endpoint sends
  `Cache-Control: no-store` even without shell authentication so each quit
  check reads fresh counts. Positron calls the count function directly.
- Apply `tasks_demo.0003_routine_poll_indexes` and
  `tasks_demo.0004_backend_activity_index` plus
  `tasks_demo.0005_backend_activity_queues` with `just migrate` in
  development. Packaged startup applies them before starting the web and worker
  processes, including to copied version state. Index creation may briefly lock
  a large local SQLite database. The migrations reverse without deleting task
  rows. The backend indexes use Django's public schema-editor API and the
  historical model from the pinned django-tasks-db 0.13.0 migration
  `django_tasks_database.0021_conditional_partial_index_ordering`; dependency
  upgrades must recheck that schema. The dependency's model and worker index
  remain unchanged. The backend index migration belongs to the optional
  `tasks_demo` extension, so the core `desktop_django_starter` app has no
  migrations and no migration dependency on `django_tasks_db`.
- Polling selects at most the final 1024 characters of each backend traceback in
  SQL before constructing a task result or splitting lines. Full diagnostics stay
  in the backend table. Unexpected exceptions display only the fixed category
  "Task exited before the demo row was finalized."; only the exact known demo
  exception class and allowlisted demo messages can publish a specific failure
  message. Worker-finalized results remain authoritative, and an independent
  routine still reconciles normally when another routine fails.
- successful backend payloads must contain a `DONE`/`FAILED` status, a result
  encodable in UTF-8 in at most 1024 bytes, a finite nonnegative numeric duration
  (no booleans), and a timezone-aware ISO
  completion timestamp. Polling normalizes the timestamp to the database's UTC
  domain before writing. A conversion overflow or other invalid payload becomes
  a failed demo row through the same conditional update. A duplicate's
  active-state snapshot is a no-op.
- workers finalize only a still-running row with the backend ID they claimed;
  a retired or deleted row is never overwritten or recreated. Missing queue
  metadata fails pending rows, but leaves running claims alone because a live
  worker may still finish. The shells run `recover_stale_routines` after
  migrations, with exclusive profile ownership and after the old worker has
  stopped. It marks pending and running demo rows failed and leaves terminal
  rows and the backend queue intact. Without the optional demo app recovery
  succeeds immediately. A database error fails the command with a fixed
  diagnostic. The shells report the startup failure before opening Django
  or the worker. Ordinary Django setup and standalone worker startup leave these
  rows alone. When using the development database, stop any manually launched
  worker before starting a desktop shell against the same checkout.
- task polling applies backend outcomes only while the current demo row is
  pending or running and still has the backend ID used for the lookup. If a
  worker finalizes the row or it is rebound to another backend ID, a rejected
  poll update reloads the current row and preserves its stored state.
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

## Electron frame permissions

Before `loadURL`, the main window installs both public Electron session permission
handlers through `registerSessionPermissionPolicy`. The starter needs no renderer
capabilities, so the default allowlist is empty. Remote embeds can still load;
camera, microphone, location, notifications and other capability requests/checks
are denied. Unknown permissions and requests without document evidence deny too.

A reviewed adaptation can pass individual permission names to the installer.
Admission requires the owned live WebContents, an explicit main-frame flag,
the requesting document URL and current main document on the exact Django origin;
checks also require the requesting origin to match. Subframes and non-document
checks (including null WebContents) remain denied. This shared-session policy is
reinstalled for a recreated main window. Keep the exact-origin auth-header hook
and IPC sender checks independent. See {ref}`the shell guide <frame-permissions>`
for the opt-in seam and real-browser verification command.

Popup dispatch uses the complete public `WindowOpenDetails` through
`registerWindowOpenGuard`. It always denies creating a child window. A safe
HTTP(S)/mailto target opens externally only when the referrer is on the exact
Django origin and the owning WebContents is alive and still displaying that
origin. Foreign, missing, malformed and suppressed referrers deny native dispatch.
The referrer is origin evidence, not proof of a user gesture; disposition alone
never authorizes dispatch. Electron reports the referrer after the page's policy
is applied, so the starter sets `SECURE_REFERRER_POLICY =
"strict-origin-when-cross-origin"` instead of Django's default `same-origin`,
which would refuse every trusted target-blank outbound link; the token bootstrap
path keeps `no-referrer`. Ordinary main-frame navigation and redirect guards
retain their existing behavior, as does the sender-checked app-data bridge.

## Native Surface Area

The desktop integration should stay narrow:

- one preload bridge or application-menu action is enough for v1
- the first native action should be simple and generic, such as revealing the app-data folder
- no wide IPC API should be exposed to page code

## Shutdown Notes

Shutdown handling must be treated as a cross-platform lifecycle concern, not as a best-effort cleanup step.

- on macOS and Linux Electron launches each backend in a dedicated process group, closes its stdin on stop and sends group SIGTERM followed by group SIGKILL even if the leader has exited. When a leader exits on its own (crash or end of a one-shot command), Electron SIGKILLs the rest of its group as soon as it observes the exit. The guard retires its own group on pipe loss; this also covers Python behind a development `uv` launcher
- the experimental Tauri shell still stops POSIX backends by signalling only the leader (`kill -TERM`, then a leader kill), so descendants of `db_worker`, whose own SIGTERM handler replaces the guard's, can outlive a normal Tauri stop until the next start's leftover cleanup
- Windows needs explicit handling because process-tree shutdown is less predictable
- the current Electron implementation on Windows uses explicit forced child-process tree termination via `taskkill /t /f` (from `%SystemRoot%\System32`, falling back to a plain kill if it fails)
- that forced tree kill is not a graceful drain: a running task is interrupted, which is why the shells ask before quitting while tasks are running; queued tasks stay in the database and run on the next start
- for the cases normal shutdown cannot cover, every backend process runs under `desktop_process_guard.py`: it kills its owned group on POSIX when the shell's stdin pipe closes, and on Windows it holds a kill-on-close Job Object for its process tree; a later start also stops leftovers it finds by app key
- the Job Object is created by the backend process for itself and its descendants, not by Electron for its children (Node.js has no Job Object API); the stdin pipe is what ties the backend to the shell
- verified on macOS: `kill -9` of the Electron main process ends `runserver` and `db_worker` within three seconds, and a planted leftover is stopped on the next start. The Windows paths (Job Object, `taskkill`, PowerShell process listing) are implemented but not yet validated on a live Windows machine

## First-run Demo Content

Before migrating a new packaged database, Electron flushes a per-version pending
seed marker in the app-data root. The next launch resumes that seed even if
migration already created the database. Electron retires the marker after the
seed command succeeds or when the version's state records a copied predecessor.
An existing database without a pending marker stays untouched, even when empty.

First-run demo seeding uses a unique `DemoContentState` marker as its first
transactional write, before checking for existing user content. This serializes
concurrent SQLite command callers under both development's deferred transactions
and packaged `IMMEDIATE` transactions. The marker and all three ponies commit
together; failure rolls them all back and permits a later retry. Existing user
content skips insertion but commits the marker, so clearing legacy rows and
reopening the database cannot make it look new again. Call the helper before doing reads in a caller-owned
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
Both completion and stage-owner markers use one bounded JSON object reader
(16 KiB and 4 KiB respectively). Duplicate decoded member names are rejected at
every object depth, including identical values and escaped name spellings.
Both readers also reject nonstandard numeric constants and floats that decode
to infinity. Completion markers can still include ordinary JSON metadata.
A repeated claim cannot authorize reuse, predecessor copying or stage deletion.
Malformed/missing markers and incomplete restored layouts stop startup without
replacing the generation. The selected predecessor (the newest older version
directory with a database) undergoes the same validation. Older generations that
are not selected, directories without a database and stray plain files in the
state root are left untouched and do not block an upgrade; links there are refused.

The per-user app-data root, state root, version directories and SQLite leaves
(including existing sidecars) reject symlinks/reparse points; POSIX ownership is
checked. POSIX directory descriptors pin identities and media children open
relative to their admitted parent. The state reader owns the descriptor and
closes it even if stream construction fails, preserving the original error.
Windows uses direct-entry/reparse checks and
name/identity rechecks, with ACLs as the authority boundary. SQLite's public
backup API still opens a filename, and settings ultimately return writable
paths: concurrent hostile mutation by the same account is outside this contract.
Directory identity changes detected during initialization refuse publication.
On POSIX, the directory guard preserves an active error if closing its
descriptor also fails. A standalone close failure stops initialization.
System parent aliases such as macOS `/tmp` are allowed.

Media copies stream a direct tree and refuse all links (including internal
links), special files and hard-linked files. Limits count both directories and
files, bytes read from the admitted sources and depth (root is zero). The media
depth override is capped at 64. This bounds the recursive copy, sync and cleanup
walks. Each file is read only to its initial size. Early EOF and short
destination writes fail the copy before the staged tree is synced. Admission,
opened-descriptor and final named-file metadata must agree on device/inode,
size, nanosecond mtime and ctime.
Detected in-place edits, growth, truncation or replacement refuse publication.
After copying media, startup backs up SQLite, then checks each visited directory
and copied file again for matching identity, size, mtime and ctime. This detects
membership changes and in-place edits spanning traversal and the backup. An
absent legacy media root must still be absent after the backup. Change detection
uses platform filesystem metadata. Close all writers before upgrade for a
quiescent source.
Cache is disposable and never copied. Refusal removes only the private
unpublished stage and preserves the predecessor. See the release guide for
configurable limits and recovery.

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
for deletion. Recovery rechecks the admitted state root and stage before
renaming the stage into a private `.dds-retired-<uuid>` directory. It verifies
the detached identity before recursive removal. If a check or the rename fails
before the stage is detached, the still-empty retirement directory is removed
so retries do not accumulate root entries. POSIX uses directory-relative
rename and removal; Windows rechecks named entries. Live cooperating
initializers hold the same lock. Inspect retained ambiguous stages and leftover
retirement directories with the app closed. Old-style hidden stages without
ownership evidence are never automatically removed.

Owner metadata is flushed before copying. After SQLite closes its backup target,
all payload files are flushed, child directories then parent directories are
synced, the completion marker is written/flushed, and the stage directory is
synced. The initializer validates the staged marker and layout against the
intended version before rename and validates the published paths again after
rename and sync. POSIX syncs the state root after rename. macOS additionally
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

(electron-orphan-command-and-signal-limits)=

### Electron orphan command and signal limits

Recovery process tools have a three-second hard timeout and a further bounded
500 ms callback/reap allowance, with output capped at 16 MiB. Tool failure gives
a bounded diagnostic. POSIX inventory joins executable and arguments only when
both PID and observed start time agree. Before TERM and again before KILL,
recovery checks the start time, executable, complete command line and app marker;
PID replacement retires only the old candidate, never authorizes the replacement.
Windows uses CIM CreationDate and checks it again in the terminating helper;
it does not use an unchecked orphan `taskkill /t` tree.

These are public process-tool observations, not kernel process handles. POSIX
`ps` start times have second precision, and neither platform offers an atomic
observe-and-signal guarantee here. A process replaced after the last observation
is outside that guarantee. Missing identity is refused; no PID-only fallback is
used. Owned normal child shutdown remains separate from orphan discovery.

An absent session marker is the only first-launch case. An existing malformed,
foreign-shaped or unreadable marker is preserved and backend startup stops before
migrations, server or worker launch. Repair its access/content with the app closed
and explicitly launch again; do not delete a dirty marker to bypass recovery.

If update preparation or the installer handoff fails after shutdown begins,
Electron hides the now unusable app window, attempts cleanup of both backends,
shows a restart-required explanation and exits with failure. It preserves dirty
recovery evidence, rather than starting duplicate backends or leaving a window
connected to stopped services. Install ownership is held through failure handling.

Session input is limited to 4096 bytes. Electron admits a direct regular file,
opens it with no-follow/nonblocking flags where supported, checks that same
single-link descriptor before reading and refuses detected in-place changes.
Symlinks, special files and oversized inputs cannot become fresh-session state.

Managed shutdown ignores the ChildProcess `killed` delivery flag and waits for
an actual exit, including a bounded 500 ms wait after SIGKILL (or Windows
`taskkill`). Both children receive a cleanup attempt even if one fails. Only
confirmed retirement of both permits `running: false`; unresolved shutdown keeps
the dirty marker so the next launch must recover. The shell still exits on
cleanup failure, and does not claim that signal delivery proves termination.

Marker publication uses an exclusive, unique sibling temporary with private
permissions, writes through its owned descriptor and renames only that admitted
inode. Stale PID temporaries and foreign entries are neither truncated nor
removed; failed publication removes only its own temporary.

Orphan recovery returns **confirmed** or **unknown**, rather than disguising a
failed inventory as an empty list. Unknown inventory, changed/ambiguous backend
identity or unconfirmed termination blocks migrations and all new backend starts.
Even subsequent shell shutdown leaves the marker dirty. Repair the process tool
or permissions with the app closed, then explicitly relaunch to retry. A proven
empty inventory or confirmed retirement permits normal startup. This stricter
startup refusal supersedes the earlier nonfatal cleanup-failure behavior.

### Backend descendant acceptance

Run `uv run pytest tests/test_desktop_process_guard.py -v` for real POSIX guard
cleanup on stdin loss and SIGTERM, starting in the caller's shared group. The
synthetic backend spawns a sleeping descendant that ignores SIGTERM. Run
`npm --prefix shells/electron test` for normal shutdown, including real owned
groups with a leader that exits before a SIGTERM-resistant descendant.

On native Windows, run
`uv run pytest tests/test_desktop_process_guard.py -k windows_owned_child_cleanup -v`.
This holds real process handles and verifies both the guard and child terminate
on pipe loss and abrupt guard termination. These tests skip on POSIX; mocked
Job Object API tests do not substitute for that acceptance. Also run
`just packaged-smoke` for the staged runtime and shell integration.

Cleanup is forced and may interrupt active tasks. Ordinary descendants remain
in their inherited process group/job; code that deliberately escapes that
ownership is outside the starter contract. A one-shot command can still return
normally with its original status; stdin loss and shell stop own group cleanup.
