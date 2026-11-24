// Asks before quitting while background tasks are still running.
//
// The window `close` and app `before-quit` handlers share one activity check,
// one confirmation and one continuation. A failed activity check allows
// quitting. A failed confirmation dialog cancels the attempt so the user can retry.

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

function createQuitGuard({ fetchActivity, confirmQuit, onConfirmationError, skip = () => false }) {
  let confirmed = false;
  let pending = null;

  async function decide() {
    let activity;
    try {
      activity = await fetchActivity();
    } catch (_error) {
      activity = null;
    }

    const busy = activity
      && ((activity.running_tasks || 0) > 0 || (activity.queued_tasks || 0) > 0);
    if (busy) {
      try {
        if (!(await confirmQuit(describeActivity(activity)))) {
          return false;
        }
      } catch (error) {
        onConfirmationError?.(error);
        return false;
      }
    }

    return true;
  }

  async function finishAttempt(attempt) {
    try {
      const proceed = await decide();
      pending = null;
      if (proceed) {
        confirmed = true;
        if (!skip()) attempt.resume?.();
      }
      return proceed;
    } catch (error) {
      if (pending === attempt) pending = null;
      console.warn("Quit attempt failed:", error);
      return false;
    }
  }

  function pendingAttempt() {
    if (!pending) {
      const attempt = { resume: null, decision: null };
      pending = attempt;
      attempt.decision = finishAttempt(attempt);
    }
    return pending;
  }

  return {
    // Returns true if the native event was deferred. The app quit replaces a
    // pending window close because quitting the app will close its windows.
    defer(event, action, resume) {
      if (skip()) {
        if (pending) pending.resume = null;
        return false;
      }
      if (confirmed) {
        return false;
      }
      event.preventDefault();
      const attempt = pendingAttempt();
      if (attempt.resume === null || action === "app") {
        attempt.resume = resume;
      }
      return true;
    },
    needsCheck() {
      return !confirmed && !skip();
    },
    shouldProceed() {
      if (confirmed || skip()) {
        confirmed = true;
        return Promise.resolve(true);
      }
      return pendingAttempt().decision;
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
