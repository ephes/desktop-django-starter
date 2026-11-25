# Changelog

## Unreleased

- Require an absolute `target_directory` in Cargo metadata before staging a
  Tauri build. A forwarded `--target-dir` still takes precedence.

- Fail Tauri packaged smoke when the executable's exit is observed at or after
  the monotonic runtime deadline.

- Bound Tauri build Cargo metadata discovery to 60 seconds by default and
  stop before staging when it times out.

- Retire the owned Tauri packaged-smoke process group when the build wrapper
  receives SIGINT or SIGTERM, then return the corresponding interrupt status.

- Validate the Cargo profile name before discovering Tauri build artifacts.

- Measure Tauri packaged-smoke process-group retirement on a monotonic clock.

- Report only new or changed Tauri build bundles and require a single changed
  NSIS installer for the Windows validation checklist.

- Treat wrapper config that disappears before opening as missing and report
  other read failures with the config path.

- Use an absolute `XDG_CONFIG_HOME` for wrapper config on Unix-like systems.
  Fall back to `~/.config/dds/config.toml` for unset, empty, or relative values.

- Cap packaged media migration at 64 directory levels below the media root.
  Deeper trees fail before publication and leave the predecessor available.

- Reject nonfinite numbers in packaged completion and stage-owner JSON markers,
  including nested metadata and exponent overflow.

- Refuse packaged startup when the secret key path is removed or replaced
  during admission. Concurrent first starts still use the published key.

- Preserve the original packaged secret key publication error when temporary
  cleanup also fails. Once a key is published, warn about failed cleanup and
  reuse the published key.

- Refuse Positron startup when the profile lock is not a direct regular file
  or its path changes during acquisition.

- Refuse Tauri packaged startup when the runtime manifest changes during the
  read. A changed manifest produces the existing error without legacy discovery.

- Show a restart dialog and exit when Positron loses its running local server.
  An intentional shutdown closes the listener quietly.

- Clean up the Positron listener and profile lock if the task worker cannot
  start its thread, and show a startup error.

- Release the Positron listener if WSGI setup fails after binding so teardown
  can finish and release the profile lock.

- Retry interrupted first-run demo seeding on the next Positron launch.
  The pending-seed marker is flushed to disk before migration creates the
  database. Existing profiles without a pending seed retain their data,
  including empty stables.

- Verify Node.js 22.12 or newer in `dds doctor` and `dds wrap` preflight
  before launching a wrapping harness. Report a warning in print-only mode.
  Never run a `node` resolved from the current directory or a relative PATH
  entry.

- Flag refused saved OpenAI models in `dds doctor` and show how to select
  an approved model.

- Resume a confirmed Electron quit only once. An app quit takes priority
  when a window close is also pending.

- Keep Electron open when the native quit confirmation fails. Log the error
  and let the user retry.

- Count only work on queues served by the shell worker when deciding whether
  to confirm a quit. Apply the new activity index with `just migrate` in
  development. Packaged shells migrate automatically.

- Recover abandoned demo routines during desktop shell startup after the
  previous worker has stopped. Django setup, management checks and standalone
  worker startup leave active routines alone.

- Reject saved and explicit unapproved OpenAI model selections before Codex
  or Pi launches. Report how to select an approved model.
  `dds init` re-prompts for an unapproved OpenAI model instead of saving or
  keeping it, and `scripts/wrap --run --agent pi` launches
  `openai-codex/gpt-6.2-sol`.

- Default the packaged Pi wrapper to `openai-codex/gpt-6.2-sol` and show that
  model in setup, help and preflight.

- Flush staged CLI assets and their replacement journal before moving the
  previous asset tree. Report when the platform lacks directory sync.

- Flush promoted or restored CLI asset paths before removing the publication
  journal. Retain the work directory until journal removal is durable.

- Restore the previous CLI asset tree when flushing its move into the
  recovery directory fails. Flush read-only staged asset copies on Windows.

- Keep release checksum write and replacement errors visible when staging-file
  cleanup also fails, and report the retained staging filename.

