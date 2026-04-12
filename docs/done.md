# Done

This file records backlog entries after they are implemented. Move the full entry from [`backlog.md`](backlog.md) into this file in the same change that implements the work, then add a short implementation summary and validation notes.

Keep item ids stable. Do not renumber completed work.

## Completed Entries

## BL-007: Experimental Shell Lifecycle and Runtime Clarity

Status: completed

### Context

Electron remains the most complete shell in the repo, but the experimental Tauri and Positron ports had started to drift in a few lifecycle details that were no longer clearly intentional: Tauri used a more abrupt Unix shutdown path, and Positron left its single-instance and packaged-style runtime choices mostly implicit.

### Goal

Tighten the small lifecycle gaps that are easy to fix, and document the remaining shell differences so the repo's multi-shell story stays deliberate instead of accidental.

### Implemented Summary

- Updated the Tauri shell to send `SIGTERM` first on Unix and only force-kill Django or the task worker after a 2-second grace period, bringing its shutdown behavior closer to Electron.
- Added a lock-file based single-instance guard to Positron so a second launch no longer starts a second in-process Django runtime against the same app-data directory.
- Made Positron's always-packaged runtime mode explicit in code by naming the packaged settings choice and exporting `DESKTOP_DJANGO_RUNTIME_MODE=packaged` in the shell environment.
- Narrowed Positron startup static collection by keeping the refresh step but dropping `collectstatic --clear`, so repeated local launches stop rebuilding the cache-backed static tree from scratch.
- Updated the Tauri, Positron, README, and architecture docs to describe the narrowed differences and the remaining intentional divergence.
- Added shell tests and docs assertions that lock in the new Tauri shutdown language, Positron runtime contract, and completed backlog bookkeeping.

### Validation Notes

- Ran `just tauri-test`.
- Ran `just positron-check`.
- Ran `just positron-smoke`.
- Ran `uv run pytest tests/test_tauri_shell.py tests/test_positron_shell.py tests/test_docs.py`.
- Ran `just docs-build`.
- Ran `just check`.

## BL-006: Electron Navigation and Window Hardening

Status: completed

### Context

The Electron shell already had a narrow preload bridge, exact-origin auth-header injection, and a documented localhost threat model. One remaining hardening gap was that the main window did not yet apply explicit navigation or popup guards.

### Goal

Harden the Electron renderer window against unexpected navigation and window-opening behavior while preserving the current server-rendered Django flow and narrow native surface area.

### Implemented Summary

- Added a shell-local `window-guards.cjs` helper that decides whether a navigation should remain in-app, be denied, or be handed off to the OS shell.
- Added a `setWindowOpenHandler` policy in `main.js` that denies child-window creation by default.
- Added a `will-navigate` guard in `main.js` that allows same-origin localhost navigation, blocks other top-level navigation, and opens safe external URLs through the OS shell instead of inside Electron.
- Kept the preload bridge unchanged and left the Django renderer model on localhost.
- Added focused Node-side tests for the new guard helper logic.
- Updated the Electron shell docs and docs tests to reflect the hardened window behavior and completed backlog bookkeeping.

### Validation Notes

- Ran `npm --prefix shells/electron test`.
- Ran `uv run pytest tests/test_docs.py`.
- Ran `just docs-build`.
- Ran `just check`.

## BL-005: Documentation Consistency and Discoverability Cleanup

Status: completed

### Context

The docs were already strong, but a few verified inconsistencies had started to undercut trust: the design guide still described the splash screen as deferred, the published `docs/llms.txt` had drifted from the root agent entry point, and supporting docs were being built without being intentionally linked from the main docs navigation.

### Goal

Bring the documentation back into alignment with the current implementation and make supporting docs easier to discover without over-claiming maturity or completeness.

### Implemented Summary

