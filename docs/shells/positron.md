# Positron Shell

Status: implemented as an experimental local shell in this slice.

The current Positron port lives under [`shells/positron/`](../../shells/positron/).

Current responsibilities:

- import the shared Django code from `src/` instead of forking app code into the shell
- prefer the bundled `src/` when it contains the three shared packages'
  `__init__.py` files and the settings package's `__init__.py` and `packaged.py`
  files. Fall back to the development `src/` when it has those files. If neither
  tree qualifies, report the candidate paths and required files before Django
  starts.
- start Django inside the Positron process with an in-process WSGI server bound to a random localhost port
- generate a fresh per-session shell-to-Django auth token, pass it into Django as `DESKTOP_DJANGO_AUTH_TOKEN`, and load the web view through Django's `/desktop-auth/bootstrap/` URL so Django can set an HttpOnly same-origin auth cookie before redirecting to the app
- enforce a single running instance per app-data directory with a lock file before the in-process server starts
- run the optional `tasks_demo` worker in-process on a background thread
- always boot Django with `desktop_django_starter.settings.packaged` so local Positron runs validate the packaged-style app-data and staticfiles contract
- pass `DESKTOP_DJANGO_APP_VERSION` (Toga's `App.version`, falling back to the installed `desktop-django-starter-positron` distribution's version, because Toga derives its metadata lookup from the app ID and usually finds none) so packaged settings keep the database, media and cache in `<app-data>/state/<version>/`
- ask before quitting while background tasks are running or queued: the async `on_exit` handler reads `background_task_counts()` in a worker thread and, if tasks are active, shows a Toga `QuestionDialog`; answering No returns `False`, which cancels the exit. Idle, a failed count, or smoke mode exit normally, and further quit requests are ignored from the start of the activity check through confirmation and cleanup
- refresh collected static files on startup without clearing the cache-backed staticfiles tree on every launch
- reuse the shared brand source under `assets/brand/` and generate shell-local icon outputs into `shells/positron/resources/`
- keep Positron-specific runtime behavior under `shells/positron/src/desktop_django_starter_positron/`

Positron gives each launch its own port, auth token and app version. The WSGI
server binds to port zero so the OS picks a free port, and startup generates a
new auth token. When Toga and the installed distribution both lack version
metadata, Django uses `<app-data>/state/unversioned/`. Omitted values are
removed from both the constructed environment and the process environment
before Django starts. Other inherited settings such as the smoke-test flag
remain available.

The quit check gives its own connection to the task writer a 250 ms SQLite
busy timeout and interrupts long queries after a 250 ms deadline. The worker
thread closes that connection before quit proceeds. A locked database follows
the same exit path as any failed count. The ordinary activity endpoint uses
the packaged connection settings.

Before creating a new packaged database, Positron records a pending demo seed
beside that version's database and flushes the empty marker file and its
directory to disk, so a crash or power loss cannot keep the new database while
losing the claim. A marker that is not an empty regular file stops startup.
If migration or seeding is interrupted, the
same version retries on the next launch. Successful seeding clears the pending
file. Django records the seed decision with the pony rows in one transaction,
so a retry preserves edits and does not recreate deleted ponies. Positron
admits existing databases without a pending file as initialized, including
legacy profiles and databases copied from an older version.

The server thread owns the listener. If WSGI setup fails after binding, it
closes the listener directly. Exit requests during startup prevent serving
and keep the profile locked until startup stops. If Django or the task
worker fails to start, Positron cleans up the startup resources and shows a
restart message. If the WSGI server stops after readiness, the server thread
closes its listener and the UI shows a terminal error. Dismissing the dialog
exits the app so it can be relaunched. A normal quit shows no service error.

Positron requires a direct regular profile lock file. After taking the lock,
it verifies that the lock path still names the opened file before writing the
PID or starting Django. An unsafe or replaced lock stops startup with a
restart message. Keep the lock file in place while the app is running.

Lock acquisition and PID initialization failures close the opened handle and
release any acquired lock. Shutdown also closes the handle when explicit unlock
fails. Cleanup preserves the original failure, so a retained traceback does not
keep the instance locked.

Local commands:

