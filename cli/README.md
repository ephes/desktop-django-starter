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
dds wrap --run --harness pi --model openai-codex/gpt-6.2-sol
```

## Commands

### `dds init`

Interactive first-run setup for wrapper defaults. It detects installed
supported harnesses (`claude`, `pi`, `codex`), lets you pick one default
harness, optionally saves a freeform default model string, and writes
user-level config. On Unix-like systems, an absolute `XDG_CONFIG_HOME` places
it at `$XDG_CONFIG_HOME/dds/config.toml`. If the variable is unset, empty, or
relative, DDS uses `~/.config/dds/config.toml`. DDS checks that the new
configuration is readable as UTF-8 TOML before saving it. An unrepresentable
model value reports an error and leaves any existing defaults in place.

### `dds wrap`

Run from inside a Django project directory. By default, runs preflight checks
and prints the agent command. Add `--run` to invoke the agent.

`dds wrap --run` resolves the harness in this order: explicit CLI flags, saved
config, then auto-detect when exactly one supported harness is installed. If no
config exists yet and stdin is a TTY, `wrap --run` launches the same setup flow
inline. Non-interactive runs never prompt; when the harness is ambiguous they
fail with a message that points to `dds init` or `--harness`.
A config file that disappears before it can be opened is treated as missing.
Other read failures, such as permission errors, stop harness resolution and
report the config path.

When using the `claude` harness, `--run` streams concise progress lines while
Claude works. Older `dds` builds delegated to Claude's default text output,
which could look idle until the agent finished.

Saved models apply only to the harness they were saved with. An explicit
`--model` takes precedence over a saved model. If you switch harnesses without
a model, Pi uses `openai-codex/gpt-6.2-sol` and the other harnesses use their
CLI defaults. Switching harnesses during `dds init` starts the optional model
prompt empty. Keeping the harness pre-fills its saved model.

For Codex and Pi, `dds wrap --run` checks the selected OpenAI model before
launch. The approved IDs are `gpt-6.2-sol` and `gpt-6.2-astra`. The check
applies to recognized bare OpenAI IDs and `openai/` or `openai-codex/`
references. To replace an older saved model, run `dds init` or pass
`--model gpt-6.2-sol` for Codex or `--model openai-codex/gpt-6.2-sol` for Pi.
Other provider references and the native Codex default follow the harness's
own model configuration.
`dds init` applies the same check. It re-prompts for an unapproved OpenAI
model and does not keep an unapproved saved model when you press Enter.
The source-checkout `scripts/wrap --run --agent pi` also launches
`openai-codex/gpt-6.2-sol`.

`dds wrap` and `dds doctor` run a timed `node --version` check on the
executable found in an absolute PATH directory. A `node` resolved from the
current directory or a relative PATH entry is reported and never run.
Node.js 22.12 or newer is required. Missing Node,
older versions and probe failures block `dds wrap --run` before agent launch.
Plain `dds wrap` reports these as warnings.

Preflight requires a successful `git status`. A failed inspection blocks wrapping
even with `--force`; that flag permits known uncommitted changes and an existing
`electron/` directory. Command failure diagnostics are truncated to 800 UTF-8 bytes.

Claude completion requires exactly one terminal `result` with `is_error: false`
(and `subtype: success` if present), plus exit code zero. Missing, malformed,
duplicate or error results fail even when the process exits zero; nonzero child
exit codes are preserved. Stream records are limited to 1 MiB each, including
the newline, before UTF-8 decoding or JSON parsing. Oversized records fail and
trigger owned-process cleanup. Progress output is truncated to 4096 UTF-8 bytes
per event; records are processed without retaining a transcript.

Options:
- `--run` — invoke the agent after preflight passes
- `--agent NAME`, `--harness NAME` — agent harness to use: `claude`, `pi`, `codex`; overrides saved config or auto-detect
- `--model NAME` — model to pass to the selected agent; overrides the saved default model
- `--force` — permit known dirty worktrees and existing electron/ directories; failed Git inspection still blocks
- `--emit-prompt` — print the resolved wrapping prompt to stdout

Prompt emission is offline and read-only, even when combined with `--run`.
It bypasses tool checks, project discovery, saved config and harness setup.
The UTF-8 template replaces only `../desktop-django-starter/` path prefixes
with the installed asset root; spaces, Unicode and shell punctuation remain
literal. Similar ordinary text and bare repo-root names without a trailing
slash are preserved. Missing, unreadable or invalid
UTF-8 templates produce a CLI error and exit 1.

Discovery accepts a root or nested `manage.py`, excluding hidden directories,
`venv`, `env`, `node_modules` and `__pycache__`, and does not follow directory
symlinks. Multiple paths are listed in sorted order for the harness to inspect;
no discovery blocks every harness, including with `--force`. Missing tools
remain warnings in preflight-only mode and errors with `--run`.

### `dds doctor`

Check that prerequisites are installed and that wrapper config and available
harnesses are sufficient for `wrap --run`. Doctor checks every file listed in
the installed asset manifest. An incomplete bundle reports up to eight missing
paths and the total count, with instructions to reinstall.
Doctor is read-only: it never invokes a harness, saves preferences or stages assets.
Missing required assets or tools and failed Node version checks exit with
status 1. Missing optional `uv`, invalid wrapper config, refused saved models
and harness setup advice remain advisory (status 0 when core checks pass).
Doctor shows the refused model and how to replace it with an approved selection.

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

Wheel and sdist builds reject an incomplete staged bundle before producing an
archive, using the same `src/dds/asset_inventory.txt` manifest as sync and doctor.
Directories do not satisfy required files; the diagnostic lists up to eight
missing paths and points to `just cli-sync-assets`. `just cli-test` provisions
pytest and Hatchling; synthetic build/install probes run offline and require
no agents, Node runtime or package downloads during the tests.

Asset staging records each canonical input's file identity and metadata before
copying to a unique sibling staging directory. It rechecks those values around
each copy, then compares every staged file's bytes with its source across the
whole inventory before publication. A detected edit stops the sync and
preserves the existing bundle. Retry after edits finish.
Syncs hold the persistent
`cli/src/dds/.assets-sync-lock` while capturing `.gitkeep` and replacing the old
bundle. Wheel and sdist builds hold that same lock while validating and copying
one generation to a private snapshot. Hatch discovers and reads the archive
payload from that snapshot, so a sync can publish during archive creation.
Leave the lock file in place. On Windows, retry the sync or build if the OS
times out acquiring the lock. If explicit unlock fails, the handle still closes.
A completed operation reports its success and logs the unlock failure. A failed
operation raises its original error with the unlock failure in the diagnostics.
A complete tree replaces the old bundle,
removing stale files while preserving an existing `.gitkeep` and its contents.
Copy failures leave the old bundle intact. A failed promotion attempts recovery
under the same lock. If recovery fails, sync raises the original promotion
error with the recovery error and paths under `cli/src/dds/.assets-sync-*/`.
Cleanup errors during a failed sync are also included in the traceback.
Before renaming either tree, sync flushes the staged files and records and
flushes the directory identities in the publication marker. On POSIX it also
flushes the staged directories, work directory and marker's parent directory.
A failed barrier stops publication before either tree moves. Windows flushes
files and reports that directory sync and power-loss guarantees for renames
are unavailable. After a process stops mid-publication, the next sync or build
restores the recorded predecessor if the bundle path is vacant, or keeps the
completed replacement if promotion already finished. On POSIX, sync flushes the
predecessor's move to the recovery directory before promotion and restores the
predecessor if that flush fails. Publication and
recovery flush the selected directory entry before removing the journal, then
flush the journal removal before discarding the work directory. A failed
namespace flush keeps the recorded generations and journal available for retry.
If the flush after journal removal fails, the work directory remains available
in case the journal reappears after restart. Recovery reads only from the
opened regular marker file and verifies its identity and length before applying
the record. A changed marker, a reparse point, or ambiguous directory identities
stop recovery. Inspect the retained paths with syncs and builds stopped.
Git and the build configuration exclude the lock, marker and work directories.
If old-tree cleanup fails after publication, sync reports the cleanup failure
and keeps the complete new bundle live.

## Wrapper config format and saves

The user config is UTF-8 TOML, with a `[wrap]` table containing `harness`
(`"claude"`, `"pi"`, or `"codex"`) and an optional string `model`. An empty
model means no default model. TOML basic, literal and multiline strings and
comments are supported; literal strings preserve backslashes exactly:

```toml
[wrap]
harness = "pi"
model = 'provider\test'
```

Invalid TOML (including duplicate keys or tables) and incorrect field types
produce a configuration error. Unrelated valid tables and keys are ignored.
Saves use unique temporary files in the config directory, close them before
atomic replacement, and remove them on failure. Concurrent saves publish one
complete configuration each; the last atomic replacement wins. On Windows,
where a file cannot be replaced while another save or reader has it open and
cannot be opened while it is being replaced, the replacement and the read are
each retried briefly before a configuration error is reported.
