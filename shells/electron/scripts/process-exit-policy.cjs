function shouldShowManagedProcessExitDialog({
  quitting = false,
  spawnFailed = false,
  updateInstallInProgress = false,
  intentionalStopRequested = false
} = {}) {
  return !quitting && !spawnFailed && !updateInstallInProgress && !intentionalStopRequested;
}

module.exports = {
  shouldShowManagedProcessExitDialog
};
