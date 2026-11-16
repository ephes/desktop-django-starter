const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const test = require("node:test");
const { stopManagedProcess } = require("./managed-process.cjs");

function child(kill = () => {}) {
  return Object.assign(new EventEmitter(), {
    pid: 123, exitCode: null, signalCode: null, killed: true,
    kill(signal) { this.killed = true; kill(signal, this); return true; }
  });
}

test("signal delivery alone, including killed=true, never confirms child retirement", async () => {
  const signals = [];
  const process = child(signal => signals.push(signal));
  assert.equal(await stopManagedProcess(process, { platform: "darwin", graceMs: 5, reapMs: 5 }), false);
  assert.deepEqual(signals, ["SIGTERM", "SIGKILL"]);
  assert.equal(process.listenerCount("exit"), 0);
});

test("late exit after KILL confirms retirement exactly once", async () => {
  const process = child((signal, target) => {
    if (signal === "SIGKILL") setTimeout(() => { target.signalCode = signal; target.emit("exit", null, signal); }, 5);
  });
  assert.equal(await stopManagedProcess(process, { platform: "darwin", graceMs: 5, reapMs: 50 }), true);
  assert.equal(process.listenerCount("exit"), 0);
});

test("already-exited children and synchronous exit during signal settle", async () => {
  const exited = child(() => assert.fail("must not signal exited child"));
  exited.exitCode = 0;
  assert.equal(await stopManagedProcess(exited), true);
  assert.equal(await stopManagedProcess(null), true);
  assert.equal(await stopManagedProcess(child((_signal, target) => target.emit("exit", 0))), true);
});

test("Windows taskkill success still requires observing the managed child's exit", async () => {
  const process = child();
  assert.equal(await stopManagedProcess(process, {
    platform: "win32", run: async () => "", reapMs: 5
  }), false);
});
