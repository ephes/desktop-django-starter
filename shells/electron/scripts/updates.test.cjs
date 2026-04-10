const test = require("node:test");
const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");

const {
  createElectronUpdateController,
  getErrorMessage,
  getUpdateSupport,
  getVersionLabel
} = require("./updates.cjs");

class FakeAutoUpdater extends EventEmitter {
  constructor() {
    super();
    this.autoDownload = true;
    this.autoInstallOnAppQuit = true;
    this.checks = 0;
    this.downloads = 0;
    this.installs = 0;
    this.logger = undefined;
    this.checkResult = { updateInfo: { version: "1.2.3" } };
    this.checkPromise = null;
    this.downloadResult = ["/tmp/update"];
    this.downloadPromise = null;
  }

  async checkForUpdates() {
    this.checks += 1;
    if (this.checkPromise) {
      return this.checkPromise;
    }
    return this.checkResult;
  }

  async downloadUpdate() {
    this.downloads += 1;
    if (this.downloadPromise) {
      return this.downloadPromise;
    }
    return this.downloadResult;
  }

  quitAndInstall() {
    this.installs += 1;
  }
}

function createDialog(responses = []) {
  return {
    boxes: [],
    errors: [],
    async showMessageBox(options) {
      this.boxes.push(options);
      return responses.shift() || { response: 0 };
    },
    showErrorBox(title, message) {
      this.errors.push({ title, message });
    }
  };
}

function createApp(isPackaged = true) {
  return {
    isPackaged,
    getVersion() {
      return "0.1.0";
    }
  };
}

function waitForAsyncEventHandlers() {
  return new Promise((resolve) => setImmediate(resolve));
}

function neverSettles() {
  return new Promise(() => {});
}

test("getUpdateSupport disables updates outside packaged releases", () => {
  assert.deepEqual(
    getUpdateSupport({ app: createApp(false), platform: "darwin", env: {} }),
    {
      supported: false,
      reason: "Update checks are only available from a packaged desktop release."
    }
  );
});

test("getUpdateSupport respects explicit disable flag", () => {
  assert.deepEqual(
    getUpdateSupport({
      app: createApp(true),
      platform: "darwin",
      env: { DESKTOP_DJANGO_DISABLE_AUTO_UPDATE: "1" }
    }),
    {
      supported: false,
      reason: "Update checks are disabled by DESKTOP_DJANGO_DISABLE_AUTO_UPDATE."
    }
  );
});

test("getVersionLabel and getErrorMessage normalize updater values", () => {
  assert.equal(getVersionLabel({ version: " 1.2.3 " }), "1.2.3");
  assert.equal(getVersionLabel({}), "the latest version");
  assert.equal(getErrorMessage(new Error("network failed")), "network failed");
  assert.equal(getErrorMessage("plain failure"), "plain failure");
  assert.equal(getErrorMessage(null), "Unknown update failure.");
});

test("update controller keeps checks harmless when unsupported", async () => {
  const updater = new FakeAutoUpdater();
  const dialog = createDialog();
  const controller = createElectronUpdateController({
    app: createApp(false),
    autoUpdater: updater,
    dialog,
    logger: null,
    platform: "darwin",
    env: {}
  });

  await controller.checkForUpdates();

  assert.equal(updater.autoDownload, false);
  assert.equal(updater.autoInstallOnAppQuit, false);
  assert.equal(updater.checks, 0);
  assert.equal(dialog.boxes[0].title, "Updates Unavailable");
});

test("update controller blocks a second check while a check is running", async () => {
  const updater = new FakeAutoUpdater();
  updater.checkPromise = neverSettles();
  const dialog = createDialog();
  const controller = createElectronUpdateController({
    app: createApp(true),
    autoUpdater: updater,
    dialog,
    logger: null,
    platform: "darwin",
    env: {}
  });

  controller.checkForUpdates();
  await waitForAsyncEventHandlers();
  await controller.checkForUpdates();

  assert.equal(updater.checks, 1);
  assert.equal(dialog.boxes[0].title, "Update Check Already Running");
});

test("update controller blocks a new check while a download is running", async () => {
  const updater = new FakeAutoUpdater();
  updater.downloadPromise = neverSettles();
  const dialog = createDialog([{ response: 0 }]);
  const controller = createElectronUpdateController({
    app: createApp(true),
    autoUpdater: updater,
    dialog,
    logger: null,
    platform: "darwin",
    env: {}
  });

  updater.emit("update-available", { version: "1.2.3" });
  await waitForAsyncEventHandlers();
  await controller.checkForUpdates();

  assert.equal(updater.downloads, 1);
  assert.equal(updater.checks, 0);
  assert.equal(dialog.boxes[1].title, "Update Check Already Running");
});

