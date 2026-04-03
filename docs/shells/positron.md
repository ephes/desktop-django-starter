# Positron Shell

Status: implemented as an experimental local shell in this slice.

The current Positron port lives under [`shells/positron/`](../../shells/positron/).

Current responsibilities:

- import the shared Django code from `src/` instead of forking app code into the shell
- validate that the shared Django source tree is present before configuring Django, so startup failures stay readable
- start Django inside the Positron process with an in-process WSGI server bound to a random localhost port
- run the optional `tasks_demo` worker in-process on a background thread
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

Scope boundaries:

- Positron is still experimental and local-only in this slice
- GitHub Actions artifact generation remains out of scope
- Electron remains the most complete shell path
- packaged startup uses the same fallback `DJANGO_SECRET_KEY` value as Electron and Tauri when the environment does not provide one; this is only a local bootstrap convenience, not a release secret
- splashscreen parity is intentionally not required on macOS for Positron
- Positron is not a release-parity path in this slice
- Windows packaged-build parity is not claimed for Positron yet
- local macOS packaging uses Briefcase and currently depends on ad-hoc signing

`tasks_demo` posture in this slice:

- supported
- Positron intentionally differs from Electron and Tauri here: the shell starts the `django_tasks_db` worker in-process on a thread instead of spawning a `db_worker` subprocess
