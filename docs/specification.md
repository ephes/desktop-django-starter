# Desktop Django Starter Specification

Status: Draft 0.2  
Scope: specification for the starter, with the runnable development slice, staged packaged-backend slice, and sign/notarization-aware packaged-build slice now implemented, while auto-update remains deferred

## 1. Project Summary

`desktop-django-starter` is the canonical attendee-facing minimal example for running Django as a desktop application inside Electron.

It exists to answer a practical question: what is the smallest credible setup that lets a Django team package a local desktop app without having to invent the process model, packaging story, and localhost lifecycle from scratch?

## 2. Goal

The starter should help a Django developer:

- understand the minimum architecture needed to embed Django in Electron
- run the example locally in development with predictable commands
- build packaged desktop artifacts with a bundled Python runtime
- identify the exact seams where an existing Django app can replace the demo app
- give coding agents a stable spec and reusable adaptation workflow they can apply in other Django repositories

The repository should optimize for comprehension, teachability, and adaptation speed, not for feature breadth.

## 3. Target Audience

- Django developers who know server-hosted web apps but have not shipped desktop software
- conference attendees who need a clean reference implementation after the talk
- small teams evaluating whether an internal Django tool should run locally on user machines
- coding agents that need concise documentation and a reusable workflow for wrapping an existing Django app in Electron

## 4. Why This Exists Instead of "Just Combine Django and Electron Yourself"

`django-admin startproject` plus a basic Electron wrapper does not answer the parts that usually create real friction:

- how Electron starts and stops Django reliably
- how the app chooses a random localhost port and waits for readiness
- how Python is bundled so packaged builds do not depend on a system interpreter
- how SQLite and app data should live in a writable desktop location
- what "good enough" packaging looks like on macOS, Windows, and Linux
- what should stay out of scope so the example remains teachable

This starter should package those decisions into one minimal reference so users can begin from a stable baseline instead of rediscovering the integration details.

## 5. Why This App Runs Locally Instead of as a Normal Hosted Web App

The starter is intentionally local-first because that is the point of the example.

Reasons the architecture is useful:

- some tools handle confidential or regulated data that should stay on the device
- some environments are offline, air-gapped, or have unreliable network access
- some teams want desktop distribution while keeping Django templates, forms, models, and admin patterns
- some workflows benefit from light native integration such as opening a local folder or revealing app data without introducing a full separate frontend stack

Desktop-only justification for the starter:

- the example should include one minimal native affordance, such as "Open App Data Folder", to make the desktop context concrete without turning the app into a product demo

## 6. Product Shape for v1

The example app should be generic and single-user. It should feel real, but not domain-heavy.

Recommended v1 shape:

- a simple local "items" app
- one primary model such as `Item` with fields like title, notes, status, and timestamps
- list/create/edit/delete flow
- one server-rendered detail/edit page
- one desktop-only action exposed through a minimal Electron bridge or application menu

This is enough to demonstrate persistence, forms, templates, static files, and local desktop packaging without dragging in product-specific complexity.

### Current presentation layer

The example app currently uses a themed visual identity called "Flying Stable" (a Pegasus/pony theme). This is a demonstration of how the starter can carry a branded UI. The theme is entirely in the presentation layer (templates, CSS, static assets) and does not change the underlying architecture.

Key elements of the current themed UI:

- "My Ponies" section (CRUD demo) and "Stable Routines" section (background tasks demo)
- dark topnav with an SVG logo and "Flying Stable" brand name, with section links
- teal page header with background images (a custom illustration for My Ponies)
- content panel with a toolbar, sticky footer
- Item statuses themed as Grazing (backlog), Galloping (active), Show Ready (done)
- in-page modal for delete confirmations instead of a separate page
- client-side form validation with themed error messages (tooltip-style with warning icon)
- SVG empty-state illustrations (stacked documents for My Ponies, interlocking gears for Stable Routines)
- all colors defined as CSS custom properties (design tokens) in `:root`
- a splash screen at `/splash/` with animated logo and loading dots, now reused by Electron as the startup splash window
- packaged app icons derived from the same Flying Stable pony mark, with the source art stored under `assets/brand/` and generated into `shells/electron/assets/icons/`
- `django-browser-reload` for development auto-reload (local settings only)
- Play font loaded from Google Fonts, falling back to Helvetica Neue / Arial / sans-serif in offline or packaged mode

The theme is replaceable. When adapting this starter for a different project, the templates, CSS, and static assets are the seams where the visual identity lives.

## 7. Explicit Non-Goals

The starter must not become a framework or a thin copy of `djdesk`.

Out of scope for starter v1:

