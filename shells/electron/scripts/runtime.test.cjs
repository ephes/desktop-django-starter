const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { createRequire } = require("node:module");
const vm = require("node:vm");
const test = require("node:test");

function runtime(dir = fs.mkdtempSync(path.join(os.tmpdir(), "dds-runtime-"))) {
  const app = Object.assign(new EventEmitter(), {
    requestSingleInstanceLock: () => true,
    whenReady: () => new Promise(() => {}),
    getPath: () => dir,
    exit: code => { app.exitStatus = code; },
    quit: () => {}
  });
  const errors = [];
  const filename = path.join(__dirname, "..", "main.js");
  const actualRequire = createRequire(filename);
  const context = {
    require: name => name === "electron" ? {
      app, ipcMain: { handle() {} }, dialog: { showErrorBox: (...args) => errors.push(args) }
    } : name === "electron-updater" ? { autoUpdater: {} } : actualRequire(name),
    __dirname: path.dirname(filename), process, console, setTimeout, clearTimeout, URL
  };
  vm.runInNewContext(fs.readFileSync(filename, "utf8") + `
    globalThis.control = {
      bootstrap, prepareForUpdateInstall,
      children: (worker, django) => { taskWorkerProcess = worker; djangoProcess = django; },
      session: value => { shellSession = value; },
      recover: error => recoverFailedUpdateInstall(error),
      state: () => ({ currentAppUrl, updateInstallInProgress, quitting, shellSession }),
      stops: (worker, django) => { stopTaskWorker = worker; stopDjango = django; },
      startup: (manage) => {
        getOpenPort = async () => 12345;
        getPackagedDatabasePath = () => null;
        createSplashWindow = () => {};
        runManageCommand = manage;
        startDjangoServer = manage;
        startTaskWorker = manage;
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
  assert.equal(readSession(dir).running, true);
  assert.equal(beginSession(dir).previousRunWasUnclean, true);
});
