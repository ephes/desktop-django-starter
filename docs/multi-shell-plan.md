# Multi-Shell Separation Plan

Status: first layout/staging slice implemented on `experiment/multi-shell-separation-plan`; Tauri and Positron ports remain unimplemented

## Goal

Test whether this repo can evolve from an Electron-first starter into a properly separated multi-shell desktop Django repo without turning every shell experiment into a merge conflict against the others.

This page is a planning and backlog document for the spike branch. It is intentionally narrower than a full product spec.

## Current Scope For The Spike

The first spike should **not** attempt full release parity across Electron, Tauri, and Positron.

In scope for the broader separated-repo spike:

- one shared Django core under `src/`
- one shared brand asset source
- one Electron shell path
- one Tauri shell path that can start locally and optionally build a local macOS DMG
- one Positron shell path that can start locally and optionally build a local macOS DMG
- shell-specific docs and shell-specific local commands

Explicitly out of scope for the implemented first slice:

- GitHub Actions artifact generation for Tauri
- GitHub Actions artifact generation for Positron
- full signing/notarization parity outside the existing Electron path
- a fake "one launcher abstraction" that hides genuine shell differences
- forcing Positron to use the Electron subprocess model
- Windows packaged-build proof for Tauri or Positron

Implemented in this branch so far:

- shared brand source-of-truth under `assets/brand/`
- shell-neutral staged backend output under `.stage/backend/`
- Electron moved under `shells/electron/`

Still not implemented in this slice:

- runnable `shells/tauri/`
- runnable `shells/positron/`

Notes:

- Windows remains a required proof point for the repo baseline, but not for the first Tauri/Positron separation spike.
- Before any promotion to `main`, Tauri and Positron need an explicit follow-up decision on Windows support level.

## Existing Experiment Baseline

The current experiment branches are useful starting points, but they should be treated as selective input, not as merge candidates.

### `experiment/tauri-option`

Current useful traits:

- adds a runnable `tauri/` shell
- already reuses the staged backend contract from `electron/.stage/backend`
- already includes local dev, smoke, packaged-like, and host-bundle build commands
- already carries Tauri icon assets and bundle config

Current constraints:

- depends on the Electron staging pipeline rather than owning a shell-local staging step
- tests are light and mostly confirm docs/config keys
- does not add a release-grade CI lane

### `experiment/positron-option`

Current useful traits:

- already has a runnable Positron app path
- already supports local macOS app and DMG packaging commands
- already documents its scope and non-parity honestly
- includes better runtime-helper coverage than the Tauri branch

Current constraints:

- diverges from the Electron/Tauri process model by running Django and the task worker in-process on threads
- the branch, as written, deletes the Electron splash/icon path and rewrites shared UI files, so it is not safe to merge directly
- local macOS packaging currently depends on Briefcase ad-hoc signing

## Official Research Findings

### Electron / electron-builder

Findings from the official electron-builder docs:

- electron-builder supports separate config files via `--config <path>` rather than forcing one repo-global build config.
- build resources are configurable via `directories`, which means Electron icon and DMG assets do not need to live inside the shell directory forever.
- icon assets are expected in the configured build resources directory; Electron supports macOS `.icns`, Windows `.ico`, and common PNG inputs.

Implication for this repo:

- Electron can be moved into a shell-local directory while still consuming shared generated icon assets.
- The current icon work on `main` should be generalized into a shared brand pipeline rather than left as Electron-only source-of-truth.

Official sources:

- <https://www.electron.build/configuration.html>
- <https://www.electron.build/icons.html>
- <https://www.electron.build/cli>

### Tauri

Findings from the official Tauri docs:

- Tauri provides a dedicated `tauri icon` command that generates the desktop icon set from a single PNG or SVG input.
- generated icons are placed under `src-tauri/icons` by default, but the config can point to other icon locations.
- Tauri supports an explicit splashscreen flow with a hidden main window and a visible splashscreen window that is closed after startup tasks complete.
- Tauri supports bundling extra files through `tauri.conf.json > bundle > resources`.
- Tauri can build a local macOS DMG directly with `tauri build -- --bundles dmg`.

Implication for this repo:

- Tauri is a good fit for a separated shell directory.
- Tauri should keep a shell-local config and runtime, but it can still consume shared brand assets and a shared staged backend payload.
- Tauri can support the same Flying Stable icon identity and a shell-specific splash implementation without depending on Electron UI code.

