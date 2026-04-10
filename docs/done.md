# Done

This file records backlog entries after they are implemented. Move the full entry from [`backlog.md`](backlog.md) into this file in the same change that implements the work, then add a short implementation summary and validation notes.

Keep item ids stable. Do not renumber completed work.

## Completed Entries

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
