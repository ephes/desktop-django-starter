# Desktop Django Starter

Minimal documentation for `desktop-django-starter`, a teachable Django-plus-Electron reference with a runnable development slice, a staged packaged-backend slice, a sign/notarization-aware Electron GitHub packaging slice, and experimental Tauri and Positron shells for local comparison work. Electron remains the baseline release-oriented shell, while Tauri now has an experimental GitHub-hosted artifact lane.

The current implementation includes a local Django app, an Electron shell that supervises it over localhost, a `/health/` readiness check, a tiny CRUD demo, a background task visualization demo with animated indicators and live polling, a packaged-like staging flow with a bundled Python runtime plus collected static assets, and on-demand GitHub Actions workflows that build desktop artifacts for macOS, Windows, and Linux. macOS signing/notarization scaffolding and optional Windows signing inputs are now documented and wired into packaging; auto-update is still deferred.

```{toctree}
:maxdepth: 2
:caption: Contents

specification
architecture
decisions
release
backlog
done
agent-use
shells/electron
shells/tauri
shells/positron
```

## Local Development

- `just install` installs the development environment with `uv`
- `just electron-install` installs the Electron dependencies
- `just dev` starts Electron, which launches Django on a random localhost port
- `just tauri-install` installs the Tauri shell dependencies
- `just tauri-test` compile-checks the Tauri shell
- `just tauri-start` starts the Tauri shell, which launches Django on a random localhost port
- `just tauri-packaged-start` launches the packaged-like Tauri path against `.stage/backend`
- `just tauri-build` builds a local Tauri host bundle, defaulting to `dmg` on macOS, `nsis` on Windows, and `appimage` on Linux
- `just positron-install` installs the Positron shell environment
- `just positron-check` runs Django checks from the Positron shell environment
- `just positron-start` starts the Positron shell, which runs Django and the optional task worker in-process
- `just positron-smoke` starts the Positron shell and exits after the first page load
- `just positron-package-dmg` packages a local macOS Positron DMG with Briefcase ad-hoc signing
- `just backend-dev` runs Django directly on `127.0.0.1:8000`
- `just packaged-stage` builds the staged packaged backend under `.stage/backend`
- `just packaged-start` launches the packaged-like Electron path against the staged backend and bundled runtime
- `just packaged-smoke` runs a packaged-like smoke launch and exits automatically after load
- `just package-dist` builds a local packaged desktop artifact for the current host target
- `just package-dist-dir` builds an unpacked local desktop app for the current host target
- `just github-package` triggers the cross-platform GitHub Actions packaging workflow for the current branch
- `just github-package-download <run-id>` downloads one packaging workflow run into `dist/github-actions/<run-id>/`
- `just github-package-latest-run` prints the latest successful packaging workflow run id for the current branch
- `just github-package-latest-path` prints the local path for the last `github-package-download-latest` download
- `just github-package-download-latest` downloads the latest successful packaging workflow run for the current branch and records it under `dist/github-actions/latest-run.txt`, with a best-effort `dist/github-actions/latest` symlink when the platform allows it
- `just github-package-tauri` triggers the Tauri GitHub Actions packaging workflow for the current branch
- `just github-package-tauri-download <run-id>` downloads one Tauri packaging workflow run into `dist/github-actions/tauri/<run-id>/`
- `just github-package-tauri-latest-run` prints the latest successful Tauri packaging workflow run id for the current branch
- `just github-package-tauri-latest-path` prints the local path for the last `github-package-tauri-download-latest` download
- `just github-package-tauri-download-latest` downloads the latest successful Tauri packaging workflow run for the current branch and records it under `dist/github-actions/tauri/latest-run.txt`, with a best-effort `dist/github-actions/tauri/latest` symlink when the platform allows it
- `just docs` builds the documentation and opens it locally
- `just docs-serve` starts a live-reloading docs server
- `just test` runs the backend and docs test suite
- `just build` builds the Python package metadata scaffold

## Staged Runtime Contract

The packaged-like staging flow now writes a concrete backend payload under `.stage/backend/`:

- `manage.py` remains at backend root
- `src/` remains in normal source layout
- `python/` contains the bundled runtime and installed app dependencies
- `staticfiles/` contains collected static assets for packaged settings
- `runtime-manifest.json` records the staged interpreter path and launcher metadata

Electron and Tauri packaged mode use that manifest to resolve the interpreter from the staged backend instead of falling back to the repo's `uv` environment.

The GitHub packaging helpers use the GitHub CLI locally, require an authenticated `gh` session, and accept an optional first argument to target a different branch when the current checkout is not the branch you want to build or query. Electron downloads live under `dist/github-actions/<run-id>/`, while Tauri downloads live under `dist/github-actions/tauri/<run-id>/`. Both workflows currently build macOS arm64 plus Windows x64 and Linux x64 artifacts.

See [release](release.md) for the signing secrets, installer/update guidance, and the explicit boundary that Tauri's hosted lane is still artifact-only and not release parity.
