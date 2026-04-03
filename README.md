# Desktop Django Starter

Minimal, attendee-facing starter for shipping a Django app inside Electron with a bundled Python runtime, now with experimental Tauri and Positron shells for local comparison work.

**Documentation: [desktop-django-starter.readthedocs.io](https://desktop-django-starter.readthedocs.io/en/latest/)**

This repository now includes a runnable development slice, a staged packaged-backend slice, a sign/notarization-aware GitHub packaging slice, plus experimental Tauri and Positron ports: a tiny Django app served locally and supervised by Electron or Tauri, plus an in-process Positron shell that keeps the shared Django core under `src/`. Electron remains the baseline release lane, while Tauri now also has a GitHub-hosted artifact-only packaging workflow built in the official `tauri-action` style.

## Intent

- Be the canonical teaching repo for the DjangoCon Europe 2026 talk/blog cycle.
- Stay minimal, generic, and easy to adapt to an existing Django app.
- Show the hard parts people should not have to rediscover from scratch: process lifecycle, local runtime packaging, localhost boot, and cross-platform expectations.
- Use `djdesk` as reference material for packaging/build patterns only, not as the starter baseline.

## Current Status

Runnable starter slices:

- Django 6.0.3 project under `src/desktop_django_starter/`
- tiny server-rendered CRUD demo app under `src/example_app/`, themed as "My Ponies" in the Flying Stable presentation layer
- background task visualization demo under `src/tasks_demo/`, themed as "Stable Routines", with animated pulse-ring indicators, polling-based live updates, and real `django_tasks` execution backed by SQLite
- Electron 40 shell under `shells/electron/`
- Tauri 2 shell under `shells/tauri/` for local experiment scope, using the same staged backend contract and child-process worker model
- Positron shell under `shells/positron/` for local experiment scope, running Django plus the optional task worker in-process inside a Toga web view
- random-port localhost startup with `/health/` readiness polling
- minimal preload bridge for opening the app-data folder
- staged packaged-backend flow under `.stage/backend/` with a bundled Python runtime, installed app dependencies, collected static assets, and `desktop_django_starter.settings.packaged`
- packaged-like Electron launcher that exercises the staged bundled-runtime contract locally, including the supervised task worker
- experimental packaged-like Tauri launcher plus local host-bundle build paths, including a prepared but unverified Windows NSIS installer path, a macOS DMG path, and a GitHub-hosted artifact-only packaging workflow
- experimental Positron local start/smoke path plus a local macOS build/DMG path through Briefcase, with ad-hoc signing explicitly documented as local-only
- on-demand GitHub Actions packaging for macOS, Windows, and Linux, with downloadable workflow artifacts, per-platform SHA-256 checksum files, env-driven macOS signing/notarization scaffolding, optional Windows signing inputs, and `just` helpers for triggering and fetching them

Auto-update and full production release automation are still deferred. The current slice is intended to make release signing/notarization expectations explicit without making unsigned local packaging unusable.

The example app uses a branded presentation layer called "Flying Stable" (a Pegasus/pony theme) to demonstrate that the starter can carry a real visual identity while remaining a generic teaching scaffold underneath. The theme includes a dark topnav with logo and brand name, teal page headers with background images, a content panel with toolbar, a sticky footer, CSS custom-property design tokens, SVG empty-state illustrations, an in-page delete-confirmation modal, client-side form validation with themed error messages, a splash screen at `/splash/` that Electron now shows during backend startup, and packaged app icons generated in `shells/electron/assets/icons/` and `shells/tauri/src-tauri/icons/` from the shared source art under `assets/brand/`. Item statuses are themed as Grazing (backlog), Galloping (active), and Show Ready (done). Development mode includes `django-browser-reload` for auto-reload.

## Docs

- [`docs/specification.md`](docs/specification.md): main product and technical specification
- [`docs/architecture.md`](docs/architecture.md): intended runtime model and draft repo shape
- [`docs/decisions.md`](docs/decisions.md): repo-local decisions captured from the initial planning pass
- [`docs/release.md`](docs/release.md): packaging secrets, installer artifacts, and connected/offline manual update guidance
- [`docs/agent-use.md`](docs/agent-use.md): how coding agents should consume this repo and reuse its skill

The docs are built with Sphinx over the Markdown sources in `docs/` and are intended to be publishable on Read the Docs.

## Agent Consumers

- `llms.txt`: concise repo entry point for coding agents
- `skills/wrap-existing-django-in-electron/SKILL.md`: reusable workflow for adapting an existing Django project to an Electron shell
- `docs/agent-use.md`: agent-oriented usage notes and guardrails

## Development

- `just install`: install the local environment with `uv`
- `just migrate`: apply the local SQLite migrations
- `just backend-dev`: run the Django app directly on `127.0.0.1:8000`
- `just task-worker`: run the single background task worker for `/tasks/` without Electron
- `just electron-install`: install Electron dependencies
- `just electron-start`: start the Electron shell, which launches Django plus one background task worker on a random localhost port
- `just tauri-install`: install Tauri shell dependencies
- `just tauri-test`: compile-check the Tauri shell with `cargo test`
- `just tauri-start`: start the Tauri shell, which launches Django plus one background task worker on a random localhost port
- `just tauri-smoke`: start the Tauri shell and auto-exit after the first page load
- `just tauri-packaged-start`: rebuild the shared staged backend and launch the Tauri shell against the packaged runtime contract
- `just tauri-packaged-smoke`: rebuild the shared staged backend, launch the Tauri shell against the packaged runtime contract, and auto-exit after the first page load
- `just tauri-build`: build a local Tauri host bundle, defaulting to `dmg` on macOS, `nsis` on Windows, and `appimage` on Linux
- `just positron-install`: install the Positron shell environment with `uv`
- `just positron-check`: run Django's system checks from the Positron shell environment
- `just positron-start`: start the Positron shell, which runs Django plus one background task worker in-process
- `just positron-smoke`: start the Positron shell and auto-exit after the first page load
- `just positron-icons`: regenerate `shells/positron/resources/app-icon.png` and, on macOS, `app-icon.icns` from `assets/brand/flying-stable-app-icon.svg`
- `just positron-create`: create the local macOS Briefcase app scaffold for Positron
- `just positron-build`: build the local macOS Positron app bundle
- `just positron-package-dmg`: package a local macOS Positron DMG with Briefcase ad-hoc signing
- `npm --prefix shells/electron run icons`: regenerate the packaged app icon PNG and macOS ICNS from `assets/brand/flying-stable-app-icon.svg` into `shells/electron/assets/icons/` (requires `rsvg-convert` from `librsvg`; macOS uses the built-in `iconutil` for ICNS output)
- `npm --prefix shells/tauri run icons`: regenerate the Tauri icon set in `shells/tauri/src-tauri/icons/` from the same shared SVG source

The generated Electron icon outputs under `shells/electron/assets/icons/` are kept in the repo so a fresh clone can still run the shell and packaging flow before local icon-tooling is installed.
- `just packaged-stage`: build the staged packaged-backend bundle under `.stage/backend`, including the bundled Python runtime
- `just packaged-start`: rebuild the staged bundle and launch Electron in packaged-like mode against the staged bundled runtime
- `just packaged-smoke`: rebuild the staged bundle and run a packaged-like Electron smoke launch that auto-exits after load
- `just package-dist`: build a local desktop package for the current host target (defaults to `--mac dmg`)
- `just package-dist-dir`: build an unpacked local desktop app for the current host target
- `just github-package`: trigger the GitHub Actions cross-platform packaging workflow for the current branch
- `just github-package-download <run-id>`: download a specific packaging workflow run into `dist/github-actions/<run-id>/`
- `just github-package-latest-run`: print the latest successful packaging workflow run id for the current branch
- `just github-package-latest-path`: print the local path for the last `github-package-download-latest` download
- `just github-package-download-latest`: download the latest successful packaging workflow run for the current branch
- `just github-package-tauri`: trigger the Tauri GitHub Actions packaging workflow for the current branch
- `just github-package-tauri-download <run-id>`: download a specific Tauri packaging workflow run into `dist/github-actions/tauri/<run-id>/`
- `just github-package-tauri-latest-run`: print the latest successful Tauri packaging workflow run id for the current branch
- `just github-package-tauri-latest-path`: print the local path for the last `github-package-tauri-download-latest` download
- `just github-package-tauri-download-latest`: download the latest successful Tauri packaging workflow run for the current branch
- `just dev`: same as `just electron-start`
- `just docs`: build the docs and open the generated site
- `just docs-serve`: run a live-reloading local docs server
- `just loc`: print a `cloc` summary plus a per-directory code breakdown, with a Python fallback when `cloc` is absent
- `just test`: run the Django and docs test suite
- `just build`: build the Python package metadata scaffold

## Quickstart

1. `just install`
2. `just electron-install`
3. `just dev`

For backend-only work, use `just backend-dev`.
When you need the real `/tasks/` demo outside Electron, run `just task-worker` in a second terminal.

For the experimental Tauri shell, use `just tauri-install` once and then `just tauri-start`. The Tauri path keeps the same localhost Django plus `db_worker` subprocess model as Electron, now with a shell-local startup splash while backend bootstrap runs in the background. Its Tauri-side assets now use a minimal CSP for the local splash/bootstrap surface, not as a claim of release-grade hardening for the Django pages loaded over `http://127.0.0.1:<random-port>`. This slice now also includes `.github/workflows/tauri-packages.yml`, an artifact-only GitHub-hosted packaging lane built around `tauri-action` without GitHub Release publication. Tauri is still not a release-parity path: Electron remains the more complete release lane, Tauri signing/notarization automation is not wired here, and Windows installer install/run validation still requires a real live Windows machine. The current Tauri NSIS config keeps Tauri's default `downloadBootstrapper` WebView2 behavior rather than claiming an offline-ready embedded runtime.

For the experimental Positron shell, use `just positron-install` once and then `just positron-start`. The Positron path intentionally keeps a different runtime model: Django and the optional `tasks_demo` worker run in-process on threads, there is no splashscreen-parity requirement on macOS, and packaged builds remain a local-only Briefcase experiment.

For the packaged-mode staging slice, use `just packaged-start`.
The `.stage/` directory is rebuilt on each packaged staging run and should be treated as ephemeral.

For GitHub-built Electron install artifacts, use `just github-package` and then `just github-package-download-latest` once the workflow succeeds. The download helpers require the GitHub CLI plus an authenticated `gh` session and place per-platform artifacts under `dist/github-actions/<run-id>/`. `just github-package-latest-run` prints the current latest run id, `just github-package-download-latest` prints the downloaded paths and records the run id in `dist/github-actions/latest-run.txt`, and `just github-package-latest-path` prints the local directory for that latest downloaded run.
Pass a different branch as the first argument when needed, for example `just github-package my-branch`.

For GitHub-built Tauri artifacts, use `just github-package-tauri` and then `just github-package-tauri-download-latest` once the workflow succeeds. Those helpers place artifacts under `dist/github-actions/tauri/<run-id>/`, record the last downloaded run in `dist/github-actions/tauri/latest-run.txt`, and keep the same branch-selection behavior as the Electron helpers.

Both hosted workflows currently build one architecture per platform: macOS arm64 on `macos-latest`, plus Windows x64 and Linux x64 on the hosted runners.

## Packaging, Signing, and Manual Updates

Local packaging remains usable without any signing secrets:

- `just package-dist` builds a host-native installer artifact for the current machine
- `just package-dist-dir` builds an unpacked app directory for local inspection
- `just tauri-build` builds a local Tauri host bundle; the default target is `dmg` on macOS, `nsis` on Windows, and `appimage` on Linux

The Tauri packaging path is explicitly narrower than Electron in this slice:

- it reuses `.stage/backend` as bundled resources
- it now includes `.github/workflows/tauri-packages.yml`, an official-style `tauri-action` workflow in build-only mode with explicit artifact uploads and checksum manifests
- it now applies a minimal CSP to Tauri-served shell assets such as the local splash window, while the Django UI still loads over localhost and is not presented as production-hardening
- it keeps Tauri's default Windows `downloadBootstrapper` WebView2 installer behavior rather than switching to the much larger `offlineInstaller`
- it does not add GitHub Release publication, auto-update wiring, or signing/notarization parity with Electron
- installer install/run validation still requires a real live Windows machine and is not proved by CI alone

The Positron packaging path is also explicitly narrower than Electron:

- it is local-only and not part of `.github/workflows/desktop-packages.yml`
- it uses Briefcase rather than the Electron/Tauri staged-backend subprocess model
- local macOS DMG packaging currently depends on `briefcase package macOS app --packaging-format dmg --adhoc-sign`
- the ad-hoc-signed app is suitable only for the local machine that built it and is not a release-grade artifact
- it is not a release-parity path in this slice
- Windows packaged-build parity is not claimed for Positron in this slice

When signing credentials are present, `electron-builder` now uses them directly:

- macOS signing uses the normal `CSC_LINK` or `CSC_NAME` inputs plus `CSC_KEY_PASSWORD` when needed
- macOS notarization is enabled only when a complete Apple credential set is present; the recommended path is `APPLE_API_KEY` plus `APPLE_API_KEY_ID` and `APPLE_API_ISSUER`
- Windows signing is optional and secret-driven; `WIN_CSC_LINK` plus `WIN_CSC_KEY_PASSWORD` is the baseline path, with optional publisher/timestamp inputs documented in [`docs/release.md`](docs/release.md)

Primary installer artifacts in this starter:

- macOS: signed/notarized DMG when secrets are configured, otherwise an unsigned DMG
- Windows: NSIS `.exe` installer, optionally signed
- Linux: AppImage output remains available, but Linux signing and verification are still out of scope for this slice

GitHub Actions packaging also writes SHA-256 manifests per platform artifact set.

Electron workflow manifests:

- macOS: `desktop-django-starter-macos-sha256.txt` for the DMG artifact upload
- Windows: `desktop-django-starter-windows-sha256.txt` for the NSIS `.exe` artifact upload
- Linux: `desktop-django-starter-linux-sha256.txt` for the AppImage artifact upload

Tauri workflow manifests:

- macOS: `desktop-django-starter-tauri-macos-sha256.txt` for the DMG artifact upload
- Windows: `desktop-django-starter-tauri-windows-sha256.txt` for the NSIS `.exe` artifact upload
- Linux: `desktop-django-starter-tauri-linux-sha256.txt` for the AppImage artifact upload

Those checksum files are uploaded as separate workflow artifacts so an admin can verify the downloaded installer before promoting it into a connected release channel or transferring it through an offline/manual flow.

Manual update model for this repo:

- connected installs: download the installer plus its matching SHA-256 file from GitHub Actions artifacts, a GitHub Release, or your internal release channel, verify the checksum, then run the installer manually
- air-gapped installs: transfer the DMG or `.exe` plus its matching SHA-256 file through the approved offline channel, verify version and integrity, then run the installer manually
- local writable state survives reinstall/update because packaged mode keeps it under Electron's per-user app-data directory, with the SQLite database stored as `app.sqlite3`

## Staged Bundled Runtime Contract

The staged packaged-backend layout is now explicit enough to mirror a later packaged app:

- `.stage/backend/manage.py`: Django entrypoint kept at backend root
- `.stage/backend/src/`: app source tree
- `.stage/backend/python/`: bundled Python runtime plus installed dependencies
- `.stage/backend/staticfiles/`: collected static assets for `DEBUG=False`
- `.stage/backend/runtime-manifest.json`: runtime metadata that records the staged interpreter and launcher contract

Electron and Tauri packaged mode read `runtime-manifest.json` to locate the bundled interpreter, then invoke `manage.py` from the backend root. The current staged manifest records the interpreter as `python/bin/python3.12` on POSIX and is designed to allow `python.exe` on Windows.

The shell-neutral staging build now lives in `scripts/stage-backend.cjs`, which writes the staged backend once at the repo root so later shells can consume the same contract.

Electron and Tauri now supervise two backend commands from that staged bundle:

- `manage.py runserver ...` for the local web app
- `manage.py db_worker --queue-name default ...` for the `/tasks/` demo worker

Dependencies are installed into the staged runtime under `backend/python/lib/python3.12/site-packages` on the current macOS/Linux path. On Windows, the same contract is expected to resolve inside the staged `python/` tree rather than the repo environment.

Packaged mode still sets a small runtime environment at launch time:

- `DJANGO_SETTINGS_MODULE=desktop_django_starter.settings.packaged`
- `DESKTOP_DJANGO_APP_DATA_DIR` for writable SQLite/app data
- `DESKTOP_DJANGO_BUNDLE_DIR` for bundle-relative assets
- `DESKTOP_DJANGO_HOST` and `DESKTOP_DJANGO_PORT` for localhost startup
- `DJANGO_SECRET_KEY` if one is not already supplied
- `PYTHONUNBUFFERED=1`

## What This Repo Should Eventually Provide

- A minimal Electron shell that starts Django locally
- A bundled Python runtime for packaged builds
- A tiny example Django app that still feels real, with a themed presentation layer (currently "Flying Stable") that can be replaced
- Clear extension points for replacing the example with your own Django project
- Cross-platform packaging guidance with Windows as a required proof point
- Plain GitHub Actions packaging and artifact download flow for macOS, Windows, and Linux, including env-driven signing/notarization scaffolding

## Production Gaps

- No auto-update feed, update server, or in-app updater is included.
- No GitHub Release publishing automation is wired yet; checksum generation exists, but promotion remains manual.
- Linux packaging still exists, but Linux signing and verification are not a baseline in this slice.
- Windows public-distribution hardening beyond optional signing inputs is still follow-on work.
- Tauri now has an experimental GitHub-hosted artifact workflow, but it still does not publish Releases, does not claim signing/notarization parity with Electron, and still needs real Windows install/run validation.
- Positron remains an experimental local shell path with no GitHub Actions artifact lane, no splashscreen-parity claim on macOS, and no Windows packaged parity claim in this slice.
