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

test("owned POSIX group is killed even when its leader exits after TERM", async () => {
  const signals = [];
  const target = child(() => assert.fail("must signal the owned group"));
  target.desktopProcessGroup = true;
  const killGroup = (pid, signal) => {
    signals.push([pid, signal]);
    if (signal === "SIGTERM") {
      target.signalCode = signal;
      target.emit("exit", null, signal);
    }
  };
  assert.equal(await stopManagedProcess(target, { platform: "darwin", killGroup }), true);
  assert.deepEqual(signals, [[-123, "SIGTERM"], [-123, "SIGKILL"]]);
});

test("backend launch owns a separate POSIX group", { skip: process.platform === "win32" }, async () => {
  const { spawnManagedProcess } = require("./managed-process.cjs");
  const target = spawnManagedProcess({
    command: process.execPath, args: ["-e", "setInterval(() => {}, 1000)"], cwd: process.cwd()
  }, process.env);
  try {
    assert.equal(target.desktopProcessGroup, true);
    assert.equal(await stopManagedProcess(target), true);
  } finally {
    if (target.exitCode == null && target.signalCode == null) target.kill("SIGKILL");
  }
});

test("normal POSIX shutdown retires a real TERM-resistant descendant", {
  skip: process.platform === "win32", timeout: 15000
}, async () => {
  const { once } = require("node:events");
  const fs = require("node:fs");
  const { spawnManagedProcess } = require("./managed-process.cjs");
  const target = spawnManagedProcess({
    command: process.execPath,
    args: ["-e", `
      const { spawn } = require("node:child_process");
      spawn(process.execPath, ["-e", 'process.on("SIGTERM", () => {}); console.log(process.pid); setInterval(() => {}, 1000)'],
        { stdio: ["ignore", "inherit", "inherit"] });
      setInterval(() => {}, 1000);
    `], cwd: process.cwd()
  }, process.env);
  let descendant;
  const running = pid => {
    try { process.kill(pid, 0); } catch (error) {
      if (error.code === "ESRCH") return false;
      throw error;
    }
    if (process.platform === "linux") {
      try { return !fs.readFileSync(`/proc/${pid}/stat`, "utf8").split(") ")[1].startsWith("Z"); }
      catch (error) { if (error.code === "ENOENT") return false; throw error; }
    }
    return true;
  };
  try {
    const [output] = await once(target.stdout, "data");
    descendant = Number(String(output).trim());
    assert.ok(descendant > 0);
    assert.equal(await stopManagedProcess(target), true);
    const deadline = Date.now() + 5000;
    while (running(descendant) && Date.now() < deadline) {
      await new Promise(resolve => setTimeout(resolve, 25));
    }
    assert.equal(running(descendant), false);
  } finally {
    try { process.kill(-target.pid, "SIGKILL"); } catch (error) {
      if (error.code !== "ESRCH" && error.code !== "EPERM") throw error;
    }
  }
});

test("leader exit retires the owned POSIX group once and tolerates an empty group", async () => {
  const { spawnManagedProcess } = require("./managed-process.cjs");
  const signals = [];
  const killGroup = (pid, signal) => {
    signals.push([pid, signal]);
    throw Object.assign(new Error("gone"), { code: "ESRCH" });
  };
  const target = spawnManagedProcess({
    command: process.execPath, args: ["-e", ""], cwd: process.cwd()
  }, process.env, { platform: "darwin", killGroup });
  await require("node:events").once(target, "exit");
  assert.deepEqual(signals, [[-target.pid, "SIGKILL"]]);
  // Already exited: stopping is confirmed without signalling again.
  assert.equal(await stopManagedProcess(target, { killGroup }), true);
  assert.equal(signals.length, 1);
});

test("a leader that exits on its own retires its TERM-resistant descendant", {
  skip: process.platform === "win32", timeout: 15000
}, async () => {
  const { once } = require("node:events");
  const { spawnManagedProcess } = require("./managed-process.cjs");
  const target = spawnManagedProcess({
    command: process.execPath,
    args: ["-e", `
      const { spawn } = require("node:child_process");
      const descendant = spawn(process.execPath, ["-e", 'process.on("SIGTERM", () => {}); setInterval(() => {}, 1000)'],
        { stdio: "ignore" });
      console.log(descendant.pid);
      setTimeout(() => process.exit(0), 200);
    `], cwd: process.cwd()
  }, process.env);
  let descendant;
  const running = pid => {
    try { process.kill(pid, 0); return true; } catch (error) {
      if (error.code === "ESRCH") return false;
      throw error;
    }
  };
  try {
    const [output] = await once(target.stdout, "data");
    descendant = Number(String(output).trim());
    assert.ok(descendant > 0);
    await once(target, "exit");
    const deadline = Date.now() + 5000;
    while (running(descendant) && Date.now() < deadline) {
      await new Promise(resolve => setTimeout(resolve, 25));
    }
    assert.equal(running(descendant), false);
  } finally {
    if (descendant && running(descendant)) process.kill(descendant, "SIGKILL");
  }
});

test("group stop tolerates Darwin zombie-only EPERM but surfaces other errors", async () => {
  const fail = code => () => { throw Object.assign(new Error(code), { code }); };
  const exited = () => {
    const target = child();
    target.desktopProcessGroup = true;
    target.stdin = { destroy() {} };
    return target;
  };
  assert.equal(await stopManagedProcess(exited(), {
    platform: "darwin", killGroup: fail("EPERM"), graceMs: 5, reapMs: 5
  }), false);
  await assert.rejects(stopManagedProcess(exited(), {
    platform: "darwin", killGroup: fail("EINVAL"), graceMs: 5, reapMs: 5
  }), { code: "EINVAL" });
});
