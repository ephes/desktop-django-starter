# Agent Use

This repository is intended to be usable by coding agents, not only by human readers.

## What An Agent Should Read First

Recommended order:

1. [`llms.txt`](llms.txt)
2. [`specification.md`](specification.md)
3. [`architecture.md`](architecture.md)
4. [`release.md`](release.md) for packaging/release tasks
5. [`decisions.md`](decisions.md)
6. repo-local skill at `skills/wrap-existing-django-in-electron/SKILL.md`

## What This Repo Should Help An Agent Do

- understand the minimum desktop-Django architecture quickly
- identify the integration seams in an existing Django codebase
- avoid copying `djdesk` product complexity into a smaller project
- preserve a server-rendered Django app while adding an Electron shell
- plan for packaging, Windows behavior, signing, and update constraints early

## Guardrails For Agents

- keep the app generic and minimal unless the target repo already has domain complexity
- prefer server-rendered templates over a SPA rewrite
- keep the preload bridge narrow
- do not assume `DEBUG=True` behavior in packaged mode
- do not assume online-only update flows; account for air-gapped environments
- do not import `djdesk` code wholesale

## Repo Outputs For Agents

- `llms.txt` provides a concise entry point
- the specification defines the product and technical boundaries
- the architecture notes define the expected runtime contract
- the release guide defines signing inputs, installer artifacts, and the manual update model
- the skill provides a reusable workflow for adapting another Django repo
