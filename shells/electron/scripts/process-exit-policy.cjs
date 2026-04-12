function shouldShowManagedProcessExitDialog({
  quitting = false,
  spawnFailed = false,
  updateInstallInProgress = false
} = {}) {
  return !quitting && !spawnFailed && !updateInstallInProgress;
}

module.exports = {
  shouldShowManagedProcessExitDialog
};
