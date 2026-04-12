# Stage 2: Electron Adaptation Only

Use this prompt after the deterministic scaffold step from
`skills/wrap-existing-django-in-electron-staged/scripts/scaffold-target.sh`.

The scaffold already pre-adapts:

- `electron/package.json` identity plus the local `./scripts/stage-backend.cjs` path
- `electron/scripts/electron-builder-config.cjs` starter-specific identity strings and wrapped-repo resource paths
- wrapped-target repo-root assumptions in `electron/main.js` and `electron/scripts/launch-electron.cjs`
- wrapped-target manage/settings assumptions in `electron/main.js`, `electron/scripts/stage-backend.cjs`, and `electron/scripts/bundled-python.cjs`
- a default native navigation menu in `electron/main.js` with Home, Back, and Forward actions
- a generic light splash asset under `electron/assets/wrapped-splash.html`
- wrapped-target Electron test naming cleanup
- wrapped-target runs default to no background task worker unless `DESKTOP_DJANGO_ENABLE_TASK_WORKER=1`
- the common Django desktop baseline files needed for Stage 3

Before launch, replace the `{{...}}` placeholders in the facts block below.

Do not explore the whole repo. The scaffold is already copied into `electron/`.
If `git status --short` already shows deterministic Django-side changes outside
`electron/`, treat them as expected Stage 1 output and ignore them in Stage 2.

## Target facts

- Target repo: `{{TARGET_REPO_NAME}}`
- Desktop manage.py path: `{{TARGET_MANAGE_PATH}}`
- Development Django settings module: `{{TARGET_DEV_SETTINGS_MODULE}}`
- Planned packaged settings module name: `{{TARGET_PACKAGED_SETTINGS_MODULE}}`
- App source directories that packaged mode must account for: `{{TARGET_APP_DIRS}}`
- Root URL behavior: `{{TARGET_ROOT_URL_BEHAVIOR}}`
- Theme/background direction: `{{TARGET_THEME_NOTES}}`
- Files you may read for confirmation:
  - `{{TARGET_MANAGE_PATH}}`
  - `{{TARGET_SETTINGS_FILE}}`
  - `{{TARGET_URLS_FILE}}`
  - `{{TARGET_BASE_TEMPLATE_FILE}}`

## Your task

Adapt only the Electron-side scaffold for this target repo.

This stage is verification-first and stop-early:

1. run the narrow checks first
2. if all checks pass, stop immediately and report a zero-edit Stage 2 success
3. only if a check fails may you read the minimum `electron/` files needed to diagnose that failure
4. only edit a file if a concrete Electron-side mismatch remains after the deterministic scaffold

If the scaffold already satisfies Stage 2 cleanly, make no edits and report that Stage 2 completed with verification only.

Allowed writes:

- `electron/package.json`
- `electron/electron-builder.config.cjs`
- `electron/main.js`
- `electron/preload.cjs`
- `electron/scripts/**`
- `electron/assets/**`
- `electron/signing/**`

Forbidden writes:

- any file outside `electron/`

Required outcomes:

- app identity matches the target project instead of the starter
- path references match a wrapped project with `electron/` at repo root
- `main.js` launches the correct target `manage.py`
- Electron-side packaged-backend validation matches the target repo layout
- desktop users have a native path back to the app's primary view even when browser chrome is gone
- background color matches the target app's visual direction
- Electron-side tests and builder config no longer mention `desktop-django-starter`
- Stage 2 may complete with zero edits if the scaffold already covers those items

Important constraints:

- make the smallest coherent edits possible
- do not read extra `electron/` files after the verification bundle passes
- do not read `electron/` source files before the verification bundle unless a command itself is blocked or unclear
- treat `electron/package.json` as already scaffold-normalized; only edit it if
  a concrete Electron-side check shows more work is needed
- do not rewrite a long file from scratch unless the file is obviously unusable
- do not perform whole-file exact-string replacement attempts against
  `electron/package.json`
- do not add Django settings, middleware, URLs, or templates in this stage
- ignore expected deterministic Django scaffold files outside `electron/`
- if a needed Django-side fix is discovered, leave a concise note in your final
  summary instead of editing it now
- do not widen the task back into general repo exploration or redesign work

## Verification

Run only narrow Electron-side checks in this stage:

1. `git status --short`
2. `node --check electron/main.js`
3. `node --check electron/scripts/launch-electron.cjs`
4. `node --test electron/scripts/*.test.cjs` if the copied tests are runnable without extra install work; otherwise say clearly that you skipped them

If checks 1 to 4 pass, do not inspect any more files. Finalize immediately with a
verification-only Stage 2 summary.

At the end, report:

1. files changed
2. any known deferred Django-side dependencies for Stage 3
3. which checks ran and whether they passed
