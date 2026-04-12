# Backlog

This backlog tracks explicit follow-on work for the desktop shell lanes. It is not a replacement for the specification or decision log; it turns deferred work into implementation-sized entries that can be copied into implementation handoff prompts for agents.

When an entry is implemented, move it to [`done.md`](done.md) in the same change as the implementation and docs updates. Keep the item id stable so old handoff prompts and review notes remain traceable.

## BL-008: Electron Connected Updater Release Validation

Status: blocked on Windows live release validation

### Context

Electron is still the baseline release lane in this repo. The connected updater path is implemented through `electron-updater`, GitHub-hosted artifacts, updater metadata, and `Help > Check for Updates...`. One live proof point is now recorded: on April 12, 2026, a signed/notarized macOS packaged app updated from installed `0.1.2` to published `v0.1.4`, proving detection, download, restart/install, and `app.sqlite3` persistence. The remaining missing proof point is a real Windows NSIS update dry run.

Those live validations matter more than additional experimental-shell release work because the repo already presents Electron as the most complete path. Until the release lane is exercised end to end, the release-readiness language cannot honestly get stronger.

### Goal

Validate the implemented Electron connected updater path end to end on real packaged artifacts, then tighten or preserve the repo's release claims based on that evidence.

### Current Blocker

- The updater path is implemented, and the repo now records a real signed/notarized macOS packaged update dry run from installed `0.1.2` to published `v0.1.4`.
- Artifact-only packaging runs, unsigned local packaging, and draft GitHub Releases are not enough to close this item.
- Keep this entry in backlog until a real Windows NSIS packaged update run also proves detection, download, restart/install, and `app.sqlite3` persistence.

### Suggested Implementation Shape

- Run one real Windows NSIS updater validation using published Electron release metadata.
- Preserve the documented macOS evidence and only strengthen repo wording where the Windows proof now supports it.
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

## BL-009: First-Run Pony Demo Seeding

Status: ready

### Context

The starter now carries a clear Flying Stable presentation layer, but a fresh app launch still opens to an empty "My Ponies" list. That leaves the branded CRUD demo visually flat until the user creates content manually. At the same time, this repo treats the packaged SQLite database as real per-user local state, so the app must not surprise users by repopulating data after they have already started using or clearing their stable.

All three desktop shells run Django migrations during startup before showing the app. That makes migration-time or startup-hook seeding too blunt for this use case, because a seed path tied to `migrate`, `post_migrate`, or `AppConfig.ready()` could affect existing installs repeatedly instead of only improving the first-run experience.

### Goal

Show a small set of example ponies automatically for a brand-new per-user database, without mutating existing user data and without re-seeding after the user clears the list intentionally.

### Suggested Implementation Shape

- Add an explicit Django management command such as `seed_demo_content` that inserts starter `example_app.Item` rows only when the database is in a brand-new starter state.
- Keep the seed content in a simple local data definition or fixture-like file so the sample pony roster is easy to edit and test without embedding a long literal list inside shell bootstrap code.
- Run the command from the desktop startup flow only after migrations succeed, and only when the current per-user database is genuinely new for this app.
- Make the command idempotent and conservative: if user-created pony rows already exist, it should do nothing.
- Do not treat "table is empty again later" as a reason to re-seed. A user who cleared the stable should keep control of that empty state.
- Document the behavior clearly as first-run demo content, not as a general background sync or sample-data refresh system.

### Likely File Areas

- `src/example_app/`
- `shells/electron/main.js`
- `shells/tauri/src-tauri/src/lib.rs`
- `shells/positron/src/desktop_django_starter_positron/app.py`
- `README.md`
- `docs/specification.md`
- `llms.txt`
- `tests/`

### Non-Goals

- Do not add automatic re-seeding whenever the pony list becomes empty.
- Do not store special seed-tracking flags on every pony row unless implementation pressure proves it necessary.
- Do not couple demo-content creation to migrations, `post_migrate`, or `AppConfig.ready()`.
- Do not expand this into a general fixture-loading framework for arbitrary apps.

### Validation

- Add tests for the seed command covering brand-new database seeding and no-op behavior when pony rows already exist.
- Verify each shell startup path can invoke the seed command after `migrate` without breaking normal launch.
- Run `just check` for final handoff when feasible.

### Done Criteria

- A fresh per-user app database shows starter ponies on first open.
- Existing user databases are left unchanged by the new seed path.
- Clearing the stable does not cause ponies to reappear on a later launch.
- The seed content source and first-run behavior are documented.
- The implemented entry is moved from this file to [`done.md`](done.md) with a short implementation summary.
