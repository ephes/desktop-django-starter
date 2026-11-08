# Round 84 resume note

Branch: `fix/r84-task-authority`; base: `main` at
`c95cdcc325954ef3c58f8e8af464ecac2782b12c`.
Source report: `~/workspaces/ws-work-planning/reviews/scout-round84.md`.

Implementation stopped at the owner's explicit OAuth-expiry rule. No merge,
release, deployment, workflow invocation, or default-branch push was performed.

## B19: implemented, awaiting review and complete local validation

- `dds-task-backend-success-payload-admission`: completion objects validate
  terminal status, result string, finite nonnegative duration and aware ISO
  timestamp before the existing polling conditional update. Invalid objects fail
  clearly. Preserve the existing duplicate-worker active snapshot no-op.
- `dds-worker-finalization-current-claim-guard`: worker completion conditionally
  updates its running row and captured backend ID. Retired/deleted rows survive
  late workers unchanged. Missing backend metadata leaves running workers alive;
  startup reconciliation still handles abandoned claims.
- Specification and architecture updated. Repository has no changelog.
- Regression file: `tests/test_task_authority.py`; 24 failures against the original
  task implementation, two already-passing terminal-preservation checks.

Local verification:

- `uv run pytest tests/test_tasks_demo.py tests/test_task_authority.py -q`: 67 pass.
- `just check`: Ruff and mypy pass; Python suite 349 pass; Node suite 77 pass,
  one failure in `leftover guarded processes are stopped` because sandboxed
  process inspection cannot find the spawned process (actual `[]`). Full command
  stops before CLI/docs.
- Separately, `just cli-test`: 447 pass. `just docs-build`: succeeds with three
  pre-existing missing-reference warnings. `git diff --check`: passes.
- `npm --prefix shells/electron ci`: succeeds.
- `just packaged-smoke`: backend staging succeeds, then Electron aborts with
  SIGABRT / exit 134 before UI boot. Required smoke remains blocked.
- Opus 5.5 high review round 1: PROVIDER_ERROR, no verdict, no findings assessed.
  Exact provider diagnostic: OAuth session expired and could not be refreshed.
  Do not treat this failed review as clean.

Review artifacts and check logs are in the workspace parent (not committed):
`review-b19-1/`, `b19-check.log`, `b19-before.log`, `b19-cli.log`,
`b19-docs.log`, `b19-smoke.log`. Review result records the baseline snapshot.

Resume after Claude authentication repair: fetch and re-verify origin/main,
rebase if moved, rerun local checks in an environment supporting process
inspection and Electron startup. Run a fresh whole-bundle review using the
installed `claude-review-loop` with `--model claude-opus-5-5 --effort high`, a
fresh run directory, and the B19 scope and validation context. Fix/re-review
under the owner's convergence/4-round rules. Remove this parking note before
merging. Merge only after required local checks and review pass; fetch/rebase
immediately before merge, then run full local checks after merge before pushing
only main and verify with `git ls-remote`. Never rely on or invoke Actions.

## B20: verified present on trunk, not implemented

Continue only after B19 is resolved, in this order:

1. `dds-first-run-seed-concurrent-openers`: base/development seeding checks
   before inserting, inside a deferred SQLite transaction. Use unique marker
   arbitration and SQLite-safe transaction ownership; rollback the complete seed.
   Regressions must use two file-backed SQLite processes under base settings,
   repeat under packaged IMMEDIATE settings, and preserve user rows.
2. `dds-task-polling-bounded-history`: list/status load all demo rows and perform
   per-active-row backend lookups. Bound visible terminal history and bulk-load
   active backend states while preserving every pending/running row. Use
   thousands of synthetic rows, bounded query-count assertions, and fresh
   completion coverage; document retention/pagination.

Re-verify both against then-current trunk before editing. Read the full report
slice descriptions and validation notes. Keep synthetic fixtures portable.
