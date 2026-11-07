// Execute the complete entry point with Electron's public API substituted.
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { createRequire } = require("node:module");
const { EventEmitter } = require("node:events");

function loadMain(overrides = {}, globals = {}) {
  const filename = path.join(__dirname, "..", "main.js");
  const realRequire = createRequire(filename);
  const app = Object.assign(new EventEmitter(), {
    requestSingleInstanceLock: () => true,
    whenReady: () => new Promise(() => {})
  });
  const context = vm.createContext({
    require: (name) => {
      if (Object.hasOwn(overrides, name)) return overrides[name];
      if (name === "electron") return { app, ipcMain: { handle() {} } };
      if (name === "electron-updater") return { autoUpdater: {} };
      return realRequire(name);
    },
    __dirname: path.dirname(filename),
    process, console, URL, Buffer, performance, setTimeout, clearTimeout,
    ...globals
  });
  vm.runInContext(fs.readFileSync(filename, "utf8"), context, { filename });
  return vm.runInContext(`({ getHealthStatus, getActivity, waitForDjango,
    bootstrap, registerDesktopAuthHeaderInjection, registerWindowNavigationGuards })`, context);
}
module.exports = { loadMain };
