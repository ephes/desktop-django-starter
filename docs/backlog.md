# Backlog

This backlog tracks explicit follow-on work for the desktop shell lanes. It is not a replacement for the specification or decision log; it turns deferred work into implementation-sized entries that can be copied into implementation handoff prompts for agents.

When an entry is implemented, move it to [`done.md`](done.md) in the same change as the implementation and docs updates. Keep the item id stable so old handoff prompts and review notes remain traceable.

## BL-001: Electron Connected Auto-Update

Status: proposed

### Context

Electron is the baseline release lane in this repo. It already uses `electron-builder`, NSIS on Windows, DMG on macOS, AppImage on Linux, optional signing inputs, notarization scaffolding, GitHub Actions artifact builds, and checksum generation. It does not publish GitHub Releases or any update feed yet.

The current v1 update story remains manual installer replacement for both connected and air-gapped environments. This backlog item adds a connected update path without removing that manual path.

### Goal

Add a minimal, production-shaped connected auto-update path for the Electron shell using the existing `electron-builder` release lane.

### Suggested Implementation Shape

- Prefer `electron-updater` over Electron's built-in `autoUpdater`, because the repo already uses `electron-builder` with NSIS/AppImage targets.
- Add a publish provider to the Electron builder config, most likely GitHub Releases first unless the implementation chooses a generic HTTPS feed for an internal deployment scenario.
- Change release packaging so updater metadata is generated and uploaded with the installer artifacts, including the relevant `latest*.yml` files.
- Add Electron main-process update orchestration in `shells/electron/main.js` or a small shell-local module under `shells/electron/scripts/`.
- Keep renderer exposure narrow: update status should not broaden the preload bridge beyond a minimal, explicit user action if one is required.
- Add user-facing behavior for the starter, such as a menu action or dialog for "check for updates", "downloaded", and "restart to update".
- Ensure the update check is disabled or harmless during local development, tests, and unsigned local package builds.
- Preserve the existing manual connected and air-gapped update documentation as the fallback path.

### Likely File Areas

- `shells/electron/package.json`
- `shells/electron/package-lock.json`
- `shells/electron/main.js`
- `shells/electron/scripts/electron-builder-config.cjs`
- `.github/workflows/desktop-packages.yml`
- `README.md`
- `llms.txt`
- `docs/llms.txt`
- `docs/index.md`
- `docs/release.md`
- `docs/shells/electron.md`
- `docs/backlog.md`
- `docs/done.md`
- `tests/test_docs.py`
- Electron script tests under `shells/electron/scripts/` if update logic is factored into testable helpers

### Non-Goals

- Do not remove the offline/manual update path.
- Do not make signing credentials mandatory for local teaching builds.
- Do not add a background service outside Electron.
- Do not implement a product-sized release-channel matrix unless a later task asks for beta/stable/nightly channels.
- Do not broaden Django's local HTTP API for update checks; update orchestration belongs to the shell/release layer.

### Validation

- Run `npm --prefix shells/electron test`.
- Run the narrow packaging path needed to confirm updater metadata is produced, or document why it cannot be run locally.
- Run `just docs-build` if docs changed.
- Prefer `just check` for final handoff when feasible.
- For a real release dry run, validate at least one signed/notarized macOS build and one Windows NSIS build from GitHub Actions before claiming production readiness.

### Done Criteria

- Electron packages have a connected update feed or release metadata publication path.
- The app can check for updates without breaking development mode or local unsigned packaging.
- A downloaded update can be installed through the expected Electron update flow on the supported target platforms.
- Manual connected and air-gapped update docs remain accurate.
- The implemented entry is moved from this file to [`done.md`](done.md) with a short implementation summary.

## BL-002: Tauri Connected Auto-Update

Status: proposed

### Context

Tauri is experimental in this repo. It reuses the shared staged backend and now has a GitHub-hosted artifact-only packaging workflow through `tauri-action`, but it does not publish GitHub Releases, wire signing/notarization parity, or generate updater artifacts.

Tauri's updater model differs from Electron's. The likely path is the official Tauri updater plugin, configured with a public key, updater artifacts, signatures, and an HTTPS update endpoint or static release JSON.

### Goal

Add a connected auto-update experiment for the Tauri shell that matches Tauri 2's updater model while preserving the repo's statement that Tauri is not yet release parity with Electron.

### Suggested Implementation Shape

- Add `tauri-plugin-updater` to the Tauri shell dependencies.
- Configure updater support in `shells/tauri/src-tauri/tauri.conf.json`, including `bundle.createUpdaterArtifacts`, updater public key, and endpoint configuration.
- Decide whether the first feed target is a GitHub Release-hosted static JSON file or a generic HTTPS endpoint.
- Update `.github/workflows/tauri-packages.yml` so the updater bundles and `.sig` files are uploaded with the normal Tauri artifacts.
- Add Tauri-side update check behavior in Rust under `shells/tauri/src-tauri/src/`, or JavaScript under `shells/tauri/src/`, depending on which keeps the current shell smaller and easier to test.
- Keep the implementation honest about Windows: the existing NSIS path still needs live Windows install/run validation, and WebView2 installer behavior remains a separate release concern.
- Keep Tauri's bootstrap-cookie Django authentication flow unchanged; updater metadata and update downloads should not depend on Django's localhost app.

