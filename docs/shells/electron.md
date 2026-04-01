# Electron Shell

Status: implemented in this slice.

The current production-grade shell path in this repository is [`shells/electron/`](../../shells/electron/).

Current responsibilities:

- supervise Django and the task worker as child processes
- consume the shared staged backend from `.stage/backend/`
- package desktop artifacts with `electron-builder`
- generate shell-local icon outputs in `shells/electron/assets/icons/` from the shared brand source under `assets/brand/`

Use this shell when you need the most complete desktop path in the repo today.
