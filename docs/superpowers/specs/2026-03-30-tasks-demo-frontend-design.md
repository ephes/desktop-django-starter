# Tasks Demo Frontend — Design Spec

Status: Approved
Date: 2026-03-30
Scope: Frontend-only async task visualization with stub backend endpoints

## Summary

Add a new `tasks_demo` Django app that demonstrates background task visualization with animated pulse-ring indicators and live polling. The backend uses stub threading to simulate async work. Real `django.tasks` integration is deferred to a follow-up.

## Motivation

The starter currently demonstrates CRUD with server-rendered templates but has no async/background task example. Adding a tasks demo page shows how a desktop Django app can handle longer-running operations with visual feedback — a common need for local desktop tools. This also creates the frontend foundation for a future `django.tasks` integration.

## Decisions

- **Simulated work**: Tasks sleep for a random duration rather than doing real computation. This keeps the demo generic and lets the visual treatment be the focus.
- **Separate page**: Tasks live on their own page (`/tasks/`) with a nav link in the masthead, rather than being embedded in the items page or a drawer. This preserves the teaching pattern of one app = one concern.
- **Pulse ring visualization**: Running tasks show animated concentric teal rings radiating from a dot. Chosen for its calm, desktop-app-native feel over alternatives (waveform, orbit spinner, segmented fill).
- **Polling, not WebSocket**: The frontend polls a JSON endpoint every 2 seconds. No WebSocket/SSE complexity.
- **No JS build step**: All JavaScript is inline in the template, consistent with the starter's server-rendered philosophy.
- **Frontend-only slice**: The backend is a stub with threading. `django.tasks` comes later.

## New App: `tasks_demo`

Location: `src/tasks_demo/`

### Model: `SimulatedTask`

| Field | Type | Notes |
|-------|------|-------|
| `id` | AutoField | Primary key |
| `label` | CharField | Human-readable name (e.g., "Restocking hay loft") |
| `status` | CharField (choices) | PENDING, RUNNING, DONE, FAILED |
| `result` | TextField (nullable) | Success message or error string |
| `duration` | FloatField (nullable) | Seconds the task took |
| `created_at` | DateTimeField (auto_now_add) | When the task was created |
| `completed_at` | DateTimeField (nullable) | When the task finished |

### Views

- **`task_list`** — Renders the tasks page (HTML). Lists all tasks ordered by newest first.
- **`task_create`** — POST only. Returns `201 Created` with a JSON body:
  ```json
  {"id": 5, "label": "Restocking hay loft", "status": "PENDING"}
  ```
  Creates a new `SimulatedTask` in PENDING state with a label randomly chosen from a small hardcoded list (e.g., "Restocking hay loft", "Brushing parade manes", "Polishing tack room brass", "Counting sugar-cube tins"). Launches the worker via `_launch_task(task_id)` (see Testing section), which starts a daemon thread targeting `_run_task_worker(task_id)`. The worker:
  1. Sets status to RUNNING
  2. Sleeps for a random 3–10 seconds
  3. Sets status to DONE (with a result string) or FAILED (~20% chance, with an error message)
  4. Records duration and completed_at
- **`task_status`** — GET, returns `200 OK` with a JSON body:
  ```json
  {
    "tasks": [
      {
        "id": 5,
        "label": "Restocking hay loft",
        "status": "RUNNING",
        "result": null,
        "duration": null,
        "created_at": "2026-03-30T14:22:01Z",
        "completed_at": null
      },
      {
        "id": 4,
        "label": "Brushing parade manes",
        "status": "DONE",
        "result": "Routine complete: every stall passed inspection.",
        "duration": 6.2,
        "created_at": "2026-03-30T14:20:50Z",
        "completed_at": "2026-03-30T14:20:56Z"
      }
    ]
  }
  ```
  Returns all tasks ordered newest first. The frontend uses `created_at` to compute elapsed time for running tasks and relative completion time for finished tasks.

### URLs (under `/tasks/`)

| Path | Name | Method | View |
|------|------|--------|------|
| `""` | `task-list` | GET | `task_list` |
| `"run/"` | `task-run` | POST | `task_create` |
| `"status/"` | `task-status` | GET | `task_status` |

### Startup reconciliation

The `tasks_demo` app's `AppConfig.ready()` marks any PENDING or RUNNING tasks as FAILED with the result string `"Abandoned — app restarted"` and sets `completed_at` to the current time. This prevents stale non-terminal rows from surviving across app restarts, which would otherwise cause the frontend to poll indefinitely and misrepresent task state.

## Frontend

### Navigation

