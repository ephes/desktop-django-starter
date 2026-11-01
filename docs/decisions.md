# Decisions

Status: initial repo-local decision log

## D-001: This repo is specification-first

Implementation follows only after the minimum starter boundaries are written down.

## D-002: The starter is attendee-facing and minimal

The repo should optimize for teachability and adaptation, not product depth.

## D-003: `djdesk` is reference material, not the baseline

We may borrow packaging and lifecycle patterns from the `djdesk` repo, but we are not trimming `djdesk` into the starter.

## D-004: The example app stays generic

The starter should use a simple single-user CRUD example instead of a domain-heavy or flashy demo.

## D-005: Background tasks are deferred

The first implementation will not include a worker framework or queue. If later needed, add one local background-task path only after the minimal starter is stable.

## D-006: Windows is a required proof point

Starter v1 must demonstrate that the packaged app can launch on Windows with a bundled Python runtime and writable local data storage.

## D-007: Manual updates are acceptable for v1

The repo should document signing, notarization, and release expectations, but auto-update infrastructure is not required in the first implementation.

## D-008: Coding agents are a first-class audience

The repo should be consumable both by humans and by coding agents working in other Django repositories.

## D-009: The update story must include air-gapped environments

The starter does not need a full auto-updater in v1, but it does need a documented offline/manual update path for controlled environments.

## D-010: GitHub Actions is the baseline CI

Cross-platform validation should run on GitHub-hosted Linux, macOS, and Windows runners from the start.

## D-011: Tasks demo uses Django's built-in task API with one database-backed worker

The `tasks_demo` app remains an optional post-v1 extension. It defines and enqueues tasks through Django's built-in `django.tasks` API (Django 6.0+) and stores and runs them through the `django_tasks_db` database backend and one supervised `db_worker` process. Earlier versions used the original author's `django_tasks` backport; `django_tasks_db` 0.13 builds on the built-in API on Django 6, so the backport is no longer installed. The UI contract stays starter-sized: the app keeps its own demo row, the renderer continues to poll, and Electron owns the worker lifecycle. Product-sized worker registries, cancellation flows, and broader orchestration remain out of scope.

## D-012: Per-session shell-to-Django auth token for Electron

Electron adds a per-session shell-to-Django auth token to the localhost request channel. The main process generates a random token at startup, passes it to Django as `DESKTOP_DJANGO_AUTH_TOKEN`, and injects `X-Desktop-Django-Token` only for the exact `http://127.0.0.1:<random-port>` Django origin. Django rejects requests with missing or wrong tokens when that setting is configured. Packaged settings also set `DESKTOP_DJANGO_REQUIRE_AUTH_TOKEN = True`, so a packaged backend started without a token refuses every request instead of silently serving unauthenticated; local development settings keep the check optional.

The token is not exposed through preload or normal page JavaScript and does not replace Django's CSRF middleware. Electron keeps the token out of query strings and cookies because its `webRequest.onBeforeSendHeaders` path can inject the header for the exact Django origin.

## D-013: Bootstrap cookie auth for Tauri and Positron

Tauri and Positron also generate per-session shell-to-Django tokens and pass them to Django as `DESKTOP_DJANGO_AUTH_TOKEN`, but they use a bootstrap-cookie transport instead of trying to copy Electron's hidden header hook. Their current public web view APIs do not expose an Electron-equivalent external-localhost per-request header injection path.

The shell starts its web view at `/desktop-auth/bootstrap/?token=...&next=/`. Django validates the token, sets an HttpOnly same-origin cookie with `SameSite=Strict`, and redirects to the safe relative `next` target so the token is not retained in the current app URL. The cookie is intentionally not `Secure` because the starter serves the local app over `http://127.0.0.1:<random-port>`.

## D-014: Version-isolated packaged state

Packaged settings keep the database, media and file cache under `<app-data>/state/<app version>/`, with the version passed by the shell as `DESKTOP_DJANGO_APP_VERSION`. A version's first start copies the newest older version's state (or the pre-versioning `app.sqlite3`) with the SQLite backup API into a staged directory and renames it into place before `migrate`. Older directories are kept, so a rollback reopens the older version's own data and schema instead of running old code against new migrations. State is never copied from a newer version. The cost is disk space and that data written by a newer version does not travel back on rollback; both are documented in the release guide.

## D-015: Backend processes are tied to the shell's lifetime

Electron and Tauri start every backend process through `desktop_process_guard.py`, a standard-library launcher that runs `manage.py` in-process. The shell holds the child's stdin pipe open; when the shell dies, the guard sees end-of-file and exits. On Windows the guard joins a `KILL_ON_JOB_CLOSE` Job Object so the backend's descendants die with it. Because the guard is a script in the backend bundle rather than a native module, it works the same for Electron (Node.js has no Job Object API) and Tauri, and for wrapped apps that copy it. As a last line of defence, a start after an unclean shutdown stops processes whose command line carries the install's random app key. `taskkill /t /f` and SIGTERM/SIGKILL stay the normal shutdown path.

## D-016: Ask before quitting while background tasks run

Quitting interrupts a running `db_worker` task. The shells therefore ask before closing or quitting while `/desktop/activity/` (Positron: the same counts in-process) reports running or queued tasks. Queued tasks are not lost; they run on the next start. The check never blocks quitting when it fails, and it is skipped for update installs and smoke tests.
