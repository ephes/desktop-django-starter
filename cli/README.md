# desktop-django-starter

Wrap any Django project in an Electron shell using an AI coding agent.

## Quick start

```bash
cd ~/projects/my-django-app
uvx desktop-django-starter init          # save a default harness once
uvx desktop-django-starter wrap          # preflight only
uvx desktop-django-starter wrap --run    # preflight + invoke agent
```

Or install for repeated use:

```bash
uv tool install desktop-django-starter
dds init
dds wrap
dds wrap --run
dds wrap --run --agent codex
dds wrap --run --harness pi --model openai-codex/gpt-5.4
```

## Commands

### `dds init`

Interactive first-run setup for wrapper defaults. It detects installed
supported harnesses (`claude`, `pi`, `codex`), lets you pick one default
harness, optionally saves a freeform default model string, and writes
user-level config under `~/.config/dds/config.toml` on Unix-like systems.

### `dds wrap`

Run from inside a Django project directory. By default, runs preflight checks
and prints the agent command. Add `--run` to invoke the agent.

`dds wrap --run` resolves the harness in this order: explicit CLI flags, saved
config, then auto-detect when exactly one supported harness is installed. If no
config exists yet and stdin is a TTY, `wrap --run` launches the same setup flow
inline. Non-interactive runs never prompt; when the harness is ambiguous they
fail with a message that points to `dds init` or `--harness`.

When using the `claude` harness, `--run` streams concise progress lines while
Claude works. Older `dds` builds delegated to Claude's default text output,
which could look idle until the agent finished.

Options:
- `--run` — invoke the agent after preflight passes
- `--agent NAME`, `--harness NAME` — agent harness to use: `claude`, `pi`, `codex`; overrides saved config or auto-detect
- `--model NAME` — model to pass to the selected agent; overrides the saved default model
- `--force` — bypass dirty-worktree and existing-electron/ checks
- `--emit-prompt` — print the resolved wrapping prompt to stdout

### `dds doctor`

Check that prerequisites are installed, bundled assets are intact, and the
current wrapper config plus available harnesses are sufficient for `wrap --run`.

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

## Maintainer release

Build and publish the PyPI wrapper package from the repo root:

```bash
just cli-publish
```

The `cli-publish` recipe runs `cli-test` and `cli-build` first. The PyPI wrapper
package is the `cli/` subproject. Use `just cli-build` or `just cli-publish`
instead of the root `just build` recipe for `uvx desktop-django-starter ...`
releases.
