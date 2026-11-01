# Tauri Shell

Status: implemented as an experimental shell in this slice, now with local bundle commands, an updater-capable GitHub Actions artifact workflow, and a packaged-only connected updater experiment.

The current Tauri port lives under [`shells/tauri/`](../../shells/tauri/).

Current responsibilities:

- show a shell-local Flying Stable splash window immediately while backend startup runs
- start Django on a random localhost port and wait for `/health/`
- generate a fresh per-session shell-to-Django auth token, pass it to Django as `DESKTOP_DJANGO_AUTH_TOKEN`, and include `X-Desktop-Django-Token` in the readiness poll
- load the web view through Django's `/desktop-auth/bootstrap/` URL so Django can set an HttpOnly same-origin auth cookie before redirecting to the app
- supervise both `manage.py runserver` and `manage.py db_worker` as child processes
- shut down Unix child processes with `SIGTERM` first, then force-kill only after a 2-second grace period
- pass `DESKTOP_DJANGO_APP_VERSION` (the app's package version) to every `manage.py` command, so packaged settings keep the database, media and cache in `<app-data>/state/<version>/`; the shell decides whether to seed demo content by checking `<app-data>/state/<version>/app.sqlite3` before `migrate` (`state_dir_name` in `lib.rs` is a tested port of the Python sanitizer). After an upgrade the first launch seeds again on the copied database, which is harmless because seeding is idempotent
- start every Python child (`migrate`, `seed_demo_content`, `runserver`, `db_worker`) through `desktop_process_guard.py --app-key <key> --instance <run id> --watch-stdin -- manage.py ...` with a piped stdin that the shell holds open for the child's lifetime; if the shell dies, the operating system closes the pipe and the guard exits instead of leaving an orphan. The guard is looked up as `<backend_root>/desktop_process_guard.py` (staged backend) or `<backend_root>/scripts/desktop_process_guard.py` (repo); without it the shell runs `manage.py` directly. The normal shutdown still uses `SIGTERM`/`SIGKILL` or `taskkill /t /f`
- keep `<app-data>/desktop-shell-session.json` (`app_key`, `running`, `shell_pid`). The app key is generated once; `running` is set to `true` at startup and back to `false` after the children are stopped on a normal exit. If a launch finds `running: true`, it lists processes (`ps -axww -o pid=,command=` on macOS/Linux, PowerShell `Get-CimInstance Win32_Process` on Windows), stops those whose command line has `desktop_process_guard.py --app-key <app_key>` (`SIGTERM`, 2 seconds, then `SIGKILL`; `taskkill /pid N /t /f` on Windows) and logs each one. This runs after the single-instance check and before `migrate`
- ask before quitting while background tasks are running or queued: closing the main window, Cmd+Q, or any other exit request is held, the shell reads `GET /desktop/activity/` with the auth token (1-second timeouts, off the main thread), and if tasks are active shows a "Quit" / "Cancel" dialog. Idle, a failed request, or "Quit" continue with the normal exit (children stopped, session marked clean); smoke runs, startup-error exits and update installs never ask, and a second quit request while the dialog is open does not open another one
- in packaged mode, check a configured HTTPS updater endpoint after the first main-window load and prompt before downloading/installing a newer signed update
- consume the shared staged backend from `.stage/backend/` for packaged-like runs and local bundle builds
- bundle shell-local icon outputs generated into `shells/tauri/src-tauri/icons/` from the shared source art under `assets/brand/`
- build hosted CI artifacts through [`.github/workflows/tauri-packages.yml`](../../.github/workflows/tauri-packages.yml), including updater payloads and `.sig` files when a signing key is configured

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
- `.github/workflows/tauri-packages.yml` now provides an updater-capable GitHub Actions workflow for this shell while still staying artifact-only
- Electron remains the most complete shell path
- the Tauri main window has no navigation or redirect guard yet (no `on_navigation` handler), and it injects the `window.desktop` bridge into every page it loads; unlike Electron, a link or server-side redirect to another origin loads inside the app window with the bridge attached
- the bridge's one command, `open_app_data_directory`, is declared in an app ACL manifest (`src-tauri/build.rs`) and granted to Django pages by `src-tauri/capabilities/django-pages.json`, which is scoped to `http://127.0.0.1:*`; Tauri 2.12 and newer reject app commands from remote origins without such a capability, and Tauri treats the localhost Django origin as remote. The command also refuses callers that are not on this session's exact Django origin, the same rule as Electron's IPC sender check
- Tauri uses a bootstrap HttpOnly cookie instead of Electron's hidden per-request header injection because this Tauri path does not currently have an Electron-equivalent external-localhost outgoing request header hook
- release builds use the Windows GUI subsystem, and the Python, `uv` and `taskkill` children are started with `CREATE_NO_WINDOW`, so a packaged Windows app does not open console windows (not yet validated on a live Windows install)
- the Tauri updater uses `tauri-plugin-updater`, not a Django localhost API or a broadened shell bridge
- `tauri.conf.json` keeps a placeholder `plugins.updater` block because Tauri requires it when `bundle.createUpdaterArtifacts` is enabled; the real endpoint list and public key still come from `DESKTOP_DJANGO_TAURI_UPDATE_ENDPOINTS` plus `DESKTOP_DJANGO_TAURI_UPDATE_PUBLIC_KEY`
- packaged update checks stay disabled unless `DESKTOP_DJANGO_TAURI_UPDATE_ENDPOINTS` and `DESKTOP_DJANGO_TAURI_UPDATE_PUBLIC_KEY` are set at build time or supplied at runtime
- the hosted Tauri lane uses build-only `tauri-action`, not GitHub Release publication
- the current Tauri config now applies a minimal `app.security.csp` for Tauri-served shell assets, including the local splash window and localhost bootstrap surface
- that CSP is intentionally narrow and should not be read as production-hardening for the Django pages loaded over `http://127.0.0.1:<random-port>`
- Tauri now matches Electron's Unix shutdown shape more closely, but Windows still uses forced process-tree teardown because that remains the most reliable packaged-app cleanup path in this repo
- Tauri is not a release-parity path in this slice
- the Windows support claim is limited to local plus CI-built NSIS installer generation, with manual install/run validation still required
- the current Windows config keeps Tauri's default `downloadBootstrapper` WebView2 installer behavior rather than an offline-ready embedded runtime
- the hosted Linux AppImage job currently applies `NO_STRIP=true` as an upstream `linuxdeploy` workaround rather than a claim of finished Linux release hardening
- local `just tauri-build` runs now pass `--no-sign` automatically when `TAURI_SIGNING_PRIVATE_KEY` is absent so unsigned local bundles still build even though `createUpdaterArtifacts` is enabled in config
- `just tauri-build` now also prints a Windows NSIS validation checklist when run on Windows, while `/docs/release.md` keeps the canonical written checklist
- installer install/run validation still needs a real live Windows machine and is not automated in this repo
- on macOS the default Quit menu item is replaced by a custom item with the same Cmd+Q shortcut, because the native `terminate:` path reaches Tauri only as the unpreventable `RunEvent::Exit`. Quitting from the Dock menu, logging out or shutting down still uses `terminate:` and skips the background-task prompt (the children are still stopped)
- the Windows parts of the lifecycle work (the guard's Job Object, the PowerShell process listing and `taskkill` orphan cleanup) compile only under `#[cfg(windows)]` and are not yet validated on a live Windows machine; the stdin watchdog, orphan cleanup and version-isolated state were validated on macOS

Current minimal CSP posture:

- `default-src 'self'`
- `connect-src` is limited to Tauri IPC plus localhost (`ipc:`, `http://ipc.localhost`, `http://127.0.0.1:*`, `http://localhost:*`)
- inline style is still allowed for the shell-local splash document
- the policy blocks plugin/object embedding and framing with `object-src 'none'` and `frame-ancestors 'none'`
- this covers the Tauri-served splash/bootstrap assets only; the Django UI remains a localhost-served renderer with its own separate hardening story

`tasks_demo` posture in this slice:

- supported
- Tauri follows the same staged-backend subprocess model as Electron and starts `db_worker` after Django passes the `/health/` readiness check
