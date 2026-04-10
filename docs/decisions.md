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

## D-011: Tasks demo uses the original-author task backport with one database-backed worker

The `tasks_demo` app remains an optional post-v1 extension, but it now uses the `django_tasks` backport together with `django_tasks_db` and one supervised `db_worker` process. The UI contract stays starter-sized: the app keeps its own demo row, the renderer continues to poll, and Electron owns the worker lifecycle. Product-sized worker registries, cancellation flows, and broader orchestration remain out of scope.

## D-012: Per-session shell-to-Django auth token for Electron

Electron adds a per-session shell-to-Django auth token to the localhost request channel. The main process generates a random token at startup, passes it to Django as `DESKTOP_DJANGO_AUTH_TOKEN`, and injects `X-Desktop-Django-Token` only for the exact `http://127.0.0.1:<random-port>` Django origin. Django rejects requests with missing or wrong tokens only when that setting is configured.

The token is not exposed through preload or normal page JavaScript and does not replace Django's CSRF middleware. Electron keeps the token out of query strings and cookies because its `webRequest.onBeforeSendHeaders` path can inject the header for the exact Django origin.

## D-013: Bootstrap cookie auth for Tauri and Positron

Tauri and Positron also generate per-session shell-to-Django tokens and pass them to Django as `DESKTOP_DJANGO_AUTH_TOKEN`, but they use a bootstrap-cookie transport instead of trying to copy Electron's hidden header hook. Their current public web view APIs do not expose an Electron-equivalent external-localhost per-request header injection path.

The shell starts its web view at `/desktop-auth/bootstrap/?token=...&next=/`. Django validates the token, sets an HttpOnly same-origin cookie with `SameSite=Strict`, and redirects to the safe relative `next` target so the token is not retained in the current app URL. The cookie is intentionally not `Secure` because the starter serves the local app over `http://127.0.0.1:<random-port>`.
