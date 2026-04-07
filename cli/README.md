# desktop-django-starter

Wrap any Django project in an Electron shell using an AI coding agent.

## Quick start

```bash
cd ~/projects/my-django-app
uvx desktop-django-starter wrap          # preflight only
uvx desktop-django-starter wrap --run    # preflight + invoke agent
```

Or install for repeated use:

```bash
uv tool install desktop-django-starter
dds wrap
dds wrap --run
dds wrap --run --agent codex
```

## Commands

### `dds wrap`

Run from inside a Django project directory. By default, runs preflight checks
and prints the agent command. Add `--run` to invoke the agent.

Options:
- `--run` — invoke the agent after preflight passes
- `--agent NAME` — agent to use: `claude` (default), `pi`, `codex`
- `--force` — bypass dirty-worktree and existing-electron/ checks
- `--emit-prompt` — print the resolved wrapping prompt to stdout

### `dds doctor`

Check that prerequisites (node, npm, just, agent CLIs) are installed and
that bundled assets are intact.

## What happens after wrapping

The agent creates an `electron/` directory and justfile targets in your project:

```bash
just desktop-dev          # Electron + Django dev mode
just desktop-dev-smoke    # headless boot + health check
npm --prefix electron test  # node-side tests
```

## Version

Every wrap is stamped with the `dds` version so you can reproduce results.
The package version tracks the starter repo release.
