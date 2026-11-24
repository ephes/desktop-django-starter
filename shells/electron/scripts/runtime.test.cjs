const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { createRequire } = require("node:module");
const vm = require("node:vm");
const test = require("node:test");

const inStarter = path.basename(path.resolve(__dirname, "../..")) === "shells";
const recoveryCommands = inStarter ? ["recover_stale_routines"] : [];

function runtime(dir = fs.mkdtempSync(path.join(os.tmpdir(), "dds-runtime-")), cleanup, overrides = {}) {
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
      app, ipcMain: { handle() {} }, dialog: { showErrorBox: (...args) => errors.push(args) }, ...overrides.electron
    } : name === "./scripts/orphan-processes.cjs" && cleanup ? {
      ...actualRequire(name), stopOrphanedBackendProcesses: cleanup
    } : name === "electron-updater" ? { autoUpdater: {} } : overrides[name] ?? actualRequire(name),
    __dirname: path.dirname(filename), process, console: overrides.console ?? console,
    setTimeout, clearTimeout, URL, AbortController
  };
  vm.runInNewContext(fs.readFileSync(filename, "utf8") + `
    globalThis.control = {
      bootstrap, prepareForUpdateInstall,
      activity: fetch => { getActivity = fetch; },
      children: (worker, django) => { taskWorkerProcess = worker; djangoProcess = django; },
      session: value => { shellSession = value; shellRecoveryConfirmed = true; },
      recover: error => recoverFailedUpdateInstall(error),
      state: () => ({ currentAppUrl, updateInstallInProgress, quitting, shellSession }),
      stops: (worker, django) => { stopTaskWorker = worker; stopDjango = django; },
      stubWindows: open => {
        getOpenPort = async () => 12345;
        getRuntimeMode = () => "development";
        createSplashWindow = () => {};
        createWindow = open;
      },
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

function requestBeforeQuit(app) {
  let deferred = false;
  app.emit("before-quit", { preventDefault: () => { deferred = true; } });
  return deferred;
}

test("a rejected native quit dialog is logged once and the next app quit can succeed", async () => {
  const warnings = [];
  const dialogError = new Error("native dialog unavailable");
  let prompts = 0;
  const { app, control } = runtime(os.tmpdir(), undefined, {
    console: { warn: (...args) => warnings.push(args) },
    electron: {
      dialog: {
        showMessageBox: async () => {
          if (++prompts === 1) throw dialogError;
          return { response: 0 };
        }
      }
    }
  });
  control.visible(null);
  control.activity(async () => ({ running_tasks: 1 }));
  let quits = 0;
  app.quit = () => {
    quits++;
    assert.equal(requestBeforeQuit(app), false);
  };

  assert.equal(requestBeforeQuit(app), true);
  await new Promise(setImmediate);
  assert.equal(quits, 0);
  assert.equal(control.state().quitting, false);
  assert.deepEqual(warnings, [["Quit confirmation failed:", dialogError]]);

  assert.equal(requestBeforeQuit(app), true);
  await new Promise(setImmediate);
  assert.equal(prompts, 2);
  assert.equal(quits, 1);
  assert.equal(control.state().quitting, true);
  assert.equal(warnings.length, 1);
});

test("Django exit cancels a pending startup probe before the worker or window starts", async t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "dds-backend-exit-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const django = new EventEmitter();
  django.stdout = new EventEmitter();
  django.stderr = new EventEmitter();
  const commands = [];
  let probeCount = 0;
  let probeAborted = false;
  let probeStarted;
  const pendingProbe = new Promise(resolve => { probeStarted = resolve; });
  const { control, errors } = runtime(dir, undefined, {
    "./scripts/managed-process.cjs": {
      spawnManagedProcess: ({ args }) => {
        const command = args[args.findIndex(arg => path.basename(arg) === "manage.py") + 1];
        commands.push(command);
        if (command === "runserver") {
          queueMicrotask(() => django.emit("spawn"));
          return django;
        }
        const child = Object.assign(new EventEmitter(), { stdout: new EventEmitter(), stderr: new EventEmitter() });
        queueMicrotask(() => child.emit("exit", 0));
        return child;
      }
    },
    "node:http": {
      get: (_url, { signal }, respond) => {
        probeCount++;
        const request = Object.assign(new EventEmitter(), { setTimeout() {} });
        signal?.addEventListener("abort", () => {
          probeAborted = true;
          request.emit("error", new Error("Request aborted"));
        }, { once: true });
        probeStarted(respond);
        return request;
      }
    }
  });
  let windowOpened = false;
  control.stubWindows(() => { windowOpened = true; });

  const startup = control.bootstrap();
  const respond = await pendingProbe;
  django.emit("exit", 7, null);
  respond({ resume() {}, statusCode: 200 });

  await assert.rejects(startup, /Django process stopped[\s\S]*Code: 7/);
  assert.equal(probeAborted, true);
  assert.equal(probeCount, 1);
  assert.deepEqual(commands, ["migrate", ...recoveryCommands, "runserver"]);
  assert.equal(windowOpened, false);
  assert.deepEqual(errors, []);
});

test("the renderer shows an app-data folder error only when the native open fails", {
  // Wrapped projects have electron/ at their root and ship their own templates.
  skip: !inStarter && "Requires the starter Django template"
}, async () => {
  const appData = "/synthetic/app-data";
  const paths = [];
  let openError = "No file manager is available.";
  const handlers = new Map();
  const { control } = runtime(appData, undefined, {
    electron: {
      ipcMain: { handle: (channel, handler) => handlers.set(channel, handler) },
      shell: { openPath: async folder => { paths.push(folder); return openError; } }
    }
  });
  control.visible(null);
  const handle = handlers.get("desktop:open-app-data-directory");
  await assert.rejects(handle({ senderFrame: { url: "http://127.0.0.1:2/" } }), /only available to the local Django app/);
  assert.deepEqual(paths, []);

  const window = {};
  const trustedEvent = { senderFrame: { url: "http://127.0.0.1:1/" } };
  const preload = fs.readFileSync(path.join(__dirname, "..", "preload.cjs"), "utf8");
  vm.runInNewContext(preload, {
    require: () => ({
      contextBridge: { exposeInMainWorld: (name, api) => { window[name] = api; } },
      ipcRenderer: {
        invoke: async channel => {
          try {
            return await handlers.get(channel)(trustedEvent);
          } catch (error) {
            // IPC delivers a new Error in the renderer's realm.
            throw new Error(error.message);
          }
        }
      }
    })
  });

  let click;
  const button = { hidden: true, addEventListener: (_event, listener) => { click = listener; } };
  const status = {};
  const templatePath = path.join(__dirname, "../../../src/desktop_django_starter/templates/base.html");
  const template = fs.readFileSync(templatePath, "utf8");
  const document = { querySelector: selector => selector === "[data-open-app-data]" ? button : status };
  vm.runInNewContext(template.match(/<script>([\s\S]*?)<\/script>/)[1], { window, document, Error });

  await click();
  assert.match(status.textContent, /No file manager is available/);

  openError = "";
  await click();
  assert.equal(status.textContent, `Opened ${appData}`);
  assert.deepEqual(paths, [appData, appData]);
});

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
    const startsWorker = inStarter || process.env.DESKTOP_DJANGO_ENABLE_TASK_WORKER === "1";
    assert.equal(starts, 2 + recoveryCommands.length + Number(startsWorker));
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
    "migrate", "seed_demo_content",
    "migrate", "seed_demo_content", ...recoveryCommands,
    "migrate", ...recoveryCommands
  ]);
});

test("packaged startup leaves existing and copied legacy databases without demo content", async t => {
  const existing = packagedFixture(t);
  existing.writeMigratedState(null);
  const existingCommands = [];
  await existing.launch(async command => { existingCommands.push(command); });
  assert.deepEqual(existingCommands, ["migrate", ...recoveryCommands]);

  for (const predecessor of ["legacy", "0.1.5"]) {
    const copied = packagedFixture(t);
    const copiedCommands = [];
    await copied.launch(async command => {
      copiedCommands.push(command);
      if (command === "migrate") copied.writeMigratedState(predecessor);
    });
    assert.deepEqual(copiedCommands, ["migrate", ...recoveryCommands]);
  }
});