Official sources:

- <https://v2.tauri.app/develop/icons/>
- <https://v2.tauri.app/learn/splashscreen/>
- <https://v2.tauri.app/develop/resources/>
- <https://v2.tauri.app/distribute/dmg/>

### BeeWare Briefcase / Positron

Findings from the official Briefcase and BeeWare docs:

- Briefcase supports multiple applications in a single project, with shared code and app-specific config sections.
- Briefcase application config includes `sources`, `icon`, and `splash_background_color`.
- relative paths in `pyproject.toml` are resolved from the directory containing that file, which makes a dedicated `shells/positron/pyproject.toml` workable.
- on macOS, Briefcase packages GUI apps as DMG, ZIP, or PKG.
- Briefcase's macOS docs state that macOS apps use `.icns` icons and do not support splash screens or installer images.
- using `--adhoc-sign` on macOS produces an app that runs on the local machine only and is not suitable as a distribution-grade release artifact.
- the upstream Positron README documents the Django model as a web-view-oriented path rather than an Electron-style subprocess shell.

Implication for this repo:

- Positron fits as a separate shell track, but not as a shared runtime abstraction.
- Positron should keep its own shell-specific startup model and should not own the shared splash design, because Briefcase macOS packaging does not support splash screens.
- local macOS DMG proof is realistic for the spike; release parity is not.

Official sources:

- <https://briefcase.beeware.org/en/stable/reference/configuration/>
- <https://briefcase.beeware.org/en/stable/reference/platforms/macOS/index.html>
- <https://github.com/beeware/toga/blob/main/positron/README.md>

## Repo-Level Conclusions

### 1. Shared Django core is realistic

The backend, example apps, and most docs can remain shared.

`src/tasks_demo/` remains part of the shared backend tree, but it should still be treated as the optional post-v1 extension rather than as a required capability for every shell.

### 2. Shared brand assets are realistic

The source-of-truth brand assets should move out of `electron/assets/icons/` into a repo-level brand directory so each shell can generate its own outputs.

Suggested source-of-truth directory:

- `assets/brand/`

Suggested contents:

- canonical SVG logo mark
- canonical app icon source
- optional shell-neutral splash illustration assets
- generation scripts or manifests

### 3. Electron and Tauri can share more than Positron

Electron and Tauri can both work with a staged bundled backend plus explicit subprocess lifecycle management.

Positron should be allowed to stay different:

- in-process Django
- in-process worker
- no packaged splashscreen assumption on macOS

### 4. Shell-specific release lanes are required

Each shell should own its own local build commands, config, and release story. The first spike only needs:

- local start for all three shells
- local macOS DMG path for Electron, Tauri, and Positron

### 5. Full release parity should be deferred

The spike should prove separation, not finish distribution hardening.

### 6. The staged backend should become shell-neutral

The current Tauri branch reuses `electron/.stage/backend`, which is pragmatic but keeps Tauri coupled to Electron naming and path layout.

Proposed spike decision:

- move the shared staged backend output to a repo-level `.stage/backend/`
- move the stage-build logic into shared tooling rather than keeping it inside `shells/electron/`
- let Electron and Tauri consume the same staged backend payload from that shell-neutral location

Shared-tooling placement is a spike design decision that must be resolved during the Electron move. Plausible homes:

- a top-level `scripts/` directory
- a small shared Python or Node helper invoked from `just`
- a shell-neutral staging module that both Electron and Tauri call

The spike does not need to decide this in advance, but it does need to choose one explicit location before the Tauri port begins.

This should be treated as a spike decision, not a permanent truth. If it increases complexity materially, the spike should stop rather than forcing a bad shared abstraction.

### 7. The documentation blast radius is large and must be treated as real work

Separating Electron into `shells/electron/` is not a local path rename. At minimum, the spike should expect coordinated updates across:

- `README.md`
- `llms.txt`
- `AGENTS.md`
- `CLAUDE.md`
- `docs/specification.md`
- `docs/architecture.md`
- `docs/release.md`
- `skills/wrap-existing-django-in-electron/SKILL.md`

This documentation cascade is part of the implementation work, not cleanup to do later.

## Proposed Target Layout