- Updated `docs/design-guide.md` so the splash-screen section reflects the current Electron startup flow instead of describing it as deferred.
- Added the design guide and the tasks-demo frontend design spec to the main docs toctree so they are published intentionally instead of remaining orphaned.
- Expanded `docs/llms.txt` so its constraints, wrapping guidance, and optional references stay aligned with the richer root `llms.txt` while preserving published-doc links.
- Refreshed `docs/architecture.md` from an illustrative draft repo tree to a current repo-shape section that now includes the CLI package, wrapping skill, `tasks_demo`, and Electron script area.
- Updated architecture wording so the startup contract describes the current implementation rather than an eventual future slice.
- Added docs tests that lock in the new navigation, published agent-entry content, stale-claim fix, and backlog bookkeeping.

### Validation Notes

- Ran `uv run pytest tests/test_docs.py`.
- Ran `just docs-build`.
- Ran `just check`.

## BL-004: CI Validation Coverage for Electron and CLI

Status: completed

### Context

Cross-platform CI originally covered Python lint, pytest, and docs build, but it did not run the Electron Node-side tests or the packaged CLI test suite. That left two important validation lanes unproved on pull requests even though both existed locally.

### Goal

Extend CI so the repo's default validation covers the Electron Node-side tests and the `cli/` test suite in a way that stays fast, cross-platform, and easy to understand.

### Implemented Summary

- Added Node setup and npm caching to `.github/workflows/ci.yml`.
- Added `npm --prefix shells/electron ci` plus `npm --prefix shells/electron test` to pull-request CI.
- Added explicit CLI asset staging in CI with `uv run python cli/sync_assets.py` before the CLI test step.
- Added a dedicated CLI test step that runs under `cli/` so the wrapper package is validated in its own project context.
- Added `cli/pytest.ini` so the CLI tests stop inheriting the root Django pytest configuration and run without unrelated config warnings.
- Updated the root README development commands to mention the Electron Node-side tests and the CLI test suite.
- Added docs tests that assert the broader CI coverage and completed backlog bookkeeping.

### Validation Notes

- Ran `npm --prefix shells/electron test`.
- Ran `uv run python cli/sync_assets.py`.
- Ran `uv run --with pytest python -m pytest tests/` from `cli/`.
- Ran `uv run pytest tests/test_docs.py`.
- Ran `just docs-build`.

## BL-001: Electron Connected Auto-Update

Status: completed

### Context

Electron is the baseline release lane in this repo. It already uses `electron-builder`, NSIS on Windows, DMG on macOS, AppImage on Linux, optional signing inputs, notarization scaffolding, GitHub Actions artifact builds, and checksum generation. It did not publish GitHub Releases or any update feed yet.

The current v1 update story remains manual installer replacement for air-gapped environments. This backlog item adds a connected update path without removing that manual path.

### Goal

Add a minimal, production-shaped connected auto-update path for the Electron shell using the existing `electron-builder` release lane.

### Implemented Summary

- Added `electron-updater` as an Electron app dependency.
- Added a shell-local update controller in `shells/electron/scripts/updates.cjs`.
- Added a `Help > Check for Updates...` menu action that checks for updates in the Electron main process, prompts before downloading, and prompts before restart/install.
- Kept renderer exposure unchanged; no preload or Django HTTP API was added for update checks.
- Configured `electron-builder` with a GitHub Releases update feed by default, plus `DESKTOP_DJANGO_UPDATE_URL` and GitHub owner/repo env overrides for alternate feeds.
- Added the macOS ZIP target needed for Electron updater metadata while retaining the DMG as the primary user-facing macOS installer artifact.
- Updated `.github/workflows/desktop-packages.yml` to upload updater metadata such as `latest*.yml` and blockmap files with the installer artifacts, and to optionally publish artifacts to a draft GitHub Release when `publish_release=true`.
- Preserved the manual connected install and air-gapped installer replacement docs as the fallback path.

### Validation Notes

- Ran `npm --prefix shells/electron test`.
- Updater metadata generation and the optional GitHub Release publication path still need a real signed/notarized macOS release dry run and a Windows NSIS update validation run before claiming full production release readiness.
