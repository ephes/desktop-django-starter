# Changelog

## Unreleased

- Paginate My Ponies in stable 20-row database pages and retain return navigation.
- Atomically limit active routines to 16 across desktop windows, returning a
  retryable refusal at capacity without orphan queue entries.

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
