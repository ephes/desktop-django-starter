# Electron Shell

Status: implemented as the baseline release-oriented shell in this repo.

The current production-grade shell path in this repository is [`shells/electron/`](../../shells/electron/).

Current responsibilities:

- supervise Django and the task worker as child processes
- generate a fresh per-session shell-to-Django auth token and pass it to Django as `DESKTOP_DJANGO_AUTH_TOKEN`
- inject `X-Desktop-Django-Token` only for the exact local Django origin, including the Electron health poll, without exposing the token through preload
- keep using hidden exact-origin header injection rather than the bootstrap cookie flow used by the experimental Tauri and Positron shells
- deny child-window creation for every popup; dispatch safe external popup targets only with exact Django-referrer evidence from a live trusted app window
- block top-level navigation away from the local Django origin, opening safe external URLs through the OS shell instead
- apply the same origin rule to server-side redirects (`will-redirect`), so an off-origin redirect from Django, such as an OAuth or social-login hand-off, opens in the system browser instead of inside the app window; subframes may still navigate because they never receive the preload bridge
- answer the `window.desktop` preload bridge only for pages on the exact local Django origin, refusing IPC calls from any other sender frame
- start every backend process through `desktop_process_guard.py` with an open stdin pipe, so `runserver`, `db_worker` and their owned descendants terminate when Electron crashes or is killed; POSIX guards lead dedicated groups and retire them on pipe loss (SIGTERM/SIGINT only until the Django command installs its own handlers, as `db_worker` does); Electron signals the group on stop and SIGKILLs the rest of it as soon as a leader exits; on Windows the guard also holds a kill-on-close Job Object for the backend's process tree (`scripts/desktop_process_guard.py`)
- record a session in `desktop-shell-session.json` and, after a run that did not shut down cleanly, stop leftover backend processes of this install before `migrate` (`scripts/orphan-processes.cjs`); a process only counts when its executable is Python or `uv` and its arguments name the guard and this install's random app key
- ask before closing the window or quitting while `/desktop/activity/` reports running or queued background tasks (`scripts/quit-guard.cjs`); the check is skipped for update installs and the smoke test, and a failed check never blocks quitting
- pass `DESKTOP_DJANGO_APP_VERSION` (`app.getVersion()`) so packaged settings keep this version's database, media and cache in `state/<version>/`
- consume the shared staged backend from `.stage/backend/`
- package desktop artifacts with `electron-builder`
- generate Electron updater metadata and use `electron-updater` for connected update checks
- expose update checks through `Help > Check for Updates...` without adding a Django update API or broadening the preload bridge
- generate shell-local icon outputs in `shells/electron/assets/icons/` from the shared brand source under `assets/brand/`

Use this shell when you need the most complete desktop path in the repo today.

Installing the shell's npm dependencies (`just electron-install`) needs Node.js 22.12 or newer, the minimum declared by Electron 45.

The shell tracks a supported Electron major (currently Electron 45). Since Electron 42 the `electron` npm package no longer downloads its binary in a `postinstall` script; the first `npm start`, `just packaged-smoke` or other launch through `scripts/launch-electron.cjs` downloads it on demand (or run `npx install-electron --no` in `shells/electron/` ahead of time, for example before going offline). Electron 45 requires macOS 13 (Ventura) or newer and publishes 64-bit builds only, so Windows x86 (ia32) and Linux 32-bit ARM (armv7l) packages are no longer possible.

`shells/electron/package.json` overrides `global-agent` to 4.x. electron-builder 26 still pulls `@electron/get` 3, whose optional proxy helper `global-agent` 3 depends on `roarr` and a `sprintf-js` version with a denial-of-service advisory; `global-agent` 4 keeps the same `bootstrap()` API without that chain. Drop the override once a stable electron-builder release depends on `@electron/get` 5 or newer.

Current update scope:

- default feed: GitHub Releases for this repo, configurable through the Electron builder config environment variables documented in the release guide
- workflow support: `.github/workflows/desktop-packages.yml` uploads `latest*.yml` metadata and can publish to a draft GitHub Release when manually triggered with `publish_release=true`
- local behavior: development runs show a harmless "updates unavailable" dialog instead of attempting a feed check
- release-readiness boundary: a signed/notarized macOS update from installed `0.1.2` to published `v0.1.4` now proves detection, download, restart/install, and `app.sqlite3` persistence, but a Windows NSIS update still needs live validation before claiming production updater readiness