- multi-user collaboration
- remote hosting or cloud deployment flows
- plugin systems or extension marketplaces
- complex command runners or policy frameworks
- notebook, data-lab, or document-drawer features
- AI or agent-specific capabilities as part of the core example
- heavy frontend tooling unless the implementation later proves it is necessary
- production-hardening beyond the documented baseline
- fully automated cross-platform auto-update infrastructure
- broad background-job orchestration

## 8. Minimum Feature Set for v1

The smallest acceptable starter implementation should include:

- Electron main process that launches Django and opens a browser window
- Django served only on `127.0.0.1`
- random port allocation at startup
- explicit health/readiness check before the Electron window loads the app
- bundled Python runtime for packaged builds
- SQLite as the only database
- one example Django app with one simple model and basic CRUD
- one minimal preload or IPC example for a desktop-only action
- documentation showing how to swap in an existing Django project

Not required for v1:

- background workers
- WebSockets
- auto-updater
- multiple windows
- authentication or user accounts

## 9. Background Task Decision

Background work is not part of the minimum starter slice but an optional post-v1 extension is now included.

Decision for starter v1:

- do not include a worker framework, queue, or `django.tasks` example in the core v1 implementation
- the repo now includes an optional `tasks_demo` app that demonstrates background task visualization using `django_tasks`, `django_tasks_db`, and animated pulse-ring indicators

Extension (post-v1):

- `src/tasks_demo/` provides a separate page with a "Run Task" button, animated status indicators, and polling-based live updates
- the backend enqueues real tasks through the `django_tasks` backport and executes them in a single database-backed `django_tasks_db` worker process supervised by Electron
- the demo keeps its intentionally fake workload semantics: random duration, random success/failure, and starter-sized status/result reporting

Rationale:

- background task infrastructure is useful in production, but it is not required to prove the desktop Django architecture
- the demo keeps the teaching value by showing async UI patterns and a real worker process without expanding into a production-grade orchestration subsystem
- keeping the real worker in the optional demo, rather than the core starter flow, keeps the repo smaller, easier to explain, and less likely to drift toward `djdesk`

## 10. Expected Architecture

### Runtime model

- Electron is the desktop shell and process supervisor
- a bundled Python runtime is used for packaged builds
- Django runs locally on `127.0.0.1:<random-port>`
- Electron waits for a health check before loading the renderer window
- SQLite stores local data in a writable app-data location

Bundling direction for v1:

- the initial implementation is expected to use a `python-build-standalone` style bundled runtime, borrowing the general approach from `djdesk`
- this is the current expected direction, not an irrevocably fixed implementation choice

### Environment and settings model

The starter should support two clearly documented runtime modes:

- development mode: local interpreter, developer-friendly settings, and fast iteration
- packaged mode: bundled runtime, writable app-data paths, and production-like settings for local desktop use

Minimum expectation:

- the settings split between development and packaged runs must be explicit in the implementation and docs
- packaged mode should not rely on `DEBUG=True` behavior for static files or error handling

### Security baseline

- bind Django to `127.0.0.1` only
- use a random port instead of a fixed public default
- keep host validation tight
- keep CSRF protections enabled unless a specific implementation detail proves otherwise
- keep the preload bridge narrow and explicit

### Renderer model

- prefer server-rendered Django templates for the main UI
- keep frontend JavaScript small and optional
- avoid adding a SPA frontend to the starter baseline

### Health endpoint

The starter should define a dedicated readiness endpoint used by Electron during boot.

Minimum contract:

- a simple endpoint such as `/health/`
- returns HTTP 200 when Django is ready to serve the application
- does not depend on application-specific data
- used only as the desktop shell readiness check, not as a full observability system

## 11. Packaging Expectations

Packaged builds should include Electron, the Django code, static assets, and a Python runtime. A packaged app must not require the end user to install Python separately.

Expected release targets:

- macOS: signed app bundle with a DMG as the primary user-facing artifact; ZIP may exist as a secondary artifact
- Windows: installer as the primary artifact, plus a portable ZIP if convenient
- Linux: AppImage as the primary artifact; TAR.GZ or DEB can be secondary

Implementation note:

- the exact packaging tool is not fixed by this spec, but the initial implementation will likely borrow the `electron-builder` approach used in `djdesk`
- the packaged runtime should include a static-file strategy that works with `DEBUG=False`

## 12. What Must Work on Windows

Windows is a required proof point, not an afterthought.

Starter v1 should prove:

- the packaged app launches on a clean Windows machine without separately installed Python
- the bundled runtime can start Django reliably
- the app stores SQLite data in a writable user-data location
- the app can shut down the Django child process reliably on Windows
- the installer flow is documented clearly enough for attendees to follow

Windows-specific polish such as enterprise deployment tooling is out of scope for v1.

