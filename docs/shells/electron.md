# Electron Shell

Status: implemented as the baseline release-oriented shell in this repo.

The current production-grade shell path in this repository is [`shells/electron/`](../../shells/electron/).

Current responsibilities:

- supervise Django and the task worker as child processes
- generate a fresh per-session shell-to-Django auth token and pass it to Django as `DESKTOP_DJANGO_AUTH_TOKEN`
- inject `X-Desktop-Django-Token` only for the exact local Django origin, including the Electron health poll, without exposing the token through preload
- keep using hidden exact-origin header injection rather than the bootstrap cookie flow used by the experimental Tauri and Positron shells
- consume the shared staged backend from `.stage/backend/`
- package desktop artifacts with `electron-builder`
- generate Electron updater metadata and use `electron-updater` for connected update checks
- expose update checks through `Help > Check for Updates...` without adding a Django update API or broadening the preload bridge
- generate shell-local icon outputs in `shells/electron/assets/icons/` from the shared brand source under `assets/brand/`

Use this shell when you need the most complete desktop path in the repo today.

Current update scope:

- default feed: GitHub Releases for this repo, configurable through the Electron builder config environment variables documented in the release guide
- workflow support: `.github/workflows/desktop-packages.yml` uploads `latest*.yml` metadata and can publish to a draft GitHub Release when manually triggered with `publish_release=true`
- local behavior: development runs show a harmless "updates unavailable" dialog instead of attempting a feed check
- release-readiness boundary: a signed/notarized macOS update and Windows NSIS update still need live validation before claiming production updater readiness