## Session recovery failures

Electron preserves an unsafe or unreadable session marker and stops before any
backend command. Recovery tools have finite command deadlines. If inventory or
termination is unknown, close the app, repair the process tool or marker access,
then explicitly relaunch. Do not remove a dirty marker to bypass orphan recovery.
The app marks a session clean only after confirmed child exit; see the
{ref}`architecture recovery contract <electron-orphan-command-and-signal-limits>`
for descriptor limits, process identity checks and platform limitations.

An update handoff failure (including an installer error event) hides the unusable
window, attempts to stop both children, explains that a restart is required and
exits. The next explicit launch uses the retained dirty marker to recover.

(frame-permissions)=
## Frame permissions

The starter uses no renderer capability grants. Before loading Django, the shell
installs `setPermissionRequestHandler` and `setPermissionCheckHandler`, both with
an empty capability allowlist. This denies camera/microphone (`media`), location,
notifications, clipboard reads and unknown capabilities without OS prompts.
Ordinary remote embeds still load; the containing window's trusted URL does not
authorize an embedded frame. Existing auth-header injection and IPC checks remain
separate boundaries.

When adapting an app that actually needs a capability, review that feature and
pass only its permission name at the main-process call site, for example:

```javascript
registerSessionPermissionPolicy(win.webContents, url, ["geolocation"]);
```

This opt-in admits only the live owned main frame on the exact Django origin,
including its random port. Both the requesting URL and (for checks) requesting
origin must match. Missing details, destroyed/foreign WebContents, subframes,
service-worker/non-document checks and capabilities absent from the list deny.
Do not use a wildcard, replace either handler with `null`, or grant permission
based only on `webContents.getURL()`. Media features also need a deliberate
camera-versus-microphone policy before enabling the shared `media` capability.

Run `npm --prefix shells/electron run test:frames` on a host that can launch
Electron. This synthetic two-origin iframe fixture checks real Chromium camera,
microphone, geolocation and notification refusals, normal embed loading and
exact-origin auth-header isolation. It uses fake media devices and requests no
OS grants. `npm --prefix shells/electron test` separately covers installed
handler callbacks and main-window installation before `loadURL`.

## Popup requester admission

The popup callback retains the complete public Electron details. Safe target
schemes alone do not authorize `shell.openExternal`: the referrer's URL must
match the exact local Django origin, and the owning window must still be alive
on that origin. Foreign embeds, missing/malformed referrers and suppressed
(`noreferrer`/`no-referrer`) requests get no native side effect. All popup windows
return `action: "deny"`, including same-origin targets and refused schemes.
Referrer evidence does not prove a user gesture, and `disposition` does not grant
one. No new preload bridge is exposed.

Electron reports the referrer after the page's referrer policy is applied.
Django's default `SECURE_REFERRER_POLICY = "same-origin"` therefore strips it
from every cross-origin popup, so the starter's base settings set
`SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"`: cross-origin requests
see only the local origin (never path or query), and the token bootstrap path
still sends `no-referrer`. A wrapped app that keeps `same-origin`, `no-referrer`
or another policy without a cross-origin origin gets its target-blank outbound
links refused (fail closed, no OS browser); set the same policy in its desktop
settings or use same-window links.

For deliberate trusted-app outbound links, keep the normal same-window link path
or a target-blank link under that referrer policy. A target-blank link that
suppresses its referrer (`rel="noreferrer"`) is refused; use a same-window link
when referrer suppression is required. Existing main-frame navigation/redirect scheme checks
and sender-validated app-data IPC continue to apply.

`npm --prefix shells/electron run test:frames` also drives actual remote iframe
popups (ordinary and noreferrer) through the installed handler and verifies zero
native dispatch, no child windows, and exactly one dispatch for a trusted app
link served with the starter's referrer policy; a trusted page served with
`Referrer-Policy: same-origin` reports an empty referrer and dispatches nothing. The fixture records native dispatch in memory instead of launching the OS
browser. Node tests exercise foreign ports, missing evidence, unsafe schemes,
stale/destroyed windows and the callback registered by `main.js`.
See Electron's [public popup callback](https://www.electronjs.org/docs/latest/api/web-contents#contentssetwindowopenhandlerhandler)
for the available evidence; it does not expose an initiator frame.