```text
desktop-django-starter/
├── assets/
│   └── brand/
│       ├── app-icon.svg
│       ├── logo-mark.svg
│       └── splash/
├── docs/
│   ├── shells/
│   │   ├── electron.md
│   │   ├── tauri.md
│   │   └── positron.md
│   └── multi-shell-plan.md
├── shells/
│   ├── electron/
│   ├── tauri/
│   └── positron/
├── src/
│   ├── desktop_django_starter/
│   ├── example_app/
│   └── tasks_demo/
└── tests/
```

Notes:

- `.stage/backend/` is a generated build-time output and is intentionally not shown in the source layout tree above.
- `shells/electron/` can initially mirror the current `electron/` tree.
- `shells/tauri/` can absorb the useful parts of `experiment/tauri-option`.
- `shells/positron/` can absorb the useful parts of `experiment/positron-option`.
- the current untracked top-level `tauri/` and `positron/` directories should be treated as exploratory material only; the spike should decide early whether to move them into `shells/` or recreate the needed files cleanly there
- a compatibility pass can keep the current top-level `electron/`, `tauri/`, and `positron/` command entrypoints temporarily if needed, but the spike should prefer the final layout early.

## Proposed Shared Contracts

### Shared Across All Shells

- Django project and apps under `src/`
- localhost-only serving
- `/health/` readiness endpoint
- per-user writable app-data contract
- shared visual identity assets
- shell-specific docs that point back to common backend docs where possible

### Shared Between Electron And Tauri Only

- staged backend payload
- bundled Python runtime manifest
- subprocess startup and shutdown supervision
- packaged-like smoke flows
- shared `tasks_demo` subprocess worker model

### Positron-Only Contract

- Briefcase project config
- bundled Django code through Briefcase `sources`
- shell-local runtime bootstrap
- shell-local `tasks_demo` worker ownership through an in-process thread, if `tasks_demo` remains enabled there
- local macOS DMG proof only for the first spike

## `tasks_demo` Scope For The Spike

`tasks_demo` should remain present in the shared backend because it exercises exactly the kind of lifecycle differences the shell split must not hide.

Shell expectations for the first spike:

- Electron: keep the existing child-process `db_worker` supervision model
- Tauri: if `tasks_demo` is enabled, match Electron with child-process worker supervision as part of the Tauri port
- Positron: keep the current in-process worker thread model and document that this is intentionally different

If Tauri worker supervision proves too expensive during the spike, the fallback is not to fake parity. The fallback is to mark `tasks_demo` as temporarily unsupported in Tauri and document that explicitly.

## CI And Validation Transition

The current repo already assumes `electron/` paths in commands and validation. Moving Electron under `shells/` will break those assumptions unless the path transition is handled as part of the move.

Phase 2 and later should keep the baseline validation story working:

- `just test`
- `just docs-build`
- Electron shell tests
- any CI jobs that still call `npm --prefix electron ...`

The repo-level `.gitignore` will also need an explicit `.stage/` entry once staged output moves out of `electron/.stage/`.

The spike does not need to add full Tauri or Positron release CI, but it does need to keep the existing baseline green while paths move.

## Backlog

Estimates below are rough sizing only, not commitments.

### Phase 0: Document And Fence The Spike

Outcome:

- repo docs describe the branch as a multi-shell spike rather than the new baseline
- clear scope boundary: local start + optional local macOS DMG only for Tauri/Positron

Tasks:

- add this planning page
- add shell-specific doc placeholders
- record that Electron remains the most complete path while the spike is in progress
- state explicitly that a failed spike stays on the experiment branch and is not partially merged

Estimate:

- 0.5 day

### Phase 1: Create Shared Brand Asset Pipeline

Outcome:

- one canonical SVG source for the app icon and logo
- shell-local generated outputs rather than shell-local source art

Tasks:

- move or copy the current icon source into `assets/brand/`
- add a repo-level generation script or documented generation flow
- make Electron consume generated assets from the shared pipeline
- prepare equivalent generated outputs for Tauri and Positron

Estimate:

- 1 to 2 days

### Phase 2: Move Electron Into A Shell Directory

Outcome:

- Electron path keeps working after being treated as one shell among several

Tasks:

