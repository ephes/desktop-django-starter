# Desktop Django Starter

Minimal documentation for `desktop-django-starter`, a teachable Django-plus-Electron reference with the first runnable development slice in place.

The current implementation includes a local Django app, an Electron shell that supervises it over localhost, a `/health/` readiness check, and a tiny CRUD demo. Packaged-runtime and distribution work are still deferred.

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
- `just docs` builds the documentation and opens it locally
- `just docs-serve` starts a live-reloading docs server
- `just test` runs the backend and docs test suite
- `just build` builds the Python package metadata scaffold