### Likely File Areas

- `shells/tauri/package.json`
- `shells/tauri/package-lock.json`
- `shells/tauri/src-tauri/Cargo.toml`
- `shells/tauri/src-tauri/Cargo.lock`
- `shells/tauri/src-tauri/tauri.conf.json`
- `shells/tauri/src-tauri/src/lib.rs`
- `.github/workflows/tauri-packages.yml`
- `README.md`
- `llms.txt`
- `docs/llms.txt`
- `docs/release.md`
- `docs/shells/tauri.md`
- `docs/backlog.md`
- `docs/done.md`
- `tests/test_docs.py`

### Non-Goals

- Do not claim Tauri release parity with Electron until signing/notarization, release publication, and Windows install/run validation are in place.
- Do not remove the manual update path.
- Do not switch the Windows WebView2 strategy as part of the updater work unless that is explicitly included in the task.
- Do not add a custom updater protocol when the official Tauri updater plugin is sufficient.

### Validation

- Run `just tauri-test`.
- Run `just tauri-build` or the narrow Tauri packaging command needed to confirm updater artifacts are produced; if host limitations prevent this, document the gap.
- Run `just docs-build` if docs changed.
- Prefer `just check` for final handoff when feasible.
- For release readiness, validate a hosted updater artifact set from `.github/workflows/tauri-packages.yml` and perform a real Windows install/run test before strengthening the release claim.

### Done Criteria

- Tauri builds produce updater artifacts and signatures.
- The Tauri shell can check for updates through the configured endpoint in a connected environment.
- Docs distinguish clearly between the Tauri updater experiment and full release parity.
- Manual connected and air-gapped update docs remain accurate.
- The implemented entry is moved from this file to [`done.md`](done.md) with a short implementation summary.

## BL-003: Positron Update Strategy and Auto-Update Path

Status: proposed

### Context

Positron is a local-only experiment in this repo. It uses Briefcase/Toga, runs Django plus the optional task worker in-process, and currently supports local macOS build and DMG packaging with ad-hoc signing. It has no GitHub Actions packaging lane, checksum-artifact lane, release publication flow, Windows packaged-build proof, or release-parity claim.

Briefcase's development update workflow is not the same thing as an end-user auto-updater. For this repo, Positron should first gain a credible release lane or an explicit decision to stay manual-only before implementing a custom auto-updater.

### Goal

Define and, if still justified, implement a Positron connected update path that fits the Briefcase/Toga packaging model without pretending Positron already has Electron/Tauri release parity in this repo.

### Suggested Implementation Shape

- Start with a design note in `docs/shells/positron.md` or `docs/release.md` that chooses one of these paths:
  - manual-only signed installer replacement for Positron,
  - platform-native distribution such as signed macOS DMG/pkg, Windows MSIX/MSI/winget-style distribution, or Linux package-manager artifacts,
  - a custom in-app updater built around signed release manifests and platform-specific installer handoff.
- Add a dedicated Positron packaging workflow only if the update path depends on hosted artifacts.
- Add checksum generation and artifact download helpers for Positron before any custom updater consumes those artifacts.
- If a custom updater is chosen, keep it outside Django's localhost web app and use signed manifests plus platform-native installer/app replacement behavior.
- Preserve the current statement that Positron is experimental until macOS signing, Windows packaging proof, and hosted artifact generation are implemented.

### Likely File Areas

- `shells/positron/pyproject.toml`
- `shells/positron/src/desktop_django_starter_positron/`
- `.github/workflows/` if a Positron packaging workflow is added
- `justfile` if helper commands are added
- `README.md`
- `llms.txt`
- `docs/llms.txt`
- `docs/release.md`
- `docs/shells/positron.md`
- `docs/backlog.md`
- `docs/done.md`
- `tests/test_docs.py`

### Non-Goals

- Do not describe Briefcase's local development `update` command as an end-user auto-updater.
- Do not claim Windows packaged parity without a real Windows package build and install/run validation.
- Do not build a custom updater before deciding whether Positron should remain manual-only in this starter.
- Do not make the Django app responsible for replacing the desktop application.

### Validation

- Run `just positron-check`.
- Run `just positron-smoke` for local shell behavior when the implementation touches runtime code.
- Run `just positron-package-dmg` if macOS packaging behavior changes and local prerequisites are available.
- Run `just docs-build` if docs changed.
- Prefer `just check` for final handoff when feasible.

### Done Criteria

- Positron has an explicit update strategy documented, even if the chosen strategy is manual-only for now.
- If connected auto-update is implemented, it uses signed manifests or platform-native distribution mechanisms and has hosted artifact support.
- The release docs still clearly distinguish Positron from Electron's baseline release lane.
- The implemented entry is moved from this file to [`done.md`](done.md) with a short implementation summary.
