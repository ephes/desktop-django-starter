const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { createRequire } = require("node:module");
const vm = require("node:vm");
const test = require("node:test");

function runtime(dir = fs.mkdtempSync(path.join(os.tmpdir(), "dds-runtime-")), cleanup) {
  const app = Object.assign(new EventEmitter(), {
    requestSingleInstanceLock: () => true,
    whenReady: () => new Promise(() => {}),
    getPath: () => dir,
    getVersion: () => "0.1.6",
    exit: code => { app.exitStatus = code; },
    quit: () => {}
  });
  const errors = [];
  const filename = path.join(__dirname, "..", "main.js");
  const actualRequire = createRequire(filename);
  const context = {
    require: name => name === "electron" ? {
      app, ipcMain: { handle() {} }, dialog: { showErrorBox: (...args) => errors.push(args) }
    } : name === "./scripts/orphan-processes.cjs" && cleanup ? {
      ...actualRequire(name), stopOrphanedBackendProcesses: cleanup
    } : name === "electron-updater" ? { autoUpdater: {} } : actualRequire(name),
    __dirname: path.dirname(filename), process, console, setTimeout, clearTimeout, URL
  };
  vm.runInNewContext(fs.readFileSync(filename, "utf8") + `
    globalThis.control = {
      bootstrap, prepareForUpdateInstall,
      children: (worker, django) => { taskWorkerProcess = worker; djangoProcess = django; },
      session: value => { shellSession = value; shellRecoveryConfirmed = true; },
      recover: error => recoverFailedUpdateInstall(error),
      state: () => ({ currentAppUrl, updateInstallInProgress, quitting, shellSession }),
      stops: (worker, django) => { stopTaskWorker = worker; stopDjango = django; },
      startup: (manage, packaged = false) => {
        getOpenPort = async () => 12345;
        getRuntimeMode = () => packaged ? "packaged" : "development";
        validatePackagedBackendRoot = () => {};
        createSplashWindow = () => {};
        runManageCommand = manage;
        startDjangoServer = manage;
        startTaskWorker = manage;
        waitForDjango = async () => {};
        createWindow = () => {};
      },
      visible: win => { mainWindow = win; currentAppUrl = 'http://127.0.0.1:1'; }
    };`, context, { filename });
  return { app, errors, control: context.control };
}

module.exports = { runtime };

test("unreadable marker refuses bootstrap before any backend command", async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "dds-marker-"));
  fs.writeFileSync(path.join(dir, "desktop-shell-session.json"), "corrupt");
  const { control } = runtime(dir);
  let starts = 0;
  control.startup(async () => { starts++; });
  await assert.rejects(control.bootstrap(), /session marker/i);
  assert.equal(starts, 0);
  assert.equal(control.state().shellSession, null);
});

for (const failure of ["worker", "django", "installer"]) {
  test(`failed update handoff at ${failure} hides dead UI and exits for restart`, async () => {
    const { app, control, errors } = runtime();
    let hidden = false;
    control.visible({ isDestroyed: () => false, hide: () => { hidden = true; } });
    const stops = [];
    control.stops(async () => { stops.push("worker"); if (failure === "worker") throw Error("worker failed"); },
      async () => { stops.push("django"); if (failure === "django") throw Error("django failed"); });
    try { await control.prepareForUpdateInstall(); } catch (_) {}
    await control.recover(Error(`${failure} failed`));
    assert.ok(stops.includes("django"));
    assert.equal(hidden, true);
    assert.equal(control.state().currentAppUrl, null);
    assert.equal(control.state().updateInstallInProgress, false);
    assert.equal(app.exitStatus, 1);
    assert.match(errors.at(-1)[1], /restart/i);
  });
}

test("shutdown keeps dirty marker until both child exits are confirmed", async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "dds-retirement-"));
  const { beginSession, readSession } = require("./orphan-processes.cjs");
  const session = beginSession(dir).session;
  const { app, control } = runtime(dir);
  control.session(session);
  let release;
  const stopped = new Promise(resolve => { release = resolve; });
  control.stops(() => stopped, async () => {});
  const shutdown = app.listeners("will-quit")[0]({ preventDefault() {} });
  assert.equal(readSession(dir).running, true);
  release();
  await shutdown;
  assert.equal(readSession(dir).running, false);
});

test("unconfirmed shutdown attempts both children and preserves dirty recovery", async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "dds-unresolved-"));
  const { beginSession, readSession } = require("./orphan-processes.cjs");
  const { app, control } = runtime(dir);
  control.session(beginSession(dir).session);
  let djangoStop = false;
  control.stops(async () => { throw Error("original worker failure"); }, async () => { djangoStop = true; });
  await app.listeners("will-quit")[0]({ preventDefault() {} });
  assert.equal(djangoStop, true);
  assert.equal(app.exitStatus, 1);
  assert.equal(readSession(dir).running, true);
  assert.equal(beginSession(dir).previousRunWasUnclean, true);
});

