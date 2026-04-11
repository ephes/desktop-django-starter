# Backlog

This backlog tracks explicit follow-on work for the desktop shell lanes. It is not a replacement for the specification or decision log; it turns deferred work into implementation-sized entries that can be copied into implementation handoff prompts for agents.

When an entry is implemented, move it to [`done.md`](done.md) in the same change as the implementation and docs updates. Keep the item id stable so old handoff prompts and review notes remain traceable.

## BL-006: Electron Navigation and Window Hardening

Status: proposed

### Context

The Electron shell already keeps a narrow preload bridge, uses exact-origin auth-header injection, and documents its localhost threat model honestly. One remaining hardening gap is that the main `BrowserWindow` setup does not currently appear to guard navigation or pop-up creation explicitly.

This is not a known exploit in the current teaching flow, but it is a straightforward best-practice improvement in the baseline shell.

### Goal

Harden the Electron renderer window against unexpected navigation and window-opening behavior while preserving the current server-rendered Django flow and narrow native surface area.

### Suggested Implementation Shape

- Add a `setWindowOpenHandler` policy that denies unexpected child windows by default.
- Add a `will-navigate` guard that blocks navigation away from the expected local app origin unless the repo intentionally allows a narrow exception.
- Keep any allowed external URLs opening through the OS shell rather than inside the Electron renderer.
- Add focused Node-side tests for the new guard logic if the implementation extracts helper functions.
- Update shell docs only if the behavior becomes user-visible or materially changes the stated security baseline.

### Likely File Areas

- `shells/electron/main.js`
- `shells/electron/scripts/*.test.cjs`
- `docs/shells/electron.md`
- `README.md`
- `llms.txt`
- `docs/llms.txt`
- `docs/backlog.md`
- `docs/done.md`

### Non-Goals

- Do not broaden the preload bridge.
- Do not replace the localhost Django renderer model with a bundled frontend.
- Do not present this slice as full Electron security hardening beyond the repo's documented baseline.

### Validation

- Run `npm --prefix shells/electron test`.
- Run `just packaged-smoke` if packaged Electron behavior changes.
- Run `just docs-build` if docs change.
- Prefer `just check` for final handoff when feasible.

### Done Criteria

- Unexpected pop-up creation is denied by default.
- Unexpected top-level navigation away from the local app origin is blocked or handled intentionally.
- Automated tests cover the added Electron guard behavior.
- The implemented entry is moved from this file to [`done.md`](done.md) with a short implementation summary.

## BL-007: Experimental Shell Lifecycle and Runtime Clarity

Status: proposed

### Context

Electron is the most complete shell in the repo, but the experimental shells now have a few lifecycle and runtime-contract differences that deserve either cleanup or an explicit written decision:

- Tauri currently uses a more abrupt Unix child-process shutdown path than Electron.
- Positron does not currently enforce single-instance behavior.
- Positron always prepares a packaged-style Django environment, even for local development, and currently runs `collectstatic` on startup.

Some of these differences may be intentional. The quality issue is that the boundary between deliberate divergence and accidental drift is no longer clear.

### Goal

Tighten lifecycle behavior in the experimental shells where the fix is small, and document the remaining intentional differences so the repo's multi-shell story stays coherent.

### Suggested Implementation Shape

- For Tauri, evaluate whether child-process shutdown can match Electron's Unix `SIGTERM` then timeout/kill pattern without making the Rust shell harder to maintain.
- For Positron, add single-instance enforcement if the shell is expected to share the same SQLite/app-data assumptions as the other shells.
- Decide whether Positron should keep using packaged settings in local runs; if yes, document that more explicitly, and if not, add a clear dev/packaged mode split.
- Revisit unconditional startup `collectstatic` in Positron and either narrow it, cache it, or document why the current cost is acceptable for this experiment.
- Update shell docs and tests so the chosen behavior is explicit rather than inferred from code.

### Likely File Areas

- `shells/tauri/src-tauri/src/lib.rs`
- `shells/positron/src/desktop_django_starter_positron/app.py`
- `shells/positron/src/desktop_django_starter_positron/runtime.py`
- `tests/test_tauri_shell.py`
- `tests/test_positron_shell.py`
- `docs/shells/tauri.md`
- `docs/shells/positron.md`
- `docs/architecture.md`
- `README.md`
- `llms.txt`
- `docs/llms.txt`
- `docs/backlog.md`
- `docs/done.md`

### Non-Goals

- Do not force the experimental shells into artificial parity when their runtime models are intentionally different.
- Do not add a large cross-shell abstraction layer just to remove a small amount of duplicated logic.
- Do not strengthen release claims for Tauri or Positron as part of this cleanup alone.

### Validation

- Run `just tauri-test` if Tauri runtime code changes.
- Run `just positron-check`.
- Run `just positron-smoke` if Positron runtime behavior changes.
- Run `just docs-build` if docs change.
- Prefer `just check` for final handoff when feasible.

### Done Criteria

- The most important lifecycle differences between Electron, Tauri, and Positron are either narrowed or documented intentionally.
- Positron's instance and runtime-mode behavior is explicit in code and docs.
- Tests cover the chosen shell behavior where practical.
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
