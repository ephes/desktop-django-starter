# Backlog

This backlog tracks explicit follow-on work for the desktop shell lanes. It is not a replacement for the specification or decision log; it turns deferred work into implementation-sized entries that can be copied into implementation handoff prompts for agents.

When an entry is implemented, move it to [`done.md`](done.md) in the same change as the implementation and docs updates. Keep the item id stable so old handoff prompts and review notes remain traceable.

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
