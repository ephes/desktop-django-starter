# Backlog

This backlog tracks explicit follow-on work for the desktop shell lanes. It is not a replacement for the specification or decision log; it turns deferred work into implementation-sized entries that can be copied into implementation handoff prompts for agents.

When an entry is implemented, move it to [`done.md`](done.md) in the same change as the implementation and docs updates. Keep the item id stable so old handoff prompts and review notes remain traceable.

## BL-008: Electron Connected Updater Release Validation

Status: blocked on live release validation

### Context

Electron is still the baseline release lane in this repo. The connected updater path is implemented through `electron-updater`, GitHub-hosted artifacts, updater metadata, and `Help > Check for Updates...`, but the docs still call out one important missing proof point: there has not yet been a real signed/notarized macOS update dry run or a real Windows NSIS update dry run.

Those live validations matter more than additional experimental-shell release work because the repo already presents Electron as the most complete path. Until the release lane is exercised end to end, the release-readiness language cannot honestly get stronger.

### Goal

Validate the implemented Electron connected updater path end to end on real packaged artifacts, then tighten or preserve the repo's release claims based on that evidence.

### Current Blocker

- The updater path is implemented, but this repo still does not record a real signed/notarized macOS update dry run or a real Windows NSIS update dry run from published updater metadata.
- Artifact-only packaging runs, unsigned local packaging, and draft GitHub Releases are not enough to close this item.
- Keep this entry in backlog until both platform runs prove detection, download, restart/install, and `app.sqlite3` persistence on real packaged installs.

### Suggested Implementation Shape

- Run one real signed/notarized macOS updater validation using published Electron release metadata.
- Run one real Windows NSIS updater validation using published Electron release metadata.
- Confirm the packaged app can detect, download, and restart into the newer version through `Help > Check for Updates...`.
- Confirm the per-user app-data directory survives the update, including `app.sqlite3`.
- Capture the operator workflow and results in `docs/release.md`, `README.md`, and `docs/done.md`.
- If either platform validation fails, document the failure honestly and narrow the claimed updater readiness instead of papering over it.

### Likely File Areas

- `.github/workflows/desktop-packages.yml`
- `shells/electron/`
- `README.md`
- `docs/release.md`
- `docs/architecture.md`
- `docs/backlog.md`
- `docs/done.md`
- `tests/test_docs.py`

### Non-Goals

- Do not broaden this into a new updater architecture project.
- Do not treat unsigned local packaging as proof of release readiness.
- Do not strengthen Windows or macOS release claims without a real install/update run on that platform.
- Do not change the Django localhost app to participate in update checks or installation.

### Validation

- Run `npm --prefix shells/electron test`.
- Run `uv run pytest tests/test_docs.py`.
- Run `just docs-build` if docs changed.
- Prefer `just check` for final handoff when feasible.
- For live release proof, run the packaged updater validation flow described in `docs/release.md` on macOS and Windows.

### Done Criteria

- A real signed/notarized macOS Electron update dry run has been performed and documented.
- A real Windows NSIS Electron update dry run has been performed and documented.
- The repo docs clearly state the resulting release-readiness claim, with no stale stronger or weaker wording left behind.
- The implemented entry is moved from this file to [`done.md`](done.md) with a short implementation summary.
