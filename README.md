# Desktop Django Starter

Minimal, attendee-facing starter for shipping a Django app inside Electron with a bundled Python runtime.

This repository now includes a runnable development slice, a staged packaged-backend slice, and a sign/notarization-aware GitHub packaging slice: a tiny Django app served locally and supervised by Electron, with a bundled Python runtime staged under `electron/.stage/backend/python/` and packaged desktop artifacts built in GitHub Actions.

## Intent

- Be the canonical teaching repo for the DjangoCon Europe 2026 talk/blog cycle.
- Stay minimal, generic, and easy to adapt to an existing Django app.
- Show the hard parts people should not have to rediscover from scratch: process lifecycle, local runtime packaging, localhost boot, and cross-platform expectations.
- Use `djdesk` as reference material for packaging/build patterns only, not as the starter baseline.

## Current Status

Runnable starter slices:

- Django 6.0.3 project under `src/desktop_django_starter/`
- tiny server-rendered CRUD demo app under `src/example_app/`
- Electron 40 shell under `electron/`
- random-port localhost startup with `/health/` readiness polling
- minimal preload bridge for opening the app-data folder
- staged packaged-backend flow under `electron/.stage/backend/` with a bundled Python runtime, installed app dependencies, collected static assets, and `desktop_django_starter.settings.packaged`
- packaged-like Electron launcher that exercises the staged bundled-runtime contract locally
- on-demand GitHub Actions packaging for macOS, Windows, and Linux, with downloadable workflow artifacts, per-platform SHA-256 checksum files, env-driven macOS signing/notarization scaffolding, optional Windows signing inputs, and `just` helpers for triggering and fetching them

Auto-update and full production release automation are still deferred. The current slice is intended to make release signing/notarization expectations explicit without making unsigned local packaging unusable.

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
- `just electron-install`: install Electron dependencies
- `just electron-start`: start the Electron shell, which launches Django on a random localhost port
- `just packaged-stage`: build the staged packaged-backend bundle under `electron/.stage/backend`, including the bundled Python runtime
- `just packaged-start`: rebuild the staged bundle and launch Electron in packaged-like mode against the staged bundled runtime
- `just packaged-smoke`: rebuild the staged bundle and run a packaged-like Electron smoke launch that auto-exits after load
- `just package-dist`: build a local desktop package for the current host target (defaults to `--mac dmg`)
- `just package-dist-dir`: build an unpacked local desktop app for the current host target
- `just github-package`: trigger the GitHub Actions cross-platform packaging workflow for the current branch
- `just github-package-download <run-id>`: download a specific packaging workflow run into `dist/github-actions/<run-id>/`
- `just github-package-latest-run`: print the latest successful packaging workflow run id for the current branch
- `just github-package-latest-path`: print the local path for the last `github-package-download-latest` download
- `just github-package-download-latest`: download the latest successful packaging workflow run for the current branch
- `just dev`: same as `just electron-start`
- `just docs`: build the docs and open the generated site
- `just docs-serve`: run a live-reloading local docs server
- `just test`: run the Django and docs test suite
- `just build`: build the Python package metadata scaffold

## Quickstart

1. `just install`
2. `just electron-install`
3. `just dev`

For backend-only work, use `just backend-dev`.

For the packaged-mode staging slice, use `just packaged-start`.
The `electron/.stage/` directory is rebuilt on each packaged staging run and should be treated as ephemeral.

For GitHub-built install artifacts, use `just github-package` and then `just github-package-download-latest` once the workflow succeeds. The download helpers require the GitHub CLI plus an authenticated `gh` session and place per-platform artifacts under `dist/github-actions/<run-id>/`. `just github-package-latest-run` prints the current latest run id, `just github-package-download-latest` prints the downloaded paths and records the run id in `dist/github-actions/latest-run.txt`, and `just github-package-latest-path` prints the local directory for that latest downloaded run.
Pass a different branch as the first argument when needed, for example `just github-package my-branch`.
The current workflow builds one architecture per platform: macOS arm64 on `macos-latest`, plus Windows x64 and Linux x64 on the hosted runners.

## Packaging, Signing, and Manual Updates

Local packaging remains usable without any signing secrets:

- `just package-dist` builds a host-native installer artifact for the current machine
- `just package-dist-dir` builds an unpacked app directory for local inspection

When signing credentials are present, `electron-builder` now uses them directly:

- macOS signing uses the normal `CSC_LINK` or `CSC_NAME` inputs plus `CSC_KEY_PASSWORD` when needed
- macOS notarization is enabled only when a complete Apple credential set is present; the recommended path is `APPLE_API_KEY` plus `APPLE_API_KEY_ID` and `APPLE_API_ISSUER`
- Windows signing is optional and secret-driven; `WIN_CSC_LINK` plus `WIN_CSC_KEY_PASSWORD` is the baseline path, with optional publisher/timestamp inputs documented in [`docs/release.md`](docs/release.md)

Primary installer artifacts in this starter:

- macOS: signed/notarized DMG when secrets are configured, otherwise an unsigned DMG
- Windows: NSIS `.exe` installer, optionally signed
- Linux: AppImage output remains available, but Linux signing and verification are still out of scope for this slice

GitHub Actions packaging also writes one SHA-256 manifest per platform artifact set:

- macOS: `desktop-django-starter-macos-sha256.txt` for the DMG artifact upload
- Windows: `desktop-django-starter-windows-sha256.txt` for the NSIS `.exe` artifact upload
- Linux: `desktop-django-starter-linux-sha256.txt` for the AppImage artifact upload

Those checksum files are uploaded as separate workflow artifacts so an admin can verify the downloaded installer before promoting it into a connected release channel or transferring it through an offline/manual flow.

Manual update model for this repo:

- connected installs: download the installer plus its matching SHA-256 file from GitHub Actions artifacts, a GitHub Release, or your internal release channel, verify the checksum, then run the installer manually
- air-gapped installs: transfer the DMG or `.exe` plus its matching SHA-256 file through the approved offline channel, verify version and integrity, then run the installer manually
- local writable state survives reinstall/update because packaged mode keeps it under Electron's per-user app-data directory, with the SQLite database stored as `app.sqlite3`

## Staged Bundled Runtime Contract

The staged packaged-backend layout is now explicit enough to mirror a later packaged app:

- `electron/.stage/backend/manage.py`: Django entrypoint kept at backend root
- `electron/.stage/backend/src/`: app source tree
- `electron/.stage/backend/python/`: bundled Python runtime plus installed dependencies
- `electron/.stage/backend/staticfiles/`: collected static assets for `DEBUG=False`
- `electron/.stage/backend/runtime-manifest.json`: runtime metadata that records the staged interpreter and launcher contract

Electron packaged mode reads `runtime-manifest.json` to locate the bundled interpreter, then invokes `manage.py` from the backend root. The current staged manifest records the interpreter as `python/bin/python3.12` on POSIX and is designed to allow `python.exe` on Windows.

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
- A tiny example Django app that still feels real
- Clear extension points for replacing the example with your own Django project
- Cross-platform packaging guidance with Windows as a required proof point
- Plain GitHub Actions packaging and artifact download flow for macOS, Windows, and Linux, including env-driven signing/notarization scaffolding

## Production Gaps

- No auto-update feed, update server, or in-app updater is included.
- No GitHub Release publishing automation is wired yet; checksum generation exists, but promotion remains manual.
- Linux packaging still exists, but Linux signing and verification are not a baseline in this slice.
- Windows public-distribution hardening beyond optional signing inputs is still follow-on work.