for (const outcome of ["inventory unavailable", "exit unconfirmed"]) {
  test(`unknown recovery (${outcome}) blocks all backend starts and keeps dirty evidence on quit`, async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "dds-recovery-"));
    const { beginSession, readSession } = require("./orphan-processes.cjs");
    const previous = beginSession(dir).session;
    const { app, control } = runtime(dir, async () => ({ status: "unknown", detail: outcome }));
    let starts = 0;
    control.startup(async () => { starts++; });
    await assert.rejects(control.bootstrap(), new RegExp(outcome));
    assert.equal(starts, 0);
    await app.listeners("will-quit")[0]({ preventDefault() {} });
    assert.equal(readSession(dir).running, true);
    assert.equal(readSession(dir).app_key, previous.app_key);
  });
}

for (const previous of ["absent", "clean", "dirty"]) {
  test(`${previous} session with confirmed recovery reaches normal backend startup`, async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "dds-confirmed-"));
    const { beginSession, endSession } = require("./orphan-processes.cjs");
    if (previous !== "absent") {
      const session = beginSession(dir).session;
      if (previous === "clean") endSession(dir, session);
    }
    let cleanups = 0;
    const { control } = runtime(dir, async () => { cleanups++; return { status: "confirmed", pids: [] }; });
    let starts = 0;
    control.startup(async () => { starts++; });
    await control.bootstrap();
    assert.equal(starts, 3); // migrate, Django, worker
    assert.equal(cleanups, previous === "dirty" ? 1 : 0);
  });
}

test("failed shutdown preserves the original first error while attempting both stops", async () => {
  const { control } = runtime();
  const original = Error("worker original");
  let djangoStopped = false;
  control.stops(async () => { throw original; }, async () => { djangoStopped = true; throw Error("django later"); });
  await assert.rejects(control.prepareForUpdateInstall(), error => error === original);
  assert.equal(djangoStopped, true);
});

test("actual shutdown never marks a signal-acknowledging child as retired", async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "dds-signal-only-"));
  const { beginSession, readSession } = require("./orphan-processes.cjs");
  const { app, control } = runtime(dir);
  control.session(beginSession(dir).session);
  const signals = [];
  const child = Object.assign(new EventEmitter(), {
    pid: 123, killed: true, exitCode: null, signalCode: null,
    kill: signal => { signals.push(signal); return true; }
  });
  control.children(child, null);
  await app.listeners("will-quit")[0]({ preventDefault() {} });
  assert.deepEqual(signals, ["SIGTERM", "SIGKILL"]);
  assert.equal(readSession(dir).running, true);
  assert.equal(app.exitStatus, 1);
});

function packagedFixture(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "dds-first-run-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const state = path.join(dir, "state", "0.1.6");
  function writeMigratedState(copiedFrom) {
    fs.mkdirSync(state, { recursive: true });
    fs.writeFileSync(path.join(state, "state.json"), JSON.stringify({ copied_from: copiedFrom }));
    fs.closeSync(fs.openSync(path.join(state, "app.sqlite3"), "a"));
  }
  async function launch(manage) {
    const { control } = runtime(dir, async () => ({ status: "confirmed", pids: [] }));
    control.startup(async args => { if (Array.isArray(args)) await manage(args[0]); }, true);
    await control.bootstrap();
  }
  return { launch, writeMigratedState };
}

test("packaged startup retries interrupted migration and seeding, then retires the pending seed", async t => {
  const { launch, writeMigratedState } = packagedFixture(t);
  await assert.rejects(launch(async command => {
    assert.equal(command, "migrate");
    writeMigratedState(null);
    throw Error("interrupted after migration");
  }), /interrupted after migration/);

  const attempts = [];
  await assert.rejects(launch(async command => {
    attempts.push(command);
    if (command === "seed_demo_content") throw Error("seed failed");
  }), /seed failed/);
  await launch(async command => { attempts.push(command); });
  // An intentionally emptied database still exists on the next launch.
  await launch(async command => { attempts.push(command); });
  assert.deepEqual(attempts, [
    "migrate", "seed_demo_content", "migrate", "seed_demo_content", "migrate"
  ]);
});

test("packaged startup leaves existing and copied legacy databases without demo content", async t => {
  const existing = packagedFixture(t);
  existing.writeMigratedState(null);
  await existing.launch(async command => { assert.equal(command, "migrate"); });

  for (const predecessor of ["legacy", "0.1.5"]) {
    const copied = packagedFixture(t);
    await copied.launch(async command => {
      assert.equal(command, "migrate");
      copied.writeMigratedState(predecessor);
    });
  }
});