## 13. Signing, Notarization, and Updates

High-level release story for v1:

- macOS public distribution should assume code signing and notarization are required
- Windows code signing is recommended for public distribution, even if early workshop artifacts may be unsigned
- Linux signing is not a baseline requirement for the first public starter release
- connected environments may later add an auto-update path, but that is not required for starter v1
- starter v1 must still document a manual update path that works in air-gapped or tightly controlled environments

Minimum update story to document:

- connected installs: manually download and install a newer signed release artifact
- air-gapped installs: transfer a signed installer or zip through the approved offline channel and verify version/integrity before installation
- the repo should describe where release artifacts live and what a user or admin must replace during an offline update

Current implementation direction:

- macOS packaging uses `electron-builder` with hardened runtime, explicit entitlements, and env-driven notarization inputs
- the GitHub Actions packaging workflow is ready to consume signing/notarization secrets on platform-native runners without making local unsigned builds mandatory
- Windows signing remains optional and secret-driven rather than mandatory release automation

The repo should document these expectations clearly, but it still does not need to automate the entire release process.

## 14. Continuous Integration Expectations

The repository should use GitHub Actions from the start.

Minimum expectation:

- docs and test validation should run in CI on every push or pull request
- CI should run on GitHub-hosted runners
- the validation matrix should include macOS, Windows, and Linux
- Windows CI is required because Windows packaging and process behavior are part of the proof story

Packaging implication:

- later packaging workflows should use GitHub-hosted platform runners to produce platform-native artifacts, especially Windows builds that are inconvenient to produce reliably elsewhere

## 15. Extension Points for Existing Django Apps

The starter should make it obvious where a team can replace the demo app with its own code.

Required extension points:

- Django settings module and launcher contract
- location of the packaged Python runtime
- startup command for Django
- static file collection step
- writable database path and app-data path
- minimal preload bridge for native actions

The docs should also state what is not covered automatically:

- multi-service architectures
- external databases
- Celery or other distributed worker setups
- deployment patterns that assume a long-running remote server

Agent-oriented requirement:

- the repo should include a reusable `SKILL.md` workflow that a coding agent can apply from another Django repository when asked to add an Electron shell

## 16. Patterns We May Borrow From `djdesk`

These patterns are good candidates to reuse in simplified form:

- Electron main process supervising Django startup and shutdown
- random port selection and readiness polling
- a bundled Python runtime for packaged builds
- packaging the Django payload as an extra resource next to the app bundle
- a tiny preload bridge for a controlled native capability
- a cross-platform packaging matrix covering macOS, Windows, and Linux

## 17. What We Are Explicitly Not Copying From `djdesk`

Do not bring over the product-shaped parts of `djdesk`.

Explicit cuts:

- assistant or AI-oriented UI
- task presets and command-runner workflow
- offline documentation drawer
- sample project import pipeline
- multi-pane dashboard UX
- large documentation system
- advanced queue and polling surfaces
- broad settings matrix aimed at a richer product

## 18. What Should Be Documented Now vs Implemented Later

Document now:

- project intent and audience
- minimum feature set
- runtime contract between Electron and Django
- packaging expectations
- high-level signing/update stance
- extension points and non-goals
- agent-consumable entry points such as `llms.txt`
- a reusable skill for adapting an existing Django project

Implement later:

- Electron shell code
- bundled Python build step
- installer configuration
- sample app
- release promotion and checksum publication automation
- optional post-v1 background-task example

## 19. Acceptance Criteria

### A. "Spec complete"

The specification phase is complete when:

- the repo has a short top-level README and one main specification document
- goal, audience, and non-goals are explicit
- the minimum v1 feature set is frozen
- the runtime architecture is defined at a high level
- packaging expectations for macOS, Windows, and Linux are written down
- the `djdesk` borrow-vs-cut boundary is explicit
- acceptance criteria for starter v1 are documented
- the update story includes connected and air-gapped environments
- the repo includes an agent-readable `llms.txt` and one reusable `SKILL.md`

### B. "Starter v1 complete"

The implementation phase is complete when:

- a fresh clone has a documented development quickstart
- one command starts the app in development
- Electron launches Django locally and waits for readiness successfully
- the example CRUD app works with SQLite
- one packaged build path works on macOS
- one packaged build path works on Windows
- the repo explains how to swap the demo app for an existing Django project
- the repo includes a short "production gaps" section so users know what is intentionally omitted
- GitHub Actions validates docs/tests on Linux, macOS, and Windows
- the repo documents signing/notarization requirements and manual updates clearly enough for follow-on release hardening

## 20. Guiding Principle

If a feature makes the starter feel more like a product than a teaching reference, it probably does not belong in v1.
