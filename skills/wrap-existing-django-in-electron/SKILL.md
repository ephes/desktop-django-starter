---
name: wrap-existing-django-in-electron
description: Use this skill when a user wants to add an Electron shell around an existing Django project, especially from a different repository. It provides the workflow, guardrails, and key integration points for adapting a server-rendered Django app into a local desktop app with a bundled Python runtime.
---

# Wrap Existing Django In Electron

Use this skill when the user already has a Django project and wants to run it inside Electron without turning it into a different product.

## Read First

If you are using this skill from another Django repository, first locate this
`desktop-django-starter` repository or its published documentation. Resolve the
following paths against the starter repo, not the target repo you are changing.

Load only what you need from the starter repo:

- `docs/specification.md` for scope boundaries and non-goals
- `docs/architecture.md` for runtime contract and shutdown/update expectations
- `docs/decisions.md` for repo-specific tradeoffs
- `docs/agent-use.md` for agent guardrails

If source files are unavailable, use the published docs and `llms.txt` as the fallback context.

## Goal

Adapt the target Django repo so Electron becomes a thin desktop shell around the existing app.

Preserve:

- the Django app's existing server-rendered behavior where possible
- the existing domain model and app structure
- a narrow native integration surface

Avoid:

- rewriting the app as a SPA
- importing `djdesk` code wholesale
- adding product-level complexity that is not required for the target repo

## Workflow

1. Inspect the target Django repo.

Look for:

- `manage.py`
- settings layout
- static file handling
- SQLite or other database assumptions
- startup command and local dev commands
- whether the app already has a natural readiness URL

2. Define the Electron boundary.

Minimum boundary:

- Electron main process starts Django
- Django binds to `127.0.0.1` on a random port
- Electron waits on a health endpoint before loading the window
- Electron owns shutdown behavior

3. Make the Django runtime desktop-safe.

Check for:

- explicit development vs packaged settings
- writable database and app-data paths
- static files that still work with `DEBUG=False`
- host validation and CSRF assumptions

4. Add the smallest native surface.

Prefer:

- one preload bridge or one menu action
- simple native affordances such as opening the app-data folder

5. Plan packaging and release behavior early.

Minimum concerns:

- bundled Python runtime
- Windows process behavior and writable paths
- macOS signing and notarization expectations
- manual updates for air-gapped installs

6. Add CI expectations.

At minimum:

- validate on Linux, macOS, and Windows runners
- make Windows part of the normal feedback loop, not a late-stage check

## Required Output Shape

When implementing in another repo, aim for these seams:

- `electron/` shell code
- launcher script for Django
- explicit health endpoint
- packaged/static-file strategy
- docs explaining how desktop mode differs from normal web deployment

## Validation Checklist

- Django starts on a random localhost port
- Electron waits for readiness instead of racing page load
- packaged mode does not assume `DEBUG=True`
- shutdown works on Windows as well as macOS/Linux
- update docs include connected and air-gapped/manual paths
- CI exercises Windows, macOS, and Linux
