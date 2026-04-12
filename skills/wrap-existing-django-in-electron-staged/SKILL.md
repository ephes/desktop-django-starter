---
name: wrap-existing-django-in-electron-staged
description: Use this experimental workflow when the one-shot wrap prompt is too broad for a smaller local model. It splits the work into a deterministic scaffold step, a focused Electron adaptation step, a focused Django integration step, and a final fix-from-failures step.
---

# Wrap Existing Django In Electron, Staged

Use this experimental workflow when the original `wrap-existing-django-in-electron`
skill is too large for the model you want to run locally.

This workflow is intentionally separate from the original skill. Do not edit or
reinterpret the original one-shot prompt when you use this path.

## Goal

Reduce failure modes from smaller or local models by:

- removing the repetitive copy step from the model
- shrinking the prompt context per stage
- limiting each stage to a small write set
- feeding exact failures into a dedicated repair pass instead of asking the model
  to solve everything at once

## When To Use It

Prefer this staged workflow when:

- the one-shot wrap run stalls, drifts, or corrupts long files
- the model has a smaller or less reliable context window
- you want a tmux-friendly experiment loop with clean reset points between stages

Prefer the original skill when:

- the model is strong enough to handle the full wrap prompt cleanly
- you want the standard `scripts/wrap` or `dds wrap` path

## Stages

### Stage 1: Deterministic Scaffold

Run the scaffold helper from a clean target repo:

```bash
~/projects/desktop-django-starter/skills/wrap-existing-django-in-electron-staged/scripts/scaffold-target.sh \
  ~/projects/my-django-app
```

This copies the starter Electron skeleton into `electron/`, installs the shared
helper scripts directly into `electron/scripts/`, and then deterministically
rewrites the most brittle Stage 2 and common Stage 3 boilerplate before any
model edits:

- `electron/package.json` identity and local `stage-backend` script path
- `electron/scripts/electron-builder-config.cjs` identity strings and wrapped-repo paths
- wrapped-target repo-root assumptions in `electron/main.js`, `electron/scripts/launch-electron.cjs`, and `electron/scripts/stage-backend.cjs`
- wrapped-target development and packaged manage/settings assumptions in `electron/main.js`, `electron/scripts/stage-backend.cjs`, and `electron/scripts/bundled-python.cjs`
- a default Electron navigation menu with Home, Back, and Forward actions
- a generic wrapped splash asset under `electron/assets/wrapped-splash.html`
- copied Electron-side test naming cleanup
- wrapped-target runs default to no background task worker unless explicitly re-enabled
- `electron/wrap-target.json` with deterministic target facts for later stages, including development and packaged manage/settings paths
- a deterministic Django desktop baseline: packaged settings skeleton, desktop token middleware, runtime database bootstrap middleware for empty desktop SQLite databases, desktop auto-login middleware, health plus packaged static/media URL wiring, packaged seed database/media bootstrap helpers, desktop-safe `ALLOWED_HOSTS` additions for packaged test-client checks, and default Electron runtime auto-login with a single-user fallback
- known wrapped-template navigation affordances, such as a minimal back-to-list link for `django_resume` `headwind` pages
- explicit target-side `just` shortcuts for `desktop-install`, `desktop-stage`, `desktop-packaged-start`, and `desktop-smoke`

No model should do that copy or exact-string boilerplate rewrite work.

### Stage 2: Electron Adaptation Only

Use `prompt-stage-2-electron.md`.

Stage 1 already pre-adapts the most fragile Electron identity/path boilerplate.
Stage 2 should verify that scaffold, then finish only the small remaining
Electron-specific changes instead of redoing whole-file starter-to-target
rewrites. A zero-edit Stage 2 is valid if the deterministic scaffold already
covers the target cleanly. If the Stage 2 verification bundle passes, the model
should stop immediately instead of continuing to read `electron/` files.

Allowed writes:

- `electron/package.json`
- `electron/electron-builder.config.cjs`
- `electron/main.js`
- `electron/preload.cjs`
- `electron/scripts/**`
- `electron/assets/**`
- `electron/signing/**`

Forbidden writes:

- any non-`electron/` path

This stage should adapt:

- app identity
- path layout
- manage.py cwd assumptions
- packaged-backend path references
- native navigation affordances when the wrapped app would otherwise lose browser back/forward or a route back to its primary view
- background color
- Electron-side tests and builder config

