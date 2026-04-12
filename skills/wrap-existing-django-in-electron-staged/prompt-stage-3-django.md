# Stage 3: Django Integration Only

Use this prompt after Stage 2 completes and the Electron-side diff looks coherent.
The deterministic scaffold may already have created the common Django desktop
baseline. Verification-only Stage 3 is valid when that baseline already matches
the target cleanly.
For known wrapped-template shapes, the scaffold may also have added the
smallest in-page back-to-list affordance already.
The wrapped target may also already expose explicit `just` shortcuts such as
`desktop-install`, `desktop-stage`, `desktop-packaged-start`, and
`desktop-smoke`; prefer those when they exist instead of restating raw npm
commands in target-facing notes.

Before launch, replace the `{{...}}` placeholders in the facts block below.

Do not rediscover facts already present in `electron/wrap-target.json`.

## Target facts

- Target repo: `{{TARGET_REPO_NAME}}`
- Desktop manage.py path: `{{TARGET_MANAGE_PATH}}`
- Packaged manage.py path from scaffold metadata: `{{TARGET_PACKAGED_MANAGE_PATH}}`
- Development Django settings module: `{{TARGET_DEV_SETTINGS_MODULE}}`
- Packaged settings module to create: `{{TARGET_PACKAGED_SETTINGS_MODULE}}`
- Existing root URL behavior: `{{TARGET_ROOT_URL_BEHAVIOR}}`
- Auth behavior that desktop mode must avoid: `{{TARGET_AUTH_NOTES}}`
- Seed data/media notes: `{{TARGET_SEED_NOTES}}`
- Files you may read for confirmation:
  - `{{TARGET_SETTINGS_FILE}}`
  - `{{TARGET_URLS_FILE}}`
  - `{{TARGET_VIEWS_FILE}}`
  - `{{TARGET_BASE_TEMPLATE_FILE}}`

## Your task

Adapt only the Django-side integration for desktop mode.

This stage is verification-first and stop-early:

1. run the narrow verification commands first
2. if all checks pass, stop immediately and report a zero-edit Stage 3 success
3. only if a check fails may you read the minimum Django files needed to diagnose that failure
4. only copy or adapt a proven pattern when a failed check shows that the deterministic scaffold is still wrong

Preferred write set:

- verify or narrowly adjust the scaffolded packaged settings file
- verify or narrowly adjust the scaffolded desktop-only middleware
- verify or narrowly adjust the scaffolded URLconf updates for health and packaged static/media serving
- verify or narrowly adjust the scaffolded runtime helpers for seed database and seed media bootstrap
- add or narrowly adjust a minimal template-level home/list link when the app has no persistent in-page navigation and the native menu alone would not be enough
- target-repo docs or justfile entries if the desktop workflow changes user-visible commands

Forbidden writes:

- `electron/**` unless a tiny compatibility fix is unavoidable and you explain it clearly

Required outcomes:

- desktop mode never lands on a login page when the app needs desktop auto-auth
- desktop users can navigate back to the app's primary view without relying on browser chrome alone
- packaged mode works with `DEBUG=False`
- static assets and uploaded seed media have a credible packaged-mode path
- a stable `/health/` endpoint exists for Electron readiness polling
- target repo behavior stays server-rendered and minimal
- Stage 3 may complete with zero edits if the deterministic scaffold already covers the target cleanly

Important constraints:

- preserve existing auth data and existing users
- do not create new user accounts
- do not read extra Django or `electron/` files after the verification bundle passes
- do not read Django source files before the verification bundle unless a command itself is blocked or unclear
- gate desktop-only auth behavior behind environment variables
- for the current staged Electron shell, treat desktop auto-login as enabled by
  default; if the target has multiple existing users, require an explicit
  `DESKTOP_AUTO_LOGIN_USERNAME` override instead of silently choosing one
- if packaged mode imports a dev-only app that is not part of the bundled
  runtime, remove it from packaged settings instead of broadening the packaged
  dependency set
- prefer reusing the existing development settings module with no-op gated
  middleware and URL additions instead of introducing a separate desktop-dev
  settings module, unless the current dev settings are clearly incompatible
- for the current Electron path, prefer the existing header-based shell token
  contract; do not add a cookie bootstrap flow unless a concrete requirement
  appears in the target shell integration
- packaged seed handling must bootstrap writable copies, not mutate committed seed files
- keep the write set as small as possible

## Verification

Run only Django-side checks in this stage:

1. `git status --short`
2. `python {{TARGET_MANAGE_PATH}} check --settings {{TARGET_DEV_SETTINGS_MODULE}}` or the target's equivalent narrow check
3. `node electron/scripts/stage-backend.cjs` or the target's equivalent staged-backend build
4. `DJANGO_SECRET_KEY=stage-secret DESKTOP_DJANGO_BUNDLE_DIR="$PWD/.stage/backend" DESKTOP_DJANGO_APP_DATA_DIR="$PWD/.stage/runtime-data" python {{TARGET_MANAGE_PATH}} check --settings {{TARGET_PACKAGED_SETTINGS_MODULE}}`
5. one small request smoke that proves `/health/`, the authenticated app root, packaged static serving, seed-media bootstrap, and a visible path back to the app's primary view all work through the packaged manage path from `electron/wrap-target.json`

If checks 1 to 5 pass, do not inspect any more files. Finalize immediately with a
verification-only Stage 3 summary.

At the end, report:

1. files changed
2. any remaining Electron-side dependencies that still block full smoke testing
3. which checks ran and whether they passed
4. whether Stage 3 completed with verification only or required Django-side edits
