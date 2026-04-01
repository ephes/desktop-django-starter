# Desktop Django Starter

Minimal documentation for `desktop-django-starter`, a teachable Django-plus-Electron reference with a runnable development slice, a staged packaged-backend slice, a sign/notarization-aware GitHub packaging slice in place, plus experimental Tauri and Positron shells for local comparison work.

The current implementation includes a local Django app, an Electron shell that supervises it over localhost, a `/health/` readiness check, a tiny CRUD demo, a background task visualization demo with animated indicators and live polling, a packaged-like staging flow with a bundled Python runtime plus collected static assets, and an on-demand GitHub Actions workflow that builds desktop artifacts for macOS, Windows, and Linux. macOS signing/notarization scaffolding and optional Windows signing inputs are now documented and wired into packaging; auto-update is still deferred.

```{toctree}
:maxdepth: 2
:caption: Contents

specification
architecture
decisions
release
agent-use
shells/electron
shells/tauri
shells/positron
multi-shell-plan
```

## Local Development

- `just install` installs the development environment with `uv`
- `just electron-install` installs the Electron dependencies
- `just dev` starts Electron, which launches Django on a random localhost port
- `just tauri-install` installs the Tauri shell dependencies
- `just tauri-test` compile-checks the Tauri shell
- `just tauri-start` starts the Tauri shell, which launches Django on a random localhost port
- `just tauri-packaged-start` launches the packaged-like Tauri path against `.stage/backend`
- `just tauri-build` builds a local Tauri host bundle, defaulting to a macOS DMG on macOS
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
- `just github-package-download-latest` downloads the latest successful packaging workflow run for the current branch
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

The GitHub packaging helpers use the GitHub CLI locally, require an authenticated `gh` session, and accept an optional first argument to target a different branch when the current checkout is not the branch you want to build or query. `just github-package-latest-run` prints the current latest successful run id, `just github-package-download-latest` prints the downloaded artifact paths and records the run id in `dist/github-actions/latest-run.txt`, and `just github-package-latest-path` prints the local directory for that latest downloaded run. The current workflow builds macOS arm64 plus Windows x64 and Linux x64 artifacts.

See [release](release.md) for the signing secrets, installer/update guidance, and the explicit boundary that Tauri and Positron local bundles do not yet have GitHub Actions artifact lanes.