- move `electron/` to `shells/electron/`
- define the shell-neutral staged backend path as `.stage/backend/` and move shared staging helpers toward that contract
- update `justfile`, package paths, CI references, and docs
- update the broader doc set, including `README.md`, `llms.txt`, `AGENTS.md`, `CLAUDE.md`, `docs/specification.md`, `docs/architecture.md`, `docs/release.md`, and `skills/wrap-existing-django-in-electron/SKILL.md`
- add the top-level `.gitignore` entry for `.stage/`
- verify staged runtime and icon/splash paths still work

Estimate:

- 2 to 3 days

### Phase 3: Port Tauri As A Separate Shell

Outcome:

- Tauri can start locally from its own shell directory
- Tauri can optionally build a local macOS DMG

Tasks:

- port the useful `experiment/tauri-option` files into `shells/tauri/`
- replace the current `electron/.stage/backend` dependency with the shell-neutral `.stage/backend/` contract
- swap in shared brand assets instead of Tauri defaults
- keep or restore child-process `tasks_demo` worker supervision if `tasks_demo` remains enabled for Tauri
- add shell-specific docs
- keep GitHub artifact generation out of scope

Estimate:

- 2 to 4 days

### Phase 4: Port Positron As A Separate Shell

Outcome:

- Positron can start locally from its own shell directory
- Positron can optionally produce a local macOS DMG

Tasks:

- port the useful `experiment/positron-option` files into `shells/positron/`
- keep Positron runtime ownership separate from Electron/Tauri
- stop Positron from deleting or owning shared Electron splash/icon files
- wire shared icon outputs into Briefcase packaging
- document that splashscreen parity is intentionally not required on macOS
- document the Windows gap explicitly and keep GitHub artifact generation out of scope

Estimate:

- 3 to 5 days

### Phase 5: Create Shell-Specific Validation Lanes

Outcome:

- the spike can be validated without pretending that all shells have equal distribution maturity

Tasks:

- add per-shell smoke commands
- add per-shell docs pages with support level and gaps
- add limited tests that check shell layout, command surface, and key runtime assumptions
- document the support matrix clearly enough that users can tell Electron baseline from Tauri/Positron experiment scope

Estimate:

- 1 to 2 days

## First Spike Acceptance Criteria

The spike is good enough to review if all of the following are true:

- Electron still launches with the current splash screen and Flying Stable icon path
- Tauri launches locally from its own shell directory
- Positron launches locally from its own shell directory
- Electron can still build its current packaged artifacts
- Tauri can produce a local macOS DMG
- Positron can produce a local macOS DMG, with docs clearly noting the ad-hoc-sign limitation if that remains true
- shared Django code lives in one place
- shared brand assets live in one place
- the docs explain that Tauri and Positron do not yet have GitHub Actions artifact lanes
- the docs explain the Windows support gap for Tauri and Positron in the spike

## Failure And Rollback Criteria

The spike should be considered unsuccessful and left on its branch if any of the following happen:

- the shared staging contract makes Electron or Tauri materially harder to understand than the current shell-local setup
- path separation causes persistent CI breakage that requires shell-specific hacks just to keep Electron working
- shared asset generation becomes more fragile than the current Electron-only icon pipeline
- the repo starts implying Tauri or Positron release parity that the implementation does not support
- the documentation burden outweighs the value of having all three shells in one repo

Rollback path:

- do not merge the spike
- keep Electron on `main` as the baseline
- salvage only the planning/docs material or shell-specific research notes that remain useful

## Main Risks

- shell drift: three shells evolve incompatible assumptions about runtime layout
- asset drift: each shell starts carrying its own icon/logo copies again
- fake abstraction: an attempted shared launcher makes the code worse instead of clearer
- doc drift: support level per shell becomes unclear
- Positron parity pressure: the repo starts implying release parity that the official Briefcase constraints do not support

## Recommendation

Proceed with the spike on this branch only if the goal is exploration, not immediate promotion to `main`.

If the spike succeeds, the existing Electron-specific skill should be reviewed for either:

- an updated Electron-specific path/layout section, or
- a follow-on multi-shell skill that makes the shell choice explicit

This is follow-on work, not a blocker for the first separation spike.

The best first implementation order is:

1. shared asset pipeline
2. Electron as one shell directory
3. Tauri port
4. Positron port

That order preserves the most working behavior while reducing the chance that Positron-specific constraints dominate the repo shape too early.
