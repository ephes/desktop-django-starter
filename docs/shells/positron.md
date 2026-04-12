# Positron Shell

Status: implemented as an experimental local shell in this slice.

The current Positron port lives under [`shells/positron/`](../../shells/positron/).

Current responsibilities:

- import the shared Django code from `src/` instead of forking app code into the shell
- validate that the shared Django source tree is present before configuring Django, so startup failures stay readable
- start Django inside the Positron process with an in-process WSGI server bound to a random localhost port
- generate a fresh per-session shell-to-Django auth token, pass it into Django as `DESKTOP_DJANGO_AUTH_TOKEN`, and load the web view through Django's `/desktop-auth/bootstrap/` URL so Django can set an HttpOnly same-origin auth cookie before redirecting to the app
- enforce a single running instance per app-data directory with a lock file before the in-process server starts
- run the optional `tasks_demo` worker in-process on a background thread
- always boot Django with `desktop_django_starter.settings.packaged` so local Positron runs validate the packaged-style app-data and staticfiles contract
- refresh collected static files on startup without clearing the cache-backed staticfiles tree on every launch
- reuse the shared brand source under `assets/brand/` and generate shell-local icon outputs into `shells/positron/resources/`
- keep Positron-specific runtime behavior under `shells/positron/src/desktop_django_starter_positron/`

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
- packaged startup uses the same fallback `DJANGO_SECRET_KEY` value as Electron and Tauri when the environment does not provide one; this is only a local bootstrap convenience, not a release secret
- Positron uses a bootstrap HttpOnly cookie instead of Electron's hidden per-request header injection because this Toga web view path does not currently have an Electron-equivalent external-localhost outgoing request header hook
- Positron now enforces single-instance startup, but unlike Electron and Tauri it currently exits the second launch instead of focusing the existing window
- Positron intentionally always uses the packaged Django settings module, even during local shell runs, so the experimental shell exercises the desktop-style SQLite location and collected-staticfiles path instead of Django's debug-oriented local settings
- startup still refreshes collected static files locally without clearing the cache-backed staticfiles tree on every launch
- splashscreen parity is intentionally not required on macOS for Positron
- Positron is not a release-parity path in this slice
- Windows packaged-build parity is not claimed for Positron yet
- local macOS packaging uses Briefcase and currently depends on ad-hoc signing

`tasks_demo` posture in this slice:

- supported
- Positron intentionally differs from Electron and Tauri here: the shell starts the `django_tasks_db` worker in-process on a thread instead of spawning a `db_worker` subprocess
