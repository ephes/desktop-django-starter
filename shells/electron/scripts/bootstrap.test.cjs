const test = require("node:test");
const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const path = require("node:path");
const { loadMain } = require("./main-test-harness.cjs");

function runtime({ packaged, existing = false, failure, secondInstance = false, unclean = false } = {}) {
  const trace = [];
  const children = [];
  const ipc = {};
  const opened = [];
  const dbPaths = [];
  const session = { app_key: "synthetic-app-key" };
  const invocations = [];
  let releaseMigration;
  let releaseHealth;
  const app = Object.assign(new EventEmitter(), {
    isPackaged: packaged,
    getPath: () => path.resolve("synthetic-app-data"),
    getVersion: () => "1.2.3",
    requestSingleInstanceLock: () => !secondInstance,
    quit: () => trace.push("quit"),
    exit: () => trace.push("exit"),
    whenReady: () => secondInstance ? Promise.resolve() : new Promise(() => {})
  });
  class BrowserWindow extends EventEmitter {
    constructor() {
      super();
      this.webContents = Object.assign(new EventEmitter(), {
        session: { webRequest: { onBeforeSendHeaders() {} } },
        setWindowOpenHandler() {}
      });
    }
    loadFile() { trace.push("splash"); }
    loadURL(url) { trace.push("window"); }
  }
  const main = loadMain({
    electron: { app, BrowserWindow,
      ipcMain: { handle: (name, handler) => { ipc[name] = handler; } },
      shell: { openPath: async (folder) => { opened.push(folder); } }
    },
    "node:net": { createServer: () => Object.assign(new EventEmitter(), {
      listen: (_port, _host, callback) => queueMicrotask(callback),
      address: () => ({ port: 4567 }),
      close: (callback) => callback()
    }) },
    "node:fs": {
      existsSync: (filename) => {
        if (path.basename(filename) !== "app.sqlite3") return true;
        dbPaths.push(filename);
        return existing;
      }
    },
    "./scripts/bundled-python.cjs": {
      getRuntimeManifestPath: (root) => path.join(root, "runtime-manifest.json"),
      resolveBundledPythonExecutable: () => "synthetic-python"
    },
    "./scripts/orphan-processes.cjs": {
      beginSession: () => ({ session, previousRunWasUnclean: unclean }),
      stopOrphanedBackendProcesses: async (key) => {
        assert.equal(key, session.app_key);
        trace.push("orphans");
      },
      endSession: (folder, ended) => {
        assert.equal(folder, app.getPath("userData"));
        assert.equal(ended, session);
        trace.push("session-ended");
      }
    },
    "node:child_process": {
      spawn: (command, args, options) => {
        const operation = args[args.indexOf("manage.py") + 1];
        trace.push(operation);
        invocations.push({ command, args, options });
        const child = Object.assign(new EventEmitter(), {
          stdin: new EventEmitter(), stdout: new EventEmitter(), stderr: new EventEmitter(),
          // Model a child that already exited before application cleanup.
          killed: true
        });
        children.push(child);
        if (operation === "migrate") {
          releaseMigration = () => child.emit("exit", failure === "migrate" ? 1 : 0);
        } else {
          queueMicrotask(() => {
            if (operation === "seed_demo_content") child.emit("exit", failure === "seed" ? 1 : 0);
            else if (operation === failure) child.emit("error", new Error("synthetic spawn failure"));
            else child.emit("spawn");
          });
        }
        return child;
      }
    },
    "node:http": {
      get: (_url, _options, callback) => {
        trace.push("health");
        const request = Object.assign(new EventEmitter(), { setTimeout() {}, destroy() {} });
        releaseHealth = () => {
          if (failure === "health") request.emit("error", new Error("synthetic health failure"));
          else callback({ statusCode: 200, resume() {}, destroy() {} });
        };
        return request;
      }
    }
  }, {
    process: { ...process, resourcesPath: path.resolve("synthetic-resources"), env: { DESKTOP_DJANGO_RUNTIME_MODE: packaged ? "packaged" : "development" } },
    // A failed health exchange exhausts the real poller's elapsed budget.
    Date: { now: () => failure === "health" && releaseHealth ? 1e9 : 0 },
    performance: { now: () => failure === "health" && releaseHealth ? 1e9 : 0 }
  });
  return { main, app, ipc, opened, dbPaths, trace, invocations, releaseMigration: () => releaseMigration(), releaseHealth: () => releaseHealth() };
}

