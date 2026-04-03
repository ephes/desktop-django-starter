# Tauri Shell

Status: implemented as an experimental local shell in this slice, now with a prepared but unverified local Windows packaged-build path.

The current Tauri port lives under [`shells/tauri/`](../../shells/tauri/).

Current responsibilities:

- show a shell-local Flying Stable splash window immediately while backend startup runs
- start Django on a random localhost port and wait for `/health/`
- supervise both `manage.py runserver` and `manage.py db_worker` as child processes
- consume the shared staged backend from `.stage/backend/` for packaged-like runs and local bundle builds
- bundle shell-local icon outputs generated into `shells/tauri/src-tauri/icons/` from the shared source art under `assets/brand/`

Local commands:

- `just tauri-install`
- `just tauri-test`
- `just tauri-start`
- `just tauri-smoke`
- `just tauri-packaged-start`
- `just tauri-packaged-smoke`
- `just tauri-build`

Scope boundaries:

- Tauri is still experimental and local-only in this slice
- GitHub Actions artifact generation remains Electron-only
- Electron remains the most complete shell path
- the current Tauri config now applies a minimal `app.security.csp` for Tauri-served shell assets, including the local splash window and localhost bootstrap surface
- that CSP is intentionally narrow and should not be read as production-hardening for the Django pages loaded over `http://127.0.0.1:<random-port>`
- Tauri is not a release-parity path in this slice
- the Windows support claim is limited to preparing a local NSIS installer path with `just tauri-build`
- `just tauri-build` now also prints a Windows NSIS validation checklist when run on Windows, while `/docs/release.md` keeps the canonical written checklist
- installer install/run validation still needs a real live Windows machine and is not automated in this repo

Current minimal CSP posture:

- `default-src 'self'`
- `connect-src` is limited to Tauri IPC plus localhost (`ipc:`, `http://ipc.localhost`, `http://127.0.0.1:*`, `http://localhost:*`)
- inline style is still allowed for the shell-local splash document
- the policy blocks plugin/object embedding and framing with `object-src 'none'` and `frame-ancestors 'none'`
- this covers the Tauri-served splash/bootstrap assets only; the Django UI remains a localhost-served renderer with its own separate hardening story

`tasks_demo` posture in this slice:

- supported
- Tauri follows the same staged-backend subprocess model as Electron and starts `db_worker` after Django passes the `/health/` readiness check
