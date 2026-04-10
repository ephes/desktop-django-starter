# Tauri Shell

Status: implemented as an experimental shell in this slice, now with local bundle commands plus an artifact-only GitHub Actions workflow.

The current Tauri port lives under [`shells/tauri/`](../../shells/tauri/).

Current responsibilities:

- show a shell-local Flying Stable splash window immediately while backend startup runs
- start Django on a random localhost port and wait for `/health/`
- generate a fresh per-session shell-to-Django auth token, pass it to Django as `DESKTOP_DJANGO_AUTH_TOKEN`, and include `X-Desktop-Django-Token` in the readiness poll
- load the web view through Django's `/desktop-auth/bootstrap/` URL so Django can set an HttpOnly same-origin auth cookie before redirecting to the app
- supervise both `manage.py runserver` and `manage.py db_worker` as child processes
- consume the shared staged backend from `.stage/backend/` for packaged-like runs and local bundle builds
- bundle shell-local icon outputs generated into `shells/tauri/src-tauri/icons/` from the shared source art under `assets/brand/`
- build hosted CI artifacts through [`.github/workflows/tauri-packages.yml`](../../.github/workflows/tauri-packages.yml)

Local commands:

- `just tauri-install`
- `just tauri-test`
- `just tauri-start`
- `just tauri-smoke`
- `just tauri-packaged-start`
- `just tauri-packaged-smoke`
- `just tauri-build`

Scope boundaries:

- Tauri is still experimental in this slice
- `.github/workflows/tauri-packages.yml` now provides an artifact-only GitHub Actions workflow for this shell
- Electron remains the most complete shell path
- Tauri uses a bootstrap HttpOnly cookie instead of Electron's hidden per-request header injection because this Tauri path does not currently have an Electron-equivalent external-localhost outgoing request header hook
- the hosted Tauri lane uses build-only `tauri-action`, not GitHub Release publication
- the current Tauri config now applies a minimal `app.security.csp` for Tauri-served shell assets, including the local splash window and localhost bootstrap surface
- that CSP is intentionally narrow and should not be read as production-hardening for the Django pages loaded over `http://127.0.0.1:<random-port>`
- Tauri is not a release-parity path in this slice
- the Windows support claim is limited to local plus CI-built NSIS installer generation, with manual install/run validation still required
- the current Windows config keeps Tauri's default `downloadBootstrapper` WebView2 installer behavior rather than an offline-ready embedded runtime
- the hosted Linux AppImage job currently applies `NO_STRIP=true` as an upstream `linuxdeploy` workaround rather than a claim of finished Linux release hardening
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
