# Changelog

## Unreleased

- Admit native popup dispatch only for safe targets with exact Django-referrer
  evidence from a live trusted app window. Foreign/unknown/suppressed requesters
  cannot open the OS browser; every child window remains denied. Preserve the
  existing navigation, auth-header and IPC boundaries; extend the real iframe
  fixture to cover popup requester admission and trusted outbound links. Set
  `SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"` in base settings
  because Django's default `same-origin` empties the popup referrer Electron
  reports, which would refuse every trusted target-blank outbound link; the
  staged wrap scaffold adds the same setting when the wrapped settings define no
  referrer policy of their own.

- Install both Electron session permission handlers before loading the app. Deny
  renderer capabilities by default, including remote/unknown frames; document a
  narrow opt-in for reviewed capabilities of the live Django main frame. Add a
  real remote-iframe capability and auth-header fixture (`npm --prefix
  shells/electron run test:frames`).

- Add reversible SQLite indexes for active routine polling and bounded terminal
  history ordering, preserving reconciliation and the 100-row history policy.
  Match partial-index predicates in bound ORM queries to avoid full-history scans
  and sorting. Development checkouts need `just migrate`; packaged startup
  applies the migrations before serving.
- Filter shell background-work counts to READY/RUNNING before the existing
  single aggregate snapshot. Add a `tasks_demo`-owned backend status index via
  Django's public schema editor, pinned to django-tasks-db 0.13.0's schema,
  with data-preserving reversal and no dependency edits.

- Reject duplicate JSON member claims in bounded completion and stage-owner
  markers, including nested and escaped names. Retain ambiguous recovery stages
  for inspection and refuse ambiguous published state without modifying it.

- Refuse version-state publication when media file identity, size, mtime or ctime
  changes during copying. Bound reads by each initial file size and preserve the
  predecessor for a stable retry.

- Isolate POSIX backends in owned process groups and forcibly retire descendants
  on shell pipe loss. Electron closes stdin and signals the launch group on
  normal shutdown, and kills the rest of a group as soon as its leader exits
  (crash or one-shot end). Guard SIGTERM/SIGINT retirement lasts only until
  the Django command installs its own handlers, as db_worker does. Add real
  POSIX descendant cleanup and native Windows Job Object acceptance tests.

- Refuse Windows backend startup when required Job Object admission fails,
  and close newly created job handles on configuration or assignment failure.

- Send private/no-store cache policy on every shell-authenticated response and
  refusal, including HTML forms, task JSON and GET/HEAD errors. Development
  without shell authentication retains its existing non-bootstrap behavior.

- Redact every decoded bootstrap token query member from formatted request logs,
  including encoded names/paths, repeated leading slashes, members after a raw
  `#` or quote, duplicate keys and mapping-style log arguments. Unformattable records log their redacted template
  instead of raising.

- Confirm Release All Ponies against a signed whole-stable snapshot under SQLite's
  writer lock. Stale, missing or forged confirmations return 409 and preserve all
  current rows; the modal offers a reload before a fresh confirmation. The list
  page reads its count, rows and digest in one deferred read snapshot that never
  takes SQLite's writer lock.

- Persist the first-run decision when existing content suppresses demo seeding,
  so clearing a legacy stable stays empty after reopening. Failed seed batches
  still roll back completely and can be retried.

- Count queued/running backend work in one statement to avoid false idle reports.
- Read bounded backend traceback previews before reconciliation and publish only
  safe failure categories or known demo messages in routine pages and polls.

- Fence pony edits and releases with signed displayed content revisions, checking
  under SQLite's write lock. Conflicts preserve current data and edit input;
  the release modal offers a fresh confirmation instead of hiding the conflict.

- Paginate My Ponies in stable 20-row database pages and retain return navigation;
  modal and Release All navigation never land on a vanished page.
- Atomically limit active routines to 16 across desktop windows, returning a
  retryable refusal at capacity without orphan queue entries, shown on the page.

- Smoke only the uniquely changed Tauri bundle in the current Cargo target output,
  retaining stale/unrelated artifacts and refusing ambiguous builds. Non-triple
  directories in a shared target dir are skipped, and build output lists only
  bundles written by the current invocation.
- Bound packaged smoke execution and diagnostics, retiring its owned process group
  even when the smoke leader exits with surviving descendants.

- Harden Tauri manifest opening against symlink/FIFO substitution and validate the opened descriptor.
- Always close initialization lock descriptors after unlock failure, preserving primary errors;
  an exception the caller is merely handling no longer hides an unlock failure.

- Preflight all runtime pruning parents before deletion and refuse symlinked trees.
- Reject duplicate runtime-manifest members in Node and Tauri before interpreter selection.

- Bound Electron recovery process tools and revalidate observed backend process
  identity before orphan termination and escalation.
- Preserve unreadable or invalid session markers and refuse backend startup;
  failed update handoffs now leave a clear restart-required state.
- Read session markers through bounded regular-file descriptors and mark sessions
  clean only after both managed children have confirmed exit.
- Publish session markers using exclusively owned private temporaries; refuse
  startup and retain dirty recovery evidence when orphan cleanup is unknown.
- Windows orphan inventory and termination read PowerShell output as UTF-8, so
  non-ASCII command lines (such as user profile paths) still pass the identity
  recheck, and termination waits up to 5 s for several inventory rounds.
