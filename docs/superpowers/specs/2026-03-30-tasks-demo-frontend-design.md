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
| `label` | CharField | Human-readable name (e.g., "Crunching numbers") |
| `status` | CharField (choices) | PENDING, RUNNING, DONE, FAILED |
| `result` | TextField (nullable) | Success message or error string |
| `duration` | FloatField (nullable) | Seconds the task took |
| `created_at` | DateTimeField (auto_now_add) | When the task was created |
| `completed_at` | DateTimeField (nullable) | When the task finished |

### Views

- **`task_list`** — Renders the tasks page (HTML). Lists all tasks ordered by newest first.
- **`task_create`** — POST only. Creates a new `SimulatedTask` in PENDING state with a label randomly chosen from a small hardcoded list (e.g., "Crunching numbers", "Analyzing data", "Generating report", "Processing records"). Starts a background thread that:
  1. Sets status to RUNNING
  2. Sleeps for a random 3–10 seconds
  3. Sets status to DONE (with a result string) or FAILED (~20% chance, with an error message)
  4. Records duration and completed_at
- **`task_status`** — GET, returns JSON array of all tasks with their current state. Polled by the frontend.

### URLs (under `/tasks/`)

| Path | Name | Method | View |
|------|------|--------|------|
| `""` | `task-list` | GET | `task_list` |
| `"run/"` | `task-run` | POST | `task_create` |
| `"status/"` | `task-status` | GET | `task_status` |

## Frontend

### Navigation

Add nav links to the masthead in `base.html`:
- "Items" links to `/` (the item list)
- "Tasks" links to `/tasks/`
- Active page gets a highlighted style (teal text vs muted)

### Template: `task_list.html`

- Extends `base.html` with heading "Background Tasks"
- **Run bar**: "Run Task" button + hint text ("Starts a simulated background task")
- **Task list**: Rows showing indicator, task name, status badge, and timing metadata
- **Result rows**: Completed/failed tasks show result or error text below the task row
- **Empty state**: "No tasks yet. Hit Run Task to start one."

### Task States and Indicators

| State | Indicator | Badge | Meta |
|-------|-----------|-------|------|
| PENDING | Hollow amber dot | Amber "Pending" | "queued" |
| RUNNING | Pulsing teal rings | Teal "Running" | Elapsed seconds (live) |
| DONE | Solid teal dot + ✓ | Muted "Done" | Duration + relative time |
| FAILED | Solid red dot + × | Red "Failed" | Duration + relative time |

### JavaScript (inline, no build step)

- **Polling**: Calls `/tasks/status/` every 2 seconds while any task is PENDING or RUNNING. Stops when all tasks are terminal.
- **Run Task**: POSTs to `/tasks/run/` via `fetch`, then starts/resumes polling.
- **DOM updates**: On each poll, updates indicators, badges, elapsed times, and result rows.
- **CSRF**: Token read from cookie using the standard Django pattern.

### CSS additions to `app.css`

- Pulse ring `@keyframes` animation and indicator classes (running, pending, done, failed)
- Status badge colors (teal, amber, muted gray, red)
- Task row layout (flex with indicator, name, badge, meta)
- Result row styling (indented, smaller text)
- Nav link styles in masthead (active vs inactive)

## Testing

### Backend tests (`tests/test_tasks_demo.py`)

- Task creation via POST returns redirect or appropriate response
- Status endpoint returns JSON with correct task structure
- Task model states are valid
- Task list page renders with 200 and includes the "Run Task" button
- Status endpoint returns empty list when no tasks exist

### Validation

- Existing tests remain untouched
- `just test` must pass after the change
- No JS-level testing (consistent with how the starter handles the example app)

## Documentation Updates

- `docs/specification.md` section 9: Note tasks demo frontend is implemented, `django.tasks` deferred
- `docs/decisions.md`: Add D-011 recording that the tasks demo uses stub threading for now
- `docs/architecture.md`: Update deferred areas section
- `llms.txt`: Mention the new `tasks_demo` app

## Explicit Non-Scope

- No `django.tasks` integration (deferred to follow-up)
- No persistent task history / cleanup / pagination
- No task cancellation
- No WebSocket or SSE
- No JS build tooling or framework
