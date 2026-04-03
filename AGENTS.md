# Desktop Django Starter

## Repo Intent
- Keep this repo a minimal, generic teaching starter for packaging a server-rendered Django app inside Electron.
- Preserve the Django-plus-Electron split already in the repo instead of collapsing behavior into one side.
- Use `djdesk` only as reference material for packaging and lifecycle patterns, not as a source to copy wholesale.

## Read First
- `llms.txt`
- `README.md`
- `docs/specification.md`
- `docs/architecture.md`
- `docs/decisions.md`
- `docs/agent-use.md`
- `skills/wrap-existing-django-in-electron/SKILL.md` when the task is about adapting another Django app

## Repo Map
- `src/desktop_django_starter/`: Django project, settings modules, base template, static assets
- `src/example_app/`: minimal server-rendered CRUD demo app
- `assets/brand/`: shared brand source-of-truth for shell-generated icons
- `scripts/`: shared packaging and staged-backend helpers
- `shells/electron/`: Electron shell, builder config, generated icons, Node-side tests
- `shells/tauri/`: experimental Tauri shell, Rust-side runtime supervision, and local plus hosted-artifact bundle helpers
- `shells/positron/`: experimental Positron shell, Briefcase config, and in-process runtime
- `docs/`: Sphinx source docs published from Markdown
- `tests/`: pytest coverage for backend behavior, packaged-runtime contract, static assets, and docs scaffold
- `skills/`: reusable agent workflows (wrap-existing-django-in-electron)

## Working Rules
- Prefer server-rendered Django templates. Do not introduce a SPA or broaden the preload bridge unless the task explicitly requires it.
- Treat `.stage/`, `docs/_build/`, `build/`, `dist/`, `shells/electron/dist/`, and `shells/electron/node_modules/` as generated outputs, not hand-edited sources.
- Packaged-mode changes must keep the bundled-runtime contract intact and must not assume `DEBUG=True`.
- Windows packaging and offline/manual install constraints matter. Do not make macOS-only assumptions in packaging or runtime changes.

## Documentation Updates
- Work is not complete until documentation matches the implementation when behavior, workflow, packaging steps, or user-facing usage changes.
- Update the relevant source docs in the same change. Typical targets here are `README.md`, `llms.txt`, and files under `docs/`.
- Treat missing or stale docs as incomplete work.

## Validation
- Full pre-push check: `just check` (lint + test + docs-build)
- Default validation for completion and handoff should be `just check`, not `just test` alone
- `just test` is only a narrower loop while iterating locally
- If docs changed: `just docs-build`
- If Electron code or packaging scripts changed: `npm --prefix shells/electron test`
- If packaged-runtime behavior changed: run `just packaged-smoke` unless the task requires a broader packaged run
