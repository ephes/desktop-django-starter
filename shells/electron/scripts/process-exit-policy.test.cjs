const test = require("node:test");
const assert = require("node:assert/strict");

const { shouldShowManagedProcessExitDialog } = require("./process-exit-policy.cjs");

test("managed process exits show an error dialog during normal app runtime", () => {
  assert.equal(
    shouldShowManagedProcessExitDialog({
      quitting: false,
      spawnFailed: false,
      updateInstallInProgress: false
    }),
    true
  );
});

test("managed process exits stay quiet during update installation handoff", () => {
  assert.equal(
    shouldShowManagedProcessExitDialog({
      quitting: false,
      spawnFailed: false,
      updateInstallInProgress: true
    }),
    false
  );
});

test("managed process exits stay quiet after Electron explicitly requests a stop", () => {
  assert.equal(
    shouldShowManagedProcessExitDialog({
      quitting: false,
      spawnFailed: false,
      updateInstallInProgress: false,
      intentionalStopRequested: true
    }),
    false
  );
});

test("managed process exits stay quiet while quitting or after spawn failure", () => {
  assert.equal(
    shouldShowManagedProcessExitDialog({
      quitting: true,
      spawnFailed: false,
      updateInstallInProgress: false
    }),
    false
  );
  assert.equal(
    shouldShowManagedProcessExitDialog({
      quitting: false,
      spawnFailed: true,
      updateInstallInProgress: false
    }),
    false
  );
});
