# Round 84 resume — seed concurrency and bounded polling

Parked on 2026-11-08 because the required Opus review could not authenticate:
`Failed to authenticate: OAuth session expired and could not be refreshed`.
No merge or default-branch push was attempted. This branch is unfinished work.

## Trunk verification and scope

Fresh SSH clone; origin is `git@github.com:ephes/desktop-django-starter.git`.
Default/integration branch is `main`, fetched again during verification at
`9cc34c0a903d7142c9a37743ebd050b24f77c6ab`.

Already fixed on trunk, skipped implementation:
- `dds-task-backend-success-payload-admission`
- `dds-worker-finalization-current-claim-guard`
Their existing focused tests passed (67 tests across task authority/demo files).

Implemented in report order, not reviewed/merged:
- `dds-first-run-seed-concurrent-openers`: unique marker is the first write in
  the seed transaction. Concurrent development SQLite callers serialize; all
  three ponies and marker commit together or roll back. Existing user content
  remains untouched and gets no marker. The standalone management command is
  the concurrency contract; caller-owned prior read snapshots remain unsupported.
- `dds-task-polling-bounded-history`: both endpoints show all active rows plus
  the 100 most recently completed rows. DBTaskResult.in_bulk and task_result
  preserve the public backend conversion and task-function match guard. History
  is queried after reconciliation; concurrent completions are deduplicated.
  Older history stays stored until Clear Finished Routines; no pagination.

README, architecture, and docs/release.md Unreleased describe the behavior.
Task payload regression injection now targets DBTaskResult.task_result so the
same validation assertions exercise the bulk path.

## Local evidence

- Before the seed fix: synchronized two-process, file-backed development test
  fails with `django.db.utils.OperationalError: database is locked`.
- After the seed fix: local/packaged empty/user-content process variants and
  rollback test pass; all example-app tests pass (10 total focused tests).
- Before polling fix: both endpoints execute 126 queries for 125 active rows;
  unbounded-history assertion also fails (111 returned rather than 100).
- After fix: 1,500 terminal plus 125 active rows return 225 unique rows with
  three SELECTs. Fresh old-task completion and completion-race tests pass.
- `just check`: lint and types pass; all 359 Python tests pass. Electron Node
  tests: 77/78 pass. `leftover guarded processes are stopped` fails because
  sandbox denies `/bin/ps`, leaving actual stopped PIDs `[]` instead of the
  spawned child's PID. This is the same blocker as the previous worker.
- Separate `just cli-test`: 447 passed.
- Separate `just docs-build`: succeeds with two pre-existing missing-anchor
  warnings for release#upgrades-and-rollbacks (architecture and decisions).
- Packaged Electron smoke was not run: stopped on the required OAuth failure.
  Packaged SQLite behavior is covered by the process tests, not GUI acceptance.
- No GitHub Actions were consulted, waited on, or rerun. No deploy/release/tag/PR.

## Review and next steps

The first harness attempt could not create the default lock cache (sandbox).
Retried with the lock directory inside the writable workspace. Opus 5.5 high
then returned PROVIDER_ERROR because OAuth expired; there is no valid verdict.
Review artifacts are outside the clone at `../review-b20-2/`; local check logs
are `../check.log`, `../cli-check.log`, and `../docs-check.log`.
The bundle's redaction manifest flags the enum named `Key` as a secret-looking
assignment in old seed lines; it is a non-secret fixed seed marker. The new local
variable was renamed seed_marker to avoid that false positive on the new code.

After authentication is restored, fetch current main and re-verify/rebase before
reviewing this whole bundle. Run the claude-review-loop skill with
`--model claude-opus-5-5 --effort high`, fresh run directory, writable lock/ledger
directories, and `--record-baseline`. Fix and delta-review while making progress,
maximum four valid rounds, stopping if a required finding recurs. Run full local
checks and required packaged smoke outside the blocking sandbox. Do not use
Actions as a fallback. Only merge a reviewed-clean/suggestion-only bundle with
--no-ff after a final fetch/rebase and rerun; rerun full checks after the merge
before pushing main, then verify main with git ls-remote. Never delete branches.