- Refuse to replace a release checksum manifest when an input artifact changes
  during hashing or before publication.

- Validate a new desktop state generation before and after publishing it. An
  invalid staged copy leaves the final version path free for a retry.

- Preserve SQLite backup errors during upgrade cleanup. Attempt to close both
  connections and report a close failure if the backup succeeded.

- Check source media across the SQLite backup during packaged upgrades. Refuse
  publication on detected drift and keep the predecessor available for retry.

- Refuse startup when a packaged secret key changes during reading. Repair
  POSIX key permissions on the verified descriptor after the stability check.

- Show native file-manager errors in the renderer when opening the app data
  folder fails.

- Cancel Electron readiness polling when the managed Django process exits and
  report its exit details through the startup error dialog.

- Clear Finished Routines also retires verified, exclusively owned terminal
  database queue results in the same batches as their routine history.

- Require a backend result to carry the routine's own ID before reconciling it.
  Stale references follow the missing-result recovery policy.

- Preserve the primary desktop state error when closing a guarded POSIX
  directory also fails. A standalone close failure still stops initialization.

- Recheck copied media files before completing the upgrade copy. Detected edits
  to earlier files refuse publication and preserve the predecessor for retry.

- Refuse desktop state publication when source media directory membership
  changes during copying. Preserve the predecessor for retry.

- Recheck the state root and inspected abandoned stage before detaching it for
  removal. Retain stages with uncertain identity for offline inspection and
  remove the empty retirement directory when detaching fails.

- Preserve the retryable routine queue response after rollback if diagnostics fail.
- Fail restored routines with unencodable results or results over 1024 UTF-8
  bytes. Other routines remain visible when polling.
- Restrict single-pony removal to the revision-checked POST form.
- Resume packaged Electron demo seeding after interrupted first-run migration.
  Leave existing and copied databases untouched.

- Abort desktop state upgrades after a short media write and retain the
  previous generation for retry.

- Close desktop state reader descriptors when stream construction fails and
  preserve the original startup error.

- Refuse CLI asset publication when a canonical file changes during staging,
  including same-size edits detected by comparing staged bytes with the
  sources, preserving the previous bundle.

- Recover interrupted CLI asset publication during the next sync or package
  build using the recorded generation under the asset lock.

- Normalize routine completion timestamps to UTC before writing so out-of-range
  payloads fail the affected routine and leave the status poll available.

- Log a safe startup warning when a database failure prevents abandoned-routine
  recovery. The missing routine table before migrations remains expected.

- Fence routine polling updates to the backend ID observed during lookup so
  stale outcomes cannot finalize rebound routines.

- Keep routine status polling available when a concurrently completed routine
  is cleared before reconciliation reloads it.

- Discard inherited Positron port, auth token and app version values so each
  launch uses its own settings and the normal version fallback.

- Validate the shared Python package files before Positron selects a source
  tree, so an incomplete bundle cannot shadow a valid development tree.

- Use the same bounded page numbers for pony form links and success redirects.
  Invalid return pages open the first page, and valid ones clamp to the current
  page count.

- Use a transactional SQLite inventory generation for Release All Ponies.
  List pages and clear confirmations no longer read every pony's content.

- Skip excluded directory trees before scanning them in the Python line counter.

- Prevent caches from reusing desktop quit activity responses.

- Read desktop quit activity from the task writer database when task writes are routed.

- Handle one Positron quit request at a time, starting before the activity check.

- Build CLI wheels and sdists from a snapshot of one validated asset
  generation, even when a concurrent sync publishes during archiving.

- Check the complete bundled asset inventory in `dds doctor` and report up to
  eight missing paths with the total count.

- Serialize CLI asset publication and placeholder capture across concurrent syncs
  with a persistent sibling lock.
- Keep the original CLI asset publication error when rollback or cleanup fails,
  with diagnostics for secondary failures and the retained recovery path.

- Bound local Tauri bundle discovery and report scans, and fingerprint runnable
  bundles incrementally from sorted metadata.

- Give Tauri build smoke execution and process cleanup separate deadlines so a
  timely exit can succeed after bounded cleanup.

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
