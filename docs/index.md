# Desktop Django Starter

Minimal documentation for `desktop-django-starter`, a teachable Django-plus-Electron reference with a runnable development slice and a staged packaged-backend slice in place.

The current implementation includes a local Django app, an Electron shell that supervises it over localhost, a `/health/` readiness check, a tiny CRUD demo, and a packaged-like staging flow with a bundled Python runtime plus collected static assets. Distribution artifacts are still deferred.

```{toctree}
:maxdepth: 2
:caption: Contents

specification
architecture
decisions
agent-use
```

## Local Development

- `just install` installs the development environment with `uv`
- `just electron-install` installs the Electron dependencies
- `just dev` starts Electron, which launches Django on a random localhost port
- `just backend-dev` runs Django directly on `127.0.0.1:8000`
- `just packaged-stage` builds the staged packaged backend under `electron/.stage/backend`
- `just packaged-start` launches the packaged-like Electron path against the staged backend and bundled runtime
- `just packaged-smoke` runs a packaged-like smoke launch and exits automatically after load
- `just docs` builds the documentation and opens it locally
- `just docs-serve` starts a live-reloading docs server
- `just test` runs the backend and docs test suite
- `just build` builds the Python package metadata scaffold

## Staged Runtime Contract

The packaged-like staging flow now writes a concrete backend payload under `electron/.stage/backend/`:

- `manage.py` remains at backend root
- `src/` remains in normal source layout
- `python/` contains the bundled runtime and installed app dependencies
- `staticfiles/` contains collected static assets for packaged settings
- `runtime-manifest.json` records the staged interpreter path and launcher metadata

Electron packaged mode uses that manifest to resolve the interpreter from the staged backend instead of falling back to the repo's `uv` environment.
