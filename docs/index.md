# Desktop Django Starter

Minimal documentation for the specification-first `desktop-django-starter` repository.

The initial focus of this project is to define a clean, teachable baseline for packaging Django inside Electron before application code and packaging code are implemented.

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
- `just docs` builds the documentation and opens it locally
- `just docs-serve` starts a live-reloading docs server
- `just test` runs the smoke-test suite
- `just build` builds the Python package metadata scaffold
