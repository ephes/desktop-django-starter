# Desktop Django Starter

Minimal, attendee-facing starter for shipping a Django app inside Electron with a bundled Python runtime.

This repository now includes the first runnable development slice of that idea: a tiny Django app served locally and supervised by Electron.

## Intent

- Be the canonical teaching repo for the DjangoCon Europe 2026 talk/blog cycle.
- Stay minimal, generic, and easy to adapt to an existing Django app.
- Show the hard parts people should not have to rediscover from scratch: process lifecycle, local runtime packaging, localhost boot, and cross-platform expectations.
- Use `djdesk` as reference material for packaging/build patterns only, not as the starter baseline.

## Current Status

Runnable development starter:

- Django 6.0.3 project under `src/desktop_django_starter/`
- tiny server-rendered CRUD demo app under `src/example_app/`
- Electron 40 shell under `electron/`
- random-port localhost startup with `/health/` readiness polling
- minimal preload bridge for opening the app-data folder

Packaging, signing, notarization, auto-update, and bundled Python for packaged builds are still deferred.

## Docs

- [`docs/specification.md`](docs/specification.md): main product and technical specification
- [`docs/architecture.md`](docs/architecture.md): intended runtime model and draft repo shape
- [`docs/decisions.md`](docs/decisions.md): repo-local decisions captured from the initial planning pass
- [`docs/agent-use.md`](docs/agent-use.md): how coding agents should consume this repo and reuse its skill

The docs are built with Sphinx over the Markdown sources in `docs/` and are intended to be publishable on Read the Docs.

## Agent Consumers

- `llms.txt`: concise repo entry point for coding agents
- `skills/wrap-existing-django-in-electron/SKILL.md`: reusable workflow for adapting an existing Django project to an Electron shell
- `docs/agent-use.md`: agent-oriented usage notes and guardrails

## Development

- `just install`: install the local environment with `uv`
- `just migrate`: apply the local SQLite migrations
- `just backend-dev`: run the Django app directly on `127.0.0.1:8000`
- `just electron-install`: install Electron dependencies
- `just electron-start`: start the Electron shell, which launches Django on a random localhost port
- `just dev`: same as `just electron-start`
- `just docs`: build the docs and open the generated site
- `just docs-serve`: run a live-reloading local docs server
- `just test`: run the Django and docs test suite
- `just build`: build the Python package metadata scaffold

## Quickstart

1. `just install`
2. `just electron-install`
3. `just dev`

For backend-only work, use `just backend-dev`.

## What This Repo Should Eventually Provide

- A minimal Electron shell that starts Django locally
- A bundled Python runtime for packaged builds
- A tiny example Django app that still feels real
- Clear extension points for replacing the example with your own Django project
- Cross-platform packaging guidance with Windows as a required proof point
