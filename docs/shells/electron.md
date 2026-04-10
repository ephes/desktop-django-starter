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
- generate shell-local icon outputs in `shells/electron/assets/icons/` from the shared brand source under `assets/brand/`

Use this shell when you need the most complete desktop path in the repo today.