Add nav links to the masthead in `base.html`:
- "Items" links to `/` (the item list)
- "Tasks" links to `/tasks/`
- Active page gets a highlighted style (teal text vs muted)

### Template: `task_list.html`

- Extends `base.html` with heading "Stable Routines"
- **Run bar**: "Start Routine" button + hint text ("Starts a simulated stable routine for the pony crew")
- **Task list**: Rows showing indicator, task name, status badge, and timing metadata
- **Result rows**: Completed/failed tasks show result or error text below the task row
- **Empty state**: "No routines underway. Start a routine to see the stable crew at work."

### Task States and Indicators

| State | Indicator | Badge | Meta |
|-------|-----------|-------|------|
| PENDING | Hollow amber dot | Amber "Pending" | "queued" |
| RUNNING | Pulsing teal rings | Teal "Running" | Elapsed seconds (live) |
| DONE | Solid teal dot + ✓ | Muted "Done" | Duration + relative time |
| FAILED | Solid red dot + × | Red "Failed" | Duration + relative time |

### JavaScript (inline, no build step)

- **Polling**: Calls `/tasks/status/` every 2 seconds while any task is PENDING or RUNNING. Stops when all tasks are terminal.
- **Start Routine**: POSTs to `/tasks/run/` via `fetch`, then starts/resumes polling.
- **DOM updates**: On each poll, updates indicators, badges, elapsed times, and result rows.
- **CSRF**: The `task_list` view is decorated with `@ensure_csrf_cookie` so the CSRF cookie is always set on the tasks page, even though there is no rendered `<form>`. The JS reads the token from the cookie and sends it as an `X-CSRFToken` header on the POST.

### CSS additions to `app.css`

- Pulse ring `@keyframes` animation and indicator classes (running, pending, done, failed)
- Status badge colors (teal, amber, muted gray, red)
- Task row layout (flex with indicator, name, badge, meta)
- Result row styling (indented, smaller text)
- Nav link styles in masthead (active vs inactive)

## Testing

### Deterministic testing seam

Two separate module-level functions provide the testing seam:

- **`_launch_task(task_id)`** — Called by the view. In production, starts a daemon thread targeting `_run_task_worker`. Tests patch this to call `_run_task_worker` synchronously (or to do nothing, when testing only the view/HTTP layer).
- **`_run_task_worker(task_id)`** — The pure worker body. Performs the PENDING → RUNNING → DONE/FAILED transitions, sleep, and DB updates. Tests call this directly for deterministic state-transition coverage.

The random duration (3–10s) and failure probability (~20%) are drawn from module-level constants `DURATION_RANGE = (3, 10)` and `FAILURE_RATE = 0.2`, also patchable in tests.

### Backend tests (`tests/test_tasks_demo.py`)

- Task creation via POST returns 201 JSON with `id`, `label`, `status` fields
- Status endpoint returns 200 JSON matching the documented schema
- Status endpoint returns `{"tasks": []}` when no tasks exist
- Task list page renders with 200 and includes the "Start Routine" button
- Task model status choices are valid
- Worker function (called directly, not via thread) correctly transitions PENDING → RUNNING → DONE
- Worker function (called directly, patched to fail) correctly transitions PENDING → RUNNING → FAILED
- Startup reconciliation marks stale PENDING/RUNNING tasks as FAILED with "Abandoned — app restarted"

### Validation

- Existing tests remain untouched
- `just test` must pass after the change
- No JS-level testing (consistent with how the starter handles the example app)

## Documentation Updates

- `README.md`: Mention the tasks demo in the project description
- `docs/index.md`: Add tasks demo to the documentation index
- `docs/specification.md` section 9: Note tasks demo frontend is implemented as an optional post-v1 extension, `django.tasks` deferred
- `docs/decisions.md`: Add D-011 recording that the tasks demo is an optional post-v1 extension with stub threading
- `docs/architecture.md`: Update deferred areas section
- `llms.txt`: Mention the new `tasks_demo` app

## Relationship to v1 Scope

This is an **optional post-v1 extension**, not a change to the starter's core v1 story. The specification (section 9) and decisions log (D-005) established that background tasks are deferred from v1. This demo fulfills the spec's note to "document a future extension path for one local background-task flow only after the minimal starter is stable." The tasks demo app is additive — the core starter remains complete without it.

## Explicit Non-Scope

- No `django.tasks` integration (deferred to follow-up)
- Tasks persist in the database for the demo (no ephemeral in-memory store), but no retention policy, cleanup, or pagination is included
- No task cancellation
- No WebSocket or SSE
- No JS build tooling or framework