This stage should not add Django settings, middleware, URLs, or templates.

### Stage 3: Django Integration Only

Use `prompt-stage-3-django.md`.

Allowed writes should be restricted to the Django-side integration files for the
target repo, for example:

- new desktop-specific settings files
- desktop-only middleware
- URLconf updates for health, splash, packaged static serving, or desktop auth bootstrap
- runtime helpers for seed database and seed media bootstrap
- target-repo docs or justfile entries if the workflow requires it

Forbidden writes:

- `electron/**` unless the stage prompt explicitly allows a tiny compatibility fix

This stage should add:

- desktop-safe settings split when the scaffold did not already cover it
- desktop auto-auth when the target app needs it
- a minimal in-app home/list link or breadcrumb when the target app has no persistent navigation and the native menu alone would not be enough
- packaged settings cleanup for dev-only apps that are not part of the bundled runtime
- packaged static serving
- seed database and media bootstrap
- health endpoint and any small splash-template integration

Read `electron/wrap-target.json` first so the model does not rediscover the
target's development and packaged manage paths, settings modules, packaged copy
roots, or seed asset paths from scratch.
If the deterministic scaffold already satisfies Stage 3 for the target, a
verification-only Stage 3 is a valid success outcome. If the Stage 3
verification bundle passes, the model should stop immediately instead of
continuing to read Django files or `electron/wrap-target.json` details again.

### Stage 4: Fix From Failures

Use `prompt-stage-4-fix-from-failures.md`.

Only feed exact failing command output into this stage. Do not ask the model to
"review everything again".

Use it after Stage 2 or Stage 3 when a concrete verification step fails.

## Operating Rules

- Start each experiment from a clean target repo or disposable worktree.
- Record target-specific facts yourself before launching a stage prompt. Do not
  ask the model to rediscover obvious repo facts if you already know them.
- Keep the write set small and explicit in every prompt.
- Prefer exact file paths over open-ended repo exploration.
- Prefer deterministic scaffold-time rewrites for brittle identity/path
  boilerplate instead of asking the model to exact-match replace long files.
- The Stage 1 Electron scaffold is pinned to the current starter Electron
  template files. If those starter templates change, update the compatibility
  guard and matching rewrite logic in `scripts/prepare-electron-scaffold.cjs`
  before rerunning staged experiments.
- The Django-side scaffold is now less tied to `django_resume`'s exact `LOGIN_URL`
  and URLconf formatting. It now handles both flat settings modules and common
  `settings/` package layouts, including targets that need middleware inserted
  into a shared base settings file, and it can bootstrap empty desktop SQLite
  databases when the target ships no committed seed DB. It still assumes a
  conventional `urlpatterns = [` declaration rather than arbitrary project
  structure.
- For slower local models, use a more generous Stage 3 timeout in the harness.
  Current runs were more reliable with `240s` than `120s`.
- Stop the run if the model starts rewriting a long file wholesale without a
  clear reason.
- Treat Stage 2 as a stop-early gate: if `git status`, both `node --check`
  commands, and the copied Electron tests pass, do not keep reading `electron/`
  files just to "double-check" a passing scaffold.
- Treat Stage 3 the same way: if the Django checks, staged-backend build, and
  packaged request smoke pass, do not keep reading Django files just to narrate
  a passing scaffold.
- After each stage, checkpoint the result with `git status --short` and a short
  diff review before moving on.

## Suggested Experiment Loop

1. Reset the target repo hard and clean it.
2. Run the deterministic scaffold helper.
3. Launch Stage 2 in tmux with a log.
4. Review the Electron-only diff.
5. If Stage 2 looks coherent, launch Stage 3 from that checkpoint.
6. Run exact verification commands.
7. If a command fails, use Stage 4 with only the relevant error output.
8. Record the result in this staged run log.

## Files

- `scripts/scaffold-target.sh` — deterministic stage-1 copy helper
- `scripts/prepare-electron-scaffold.cjs` — deterministic Electron identity/path helper used by stage 1
- `scripts/prepare-django-desktop-scaffold.cjs` — deterministic Django desktop baseline helper used by stage 1
- `prompt-stage-2-electron.md` — focused Electron-only prompt template
- `prompt-stage-3-django.md` — focused Django-only prompt template
- `prompt-stage-4-fix-from-failures.md` — exact-failure repair prompt template
- `run-log.md` — staged experiment results
