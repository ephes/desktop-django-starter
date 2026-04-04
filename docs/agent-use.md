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

## Wrapping An Existing Django Project

This repo provides an automated workflow for wrapping an existing Django project in
an Electron shell using an AI coding agent.

### Quick start

```bash
# Create a paired workspace (django-resume example)
just -f ~/.config/desktop-django-lab/Justfile new resume-demo

# Run the agent from the target project directory
cd ~/workspaces/resume-demo/django-resume
time claude --dangerously-skip-permissions \
  -p "$(cat ../desktop-django-starter/skills/wrap-existing-django-in-electron/prompt.md)" \
  --add-dir ../desktop-django-starter
```

The agent reads the skill, copies and adapts reference Electron code from this repo,
wires it into the target Django project, and self-verifies the result.

### Key files

- `skills/wrap-existing-django-in-electron/SKILL.md` — the wrapping workflow, strategy,
  output shape, and verification steps
- `skills/wrap-existing-django-in-electron/prompt.md` — the short invocation prompt
  piped to `claude -p`
- `skills/wrap-existing-django-in-electron/run-log.md` — results from each test run,
  with git refs linking to the skill/prompt version used

### Iteration loop

1. Create a fresh workspace with the lab tooling
2. Run the agent with the prompt (timed)
3. Check results against the verification steps in the skill
4. Record the run in `run-log.md` (see instructions in that file)
5. If it failed: improve the skill or prompt, commit, reset workspace, re-run

The workspace is disposable — reset and re-create freely. The skill, prompt, and run
log live in this repo and persist across workspace resets.

### Verification tiers

- **Tier 1 (dev mode):** existing tests pass, `just desktop-dev-smoke` passes,
  root URL returns 200/302, `npm --prefix electron test` passes
- **Tier 2 (packaged mode):** `just desktop-stage` and `just desktop-smoke` pass
- **Tier 3 (CI/cross-platform):** GitHub Actions packaging on Linux, macOS, Windows

## Repo Outputs For Agents

- `llms.txt` provides a concise entry point
- the specification defines the product and technical boundaries
- the architecture notes define the expected runtime contract
- the release guide defines signing inputs, installer artifacts, and the manual update model
- the skill provides a reusable workflow for adapting another Django repo
- the run log tracks iteration results and links them to skill/prompt versions