async function until(predicate) {
  for (let i = 0; i < 100; i++) {
    if (predicate()) return;
    await new Promise(setImmediate);
  }
  assert.fail("bootstrap did not reach the expected boundary");
}

for (const [packaged, existing] of [[true, false], [true, true], [false, false]]) {
  test(`bootstrap awaits migration and health (packaged=${packaged}, existing=${existing})`, async () => {
    const r = runtime({ packaged, existing });
    const pending = r.main.bootstrap();
    await until(() => r.trace.includes("migrate"));
    assert.deepEqual(r.trace, ["splash", "migrate"]);
    r.releaseMigration();
    await until(() => r.trace.includes("health"));
    const prefix = ["splash", "migrate", ...(packaged && !existing ? ["seed_demo_content"] : []), "runserver", "health"];
    assert.deepEqual(r.trace, prefix);
    r.releaseHealth();
    await pending;
    assert.deepEqual(r.trace, [...prefix, "db_worker", "window"]);
    assert.deepEqual(r.dbPaths, packaged
      ? [path.join(path.resolve("synthetic-app-data"), "state", "1.2.3", "app.sqlite3")] : []);
    for (const { args, options } of r.invocations) {
      assert.ok(args.includes("--watch-stdin"));
      assert.equal(options.env.DESKTOP_DJANGO_APP_VERSION, "1.2.3");
      assert.equal(options.env.DJANGO_SETTINGS_MODULE, packaged
        ? "desktop_django_starter.settings.packaged" : "desktop_django_starter.settings.local");
    }
  });
}

for (const failure of ["migrate", "seed", "runserver", "health", "db_worker"]) {
  test(`bootstrap stops at ${failure} failure`, async () => {
    const r = runtime({ packaged: true, failure });
    const pending = r.main.bootstrap();
    const rejected = assert.rejects(pending);
    await until(() => r.trace.includes("migrate"));
    r.releaseMigration();
    if (["health", "db_worker"].includes(failure)) {
      await until(() => r.trace.includes("health"));
      r.releaseHealth();
    }
    await rejected;
    const operations = ["splash", "migrate", "seed_demo_content", "runserver", "health", "db_worker"];
    const stop = failure === "seed" ? "seed_demo_content" : failure;
    assert.deepEqual(r.trace, operations.slice(0, operations.indexOf(stop) + 1));
  });
}

test("a second instance quits without reaching bootstrap or session cleanup", async () => {
  const r = runtime({ secondInstance: true });
  await new Promise(setImmediate);
  assert.deepEqual(r.trace, ["quit"]);
  assert.deepEqual(r.invocations, []);
});

test("unclean sessions stop orphans before migration and clean exits end the session", async () => {
  const r = runtime({ unclean: true });
  const pending = r.main.bootstrap();
  await until(() => r.trace.includes("migrate"));
  assert.deepEqual(r.trace, ["splash", "orphans", "migrate"]);
  r.releaseMigration();
  await until(() => r.trace.includes("health"));
  r.releaseHealth();
  await pending;
  let prevented = 0;
  r.app.emit("will-quit", { preventDefault: () => { prevented++; } });
  await until(() => r.trace.includes("exit"));
  assert.equal(prevented, 1);
  assert.deepEqual(r.trace.slice(-2), ["session-ended", "exit"]);
});

test("the registered IPC handler allows only trusted Django frames", async () => {
  const r = runtime();
  const pending = r.main.bootstrap();
  await until(() => r.trace.includes("migrate"));
  r.releaseMigration();
  await until(() => r.trace.includes("health"));
  r.releaseHealth();
  await pending;
  const handler = r.ipc["desktop:open-app-data-directory"];
  for (const url of ["https://foreign.example/", "http://127.0.0.1:9999/", "file:///synthetic.html"]) {
    await assert.rejects(handler({ senderFrame: { url } }), /only available/);
  }
  assert.deepEqual(r.opened, []);
  const result = await handler({ senderFrame: { url: "http://127.0.0.1:4567/tasks/" } });
  assert.equal(result.path, path.resolve("synthetic-app-data"));
  assert.deepEqual(r.opened, [result.path]);
});
