// Asks before quitting while background tasks are still running.
//
// main.js calls `shouldProceed()` from the window `close` and app
// `before-quit` handlers. The first call checks Django's /desktop/activity/
// endpoint; if tasks are running or queued, the user is asked. Once the user
// agreed (or nothing was running), later calls during the same quit return
// true immediately, so the user is asked at most once. A failed check never
// keeps the user from quitting.

// Running tasks are interrupted by quitting; queued tasks stay in the
// database and start when the app runs again.
function describeActivity({ running_tasks: running = 0, queued_tasks: queued = 0 }) {
  const plural = (count, noun) => `${count} ${noun}${count === 1 ? "" : "s"}`;
  const parts = [];
  if (running > 0) {
    parts.push(`Quitting now stops ${plural(running, "running background task")}.`);
  }
  if (queued > 0) {
    parts.push(`${plural(queued, "queued task")} will start the next time the app runs.`);
  }
  return parts.join(" ");
}

function createQuitGuard({ fetchActivity, confirmQuit, skip = () => false }) {
  let confirmed = false;
  let pending = null;

  async function decide() {
    if (confirmed || skip()) {
      confirmed = true;
      return true;
    }

    let activity;
    try {
      activity = await fetchActivity();
    } catch (_error) {
      activity = null;
    }

    const busy = activity
      && ((activity.running_tasks || 0) > 0 || (activity.queued_tasks || 0) > 0);
    if (busy && !(await confirmQuit(describeActivity(activity)))) {
      return false;
    }

    confirmed = true;
    return true;
  }

  return {
    // True when a quit must wait for `shouldProceed()`; false when it can
    // continue right away (already confirmed, or checks are skipped).
    needsCheck() {
      return !confirmed && !skip();
    },
    // Resolves true when quitting may continue.
    shouldProceed() {
      if (confirmed || skip()) {
        confirmed = true;
        return Promise.resolve(true);
      }
      if (!pending) {
        pending = decide().finally(() => {
          pending = null;
        });
      }
      return pending;
    },
    isConfirmed() {
      return confirmed;
    }
  };
}

module.exports = {
  createQuitGuard,
  describeActivity
};
