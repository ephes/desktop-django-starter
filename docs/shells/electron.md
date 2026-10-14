# Electron Shell

Status: implemented as the baseline release-oriented shell in this repo.

The current production-grade shell path in this repository is [`shells/electron/`](../../shells/electron/).

Current responsibilities:

- supervise Django and the task worker as child processes
- generate a fresh per-session shell-to-Django auth token and pass it to Django as `DESKTOP_DJANGO_AUTH_TOKEN`
- inject `X-Desktop-Django-Token` only for the exact local Django origin, including the Electron health poll, without exposing the token through preload
- keep using hidden exact-origin header injection rather than the bootstrap cookie flow used by the experimental Tauri and Positron shells
- deny child-window creation from the renderer by default and block top-level navigation away from the local Django origin, opening safe external URLs through the OS shell instead
- apply the same origin rule to server-side redirects (`will-redirect`), so an off-origin redirect from Django, such as an OAuth or social-login hand-off, opens in the system browser instead of inside the app window; subframes may still navigate because they never receive the preload bridge
- answer the `window.desktop` preload bridge only for pages on the exact local Django origin, refusing IPC calls from any other sender frame
- consume the shared staged backend from `.stage/backend/`
- package desktop artifacts with `electron-builder`
- generate Electron updater metadata and use `electron-updater` for connected update checks
- expose update checks through `Help > Check for Updates...` without adding a Django update API or broadening the preload bridge
- generate shell-local icon outputs in `shells/electron/assets/icons/` from the shared brand source under `assets/brand/`

Use this shell when you need the most complete desktop path in the repo today.

Installing the shell's npm dependencies (`just electron-install`) needs Node.js 22.12 or newer, the minimum declared by Electron 44 and electron-builder 26.

The shell tracks a supported Electron major (currently Electron 44). Since Electron 42 the `electron` npm package no longer downloads its binary in a `postinstall` script; the first `npm start`, `just packaged-smoke` or other launch through `scripts/launch-electron.cjs` downloads it on demand (or run `npx install-electron --no` in `shells/electron/` ahead of time, for example before going offline). Electron 44 requires macOS 13 (Ventura) or newer and publishes 64-bit builds only, so Windows x86 (ia32) and Linux 32-bit ARM (armv7l) packages are no longer possible.

`shells/electron/package.json` overrides `global-agent` to 4.x. electron-builder 26 still pulls `@electron/get` 3, whose optional proxy helper `global-agent` 3 depends on `roarr` and a `sprintf-js` version with a denial-of-service advisory; `global-agent` 4 keeps the same `bootstrap()` API without that chain. Drop the override once a stable electron-builder release depends on `@electron/get` 5 or newer.

Current update scope:

- default feed: GitHub Releases for this repo, configurable through the Electron builder config environment variables documented in the release guide
- workflow support: `.github/workflows/desktop-packages.yml` uploads `latest*.yml` metadata and can publish to a draft GitHub Release when manually triggered with `publish_release=true`
- local behavior: development runs show a harmless "updates unavailable" dialog instead of attempting a feed check
- release-readiness boundary: a signed/notarized macOS update from installed `0.1.2` to published `v0.1.4` now proves detection, download, restart/install, and `app.sqlite3` persistence, but a Windows NSIS update still needs live validation before claiming production updater readiness
