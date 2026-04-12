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

From inside the target Django project:

```bash
# Preflight: checks the target repo and prints the agent command
~/projects/desktop-django-starter/scripts/wrap

# Run the agent
~/projects/desktop-django-starter/scripts/wrap --run
```

This requires an existing `desktop-django-starter` checkout on disk. The starter
repo is inferred from the script's location, or specified with `--starter`:

```bash
~/projects/desktop-django-starter/scripts/wrap --starter ~/projects/desktop-django-starter
```

The packaged CLI can be run without a local starter checkout:

```bash
uvx desktop-django-starter wrap --run
uvx desktop-django-starter wrap --run --harness pi --model openai-codex/gpt-5.4
```

With the default `claude` agent, current `dds` builds stream concise progress
while the agent works. Older builds delegated to Claude's default `-p` text
output, which could make a long wrapping run look idle until Claude exited.
Use `--harness` and `--model` to choose the agent harness and model. `--agent`
remains available as a backward-compatible alias.

After wrapping, the target repo has an `electron/` directory and justfile targets:

```bash
just desktop-dev          # Electron + Django dev mode
just desktop-dev-smoke    # headless boot + health check
npm --prefix electron test  # node-side tests
```

### Benchmarking local models with Ollama

For local-model experiments, benchmark the real wrap prompt before running the
agent. The repo includes a small helper script for this:

```bash
# Terminal 1
ollama serve

# Terminal 2
~/projects/desktop-django-starter/scripts/bench-wrap-local-models \
  --target ~/projects/django-resume \
  --pull
```

By default the script compares `qwen3-coder` and `glm-4.7-flash`. It generates the
resolved wrap prompt with `scripts/wrap --emit-prompt`, appends a snapshot of the
target repo, sends the benchmark prompt to Ollama's `/api/generate`, and writes:

- the exact prompt used
- raw Ollama responses per model
- a `summary.tsv` table with prompt tokens, prompt tokens/sec, generated tokens,
  generated tokens/sec, model load time, and total wall time

The helper disables model-native thinking by default so the generated-output
comparison is visible and stable across models. If you want to include each
model's native thinking behavior in the benchmark, add `--with-thinking`.

The default context request is `32768`, which is a conservative starting point for
64 GB shared-memory systems. Increase it only after the smaller context works:

```bash
~/projects/desktop-django-starter/scripts/bench-wrap-local-models \
  --target ~/projects/django-resume \
  --num-ctx 65536
```

When you are ready to try a real wrapping run with Pi through Ollama, configure Pi
for Ollama first and then run the standard CLI from a clean target repo clone:

```bash
ollama launch pi --config --model qwen3-coder

cd ~/projects/django-resume-clean
time uvx desktop-django-starter wrap --run --harness pi --model ollama/qwen3-coder
```

Use a clean clone or disposable worktree for these tests. `wrap --run` edits the
target repository.

For smaller local models that drift on the one-shot wrap prompt, use the
experimental staged workflow in
`skills/wrap-existing-django-in-electron-staged/` instead of editing the
original wrap skill. That path starts with a deterministic scaffold helper and
then narrows the model work into separate Electron, Django, and fix-from-failures
prompts.

The scaffold prepares the wrapped target for those later stages by:

- adapting the brittle Electron identity and wrapped-repo path boilerplate before Stage 2 starts, including `electron/package.json`
- recording deterministic target facts in `electron/wrap-target.json`, including development and packaged manage/settings paths
- laying down the common Django desktop baseline for Stage 3 so local models verify or narrowly adjust it instead of building packaged settings and middleware from scratch
- appending explicit target-side `just` shortcuts such as `just desktop-install`, `just desktop-stage`, `just desktop-packaged-start`, and `just desktop-smoke`
- enabling desktop auto-login defaults in the wrapped Electron runtime, with a single-user fallback when no username override is configured
- adding a minimal native Home, Back, and Forward menu plus small in-page back-to-list links for known wrapped-template shapes such as `django_resume`'s `headwind` pages

Stage 2 and Stage 3 are both verification-first and stop-early. Once the
required checks for a stage pass, the model should end that stage instead of
re-reading scaffolded files. If a target app still has no persistent in-page
navigation after the native menu is in place, Stage 3 may add the smallest
possible Django-side home/list link.

The Django scaffold handles both flat settings modules and common `settings/`
package layouts, including targets that need the desktop middleware inserted
into a shared base settings file. It also covers targets with no committed seed
SQLite database by generating a small runtime bootstrap that can run migrations
on the first real desktop app request. It still assumes a recognizable
`urlpatterns = [` layout rather than arbitrary project structure.

### Lab workflow (experiment harness)

For iterating on the wrapping skill itself, the `desktop-django-lab` tooling
creates paired worktrees for reset-and-rerun experiments:

```bash
# Create a paired workspace for any target Django app
djl new wiki-demo ~/projects/django-wiki

# Run the agent from the target worktree
cd ~/workspaces/wiki-demo/django-wiki
time claude --dangerously-skip-permissions \
  -p "$(cat ../desktop-django-starter/skills/wrap-existing-django-in-electron/prompt.md)" \
  --add-dir ../desktop-django-starter

# Reset for another run
djl reset wiki-demo
```

The lab tooling lives in dotfiles (`~/.config/desktop-django-lab/`), not in this repo.

### Key files

- `scripts/wrap` — front-door command for wrapping a target Django project
- `skills/wrap-existing-django-in-electron/SKILL.md` — the wrapping workflow, strategy,
  output shape, and verification steps
- `skills/wrap-existing-django-in-electron/prompt.md` — the prompt template used by
  `scripts/wrap` and the lab workflow
- `skills/wrap-existing-django-in-electron/run-log.md` — results from each test run,
  with git refs linking to the skill/prompt version used
- `skills/wrap-existing-django-in-electron-staged/SKILL.md` — experimental staged
  alternative for smaller local models
- `skills/wrap-existing-django-in-electron-staged/scripts/scaffold-target.sh` —
  deterministic stage-1 scaffold helper
- `skills/wrap-existing-django-in-electron-staged/prompt-stage-2-electron.md`,
  `prompt-stage-3-django.md`, `prompt-stage-4-fix-from-failures.md` — narrower
  stage prompts for reset-and-rerun experiments
- `skills/wrap-existing-django-in-electron-staged/run-log.md` — staged experiment log

### Iteration loop

1. Create a fresh workspace with the lab tooling (`djl new`)
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