test("update controller reports when no update is available", async () => {
  const updater = new FakeAutoUpdater();
  const dialog = createDialog();
  createElectronUpdateController({
    app: createApp(true),
    autoUpdater: updater,
    dialog,
    logger: null,
    platform: "darwin",
    env: {}
  });

  updater.emit("update-not-available", { version: "0.1.0" });
  await waitForAsyncEventHandlers();

  assert.equal(dialog.boxes[0].title, "No Update Available");
  assert.equal(dialog.boxes[0].detail, "Current version: 0.1.0");
});

test("update controller asks before downloading an available update", async () => {
  const updater = new FakeAutoUpdater();
  const dialog = createDialog([{ response: 0 }]);
  createElectronUpdateController({
    app: createApp(true),
    autoUpdater: updater,
    dialog,
    logger: null,
    platform: "darwin",
    env: {}
  });

  updater.emit("update-available", { version: "1.2.3" });
  await waitForAsyncEventHandlers();

  assert.equal(dialog.boxes[0].title, "Update Available");
  assert.equal(updater.downloads, 1);
});

test("update controller does not download when the user cancels", async () => {
  const updater = new FakeAutoUpdater();
  const dialog = createDialog([{ response: 1 }]);
  createElectronUpdateController({
    app: createApp(true),
    autoUpdater: updater,
    dialog,
    logger: null,
    platform: "darwin",
    env: {}
  });

  updater.emit("update-available", { version: "1.2.3" });
  await waitForAsyncEventHandlers();

  assert.equal(updater.downloads, 0);
});

test("update controller stops the backend before installing a downloaded update", async () => {
  const updater = new FakeAutoUpdater();
  const dialog = createDialog([{ response: 0 }]);
  let prepared = false;
  createElectronUpdateController({
    app: createApp(true),
    autoUpdater: updater,
    dialog,
    logger: null,
    platform: "darwin",
    env: {},
    beforeInstall: async () => {
      prepared = true;
    }
  });

  updater.emit("update-downloaded", { version: "1.2.3" });
  await waitForAsyncEventHandlers();

  assert.equal(dialog.boxes[0].title, "Update Downloaded");
  assert.equal(prepared, true);
  assert.equal(updater.installs, 1);
});

test("update controller prompts to install on a later check after an update is downloaded", async () => {
  const updater = new FakeAutoUpdater();
  const dialog = createDialog([{ response: 1 }, { response: 1 }]);
  const controller = createElectronUpdateController({
    app: createApp(true),
    autoUpdater: updater,
    dialog,
    logger: null,
    platform: "darwin",
    env: {}
  });

  updater.emit("update-downloaded", { version: "1.2.3" });
  await waitForAsyncEventHandlers();
  await controller.checkForUpdates();

  assert.equal(updater.checks, 0);
  assert.equal(dialog.boxes[0].title, "Update Downloaded");
  assert.equal(dialog.boxes[1].title, "Update Downloaded");
});

test("update controller reports download errors and resets busy state", async () => {
  const updater = new FakeAutoUpdater();
  updater.downloadPromise = neverSettles();
  const dialog = createDialog([{ response: 0 }]);
  const controller = createElectronUpdateController({
    app: createApp(true),
    autoUpdater: updater,
    dialog,
    logger: null,
    platform: "darwin",
    env: {}
  });

  updater.emit("update-available", { version: "1.2.3" });
  await waitForAsyncEventHandlers();
  updater.emit("error", new Error("download failed"));
  await waitForAsyncEventHandlers();

  assert.equal(dialog.errors[0].title, "Update Download Failed");
  assert.equal(dialog.errors[0].message, "download failed");
  assert.deepEqual(controller.getState(), {
    checking: false,
    downloading: false,
    downloaded: false
  });
});

test("update controller reports check errors and resets busy state", async () => {
  const updater = new FakeAutoUpdater();
  updater.checkPromise = neverSettles();
  const dialog = createDialog();
  const controller = createElectronUpdateController({
    app: createApp(true),
    autoUpdater: updater,
    dialog,
    logger: null,
    platform: "darwin",
    env: {}
  });

  controller.checkForUpdates();
  await waitForAsyncEventHandlers();
  updater.emit("error", new Error("check failed"));
  await waitForAsyncEventHandlers();

  assert.equal(dialog.errors[0].title, "Update Check Failed");
  assert.equal(dialog.errors[0].message, "check failed");
  assert.deepEqual(controller.getState(), {
    checking: false,
    downloading: false,
    downloaded: false
  });
});