- `just positron-install`
- `just positron-check`
- `just positron-start`
- `just positron-smoke`
- `just positron-icons`
- `just positron-create`
- `just positron-build`
- `just positron-package-dmg`

Update strategy in this repo:

- manual-only for now
- current install/update artifact: a local macOS DMG produced by `just positron-package-dmg`
- current operator path: build the newer DMG locally on a macOS machine with the Briefcase prerequisites, quit the installed app, then replace the app manually from that newer DMG
- current artifact boundary: `just positron-package-dmg` uses Briefcase ad-hoc signing, so the resulting app is only suitable for local validation on the machine that built it rather than a hosted end-user release lane
- local Positron updates should leave per-user app data in place because the app bundle is replaced separately from the writable app-data directory
- Briefcase development refresh flows such as `briefcase update` or `briefcase build --update-resources` are not presented here as end-user auto-update
- there is no connected updater, hosted artifact lane, checksum lane, or GitHub release-publication flow for Positron in this repo
- a broader Positron updater path would first need a real hosted artifact lane, checksum generation, release publication, platform signing/notarization, and Windows packaged install/run proof

Scope boundaries:

- Positron is still experimental and local-only in this slice
- GitHub Actions artifact generation remains out of scope
- Electron remains the most complete shell path
- like Electron and Tauri, the shell does not inject a secret; packaged settings use a per-install `DJANGO_SECRET_KEY` generated once in the app-data directory unless the environment provides one
- Positron uses a bootstrap HttpOnly cookie instead of Electron's hidden per-request header injection because this Toga web view path does not currently have an Electron-equivalent external-localhost outgoing request header hook
- Positron now enforces single-instance startup, but unlike Electron and Tauri it currently exits the second launch instead of focusing the existing window
- Positron intentionally always uses the packaged Django settings module, even during local shell runs, so the experimental shell exercises the desktop-style SQLite location and collected-staticfiles path instead of Django's debug-oriented local settings
- startup still refreshes collected static files locally without clearing the cache-backed staticfiles tree on every launch
- splashscreen parity is intentionally not required on macOS for Positron
- Positron is not a release-parity path in this slice
- Windows packaged-build parity is not claimed for Positron yet
- local macOS packaging uses Briefcase and currently depends on ad-hoc signing
- Positron does not use `desktop_process_guard.py`, the shell session file or orphan cleanup: Django, the WSGI server and the task worker all run inside the Positron process, so a crash or force-quit ends them together and there are no child processes to leave behind

`tasks_demo` posture in this slice:

- recover abandoned rows after acquiring the profile lock and running migrations, before starting the server or worker. The lock stays held through process exit if a worker outlives the shutdown wait.
- Positron intentionally differs from Electron and Tauri here: the shell starts the `django_tasks_db` worker in-process on a thread instead of spawning a `db_worker` subprocess

Positron's canonical Python prereleases (`X.Y.ZaN`, `X.Y.ZbN`, `X.Y.ZrcN`)
are accepted for state selection and mapped to SemVer `alpha.N`, `beta.N`,
`rc.N` precedence. Directory names keep their original spelling. Python dev,
post, epoch and other version forms without a direct supported SemVer peer are
refused with a configuration error; use stable or a/b/rc release versions for
Positron builds. Equivalent spellings compare equally and are not
predecessors; if several of them are the newest older state, startup lists
them and stops so you can reconcile them.

Icon regeneration preflights `rsvg-convert` and, on macOS, `iconutil` before
rendering. It stages a nonempty PNG and, on macOS, a complete nonempty ICNS
before replacing either installed output. Other platforms publish only the
PNG and leave an existing ICNS alone. Private temporary iconsets are cleaned
on success and failure; an existing `app-icon.iconset` is never removed.
Ordinary publication errors restore the previous set (or remove newly
published files on a first run). If rollback fails, the error names retained
a recovery directory at `resources/.app-icons-*/previous`; restore its backups while
no generator is running. A first-run rollback failure may have no backups;
remove the partially published outputs before retrying. Cleanup errors preserve
the original failure diagnostic; cleanup failure after publication leaves the
new icons installed. Rendering workspaces may overlap, but run final
publication serially. This is exception rollback, not crash-safe publication.
