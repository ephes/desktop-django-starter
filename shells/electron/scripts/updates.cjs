const SUPPORTED_UPDATE_PLATFORMS = new Set(["darwin", "win32", "linux"]);

function getUpdateSupport({ app, platform = process.platform, env = process.env } = {}) {
  if (env.DESKTOP_DJANGO_DISABLE_AUTO_UPDATE === "1") {
    return {
      supported: false,
      reason: "Update checks are disabled by DESKTOP_DJANGO_DISABLE_AUTO_UPDATE."
    };
  }

  if (!app || app.isPackaged !== true) {
    return {
      supported: false,
      reason: "Update checks are only available from a packaged desktop release."
    };
  }

  if (!SUPPORTED_UPDATE_PLATFORMS.has(platform)) {
    return {
      supported: false,
      reason: `Update checks are not supported on ${platform}.`
    };
  }

  return { supported: true, reason: "" };
}

function getVersionLabel(info) {
  if (info && typeof info.version === "string" && info.version.trim()) {
    return info.version.trim();
  }

  return "the latest version";
}

function getErrorMessage(error) {
  if (error instanceof Error && error.message) {
    return error.message;
  }

  if (typeof error === "string" && error) {
    return error;
  }

  return "Unknown update failure.";
}

function createElectronUpdateController({
  app,
  autoUpdater,
  dialog,
  logger = console,
  platform = process.platform,
  env = process.env,
  beforeInstall = async () => {}
}) {
  if (!app || !autoUpdater || !dialog) {
    throw new Error("app, autoUpdater, and dialog are required for update checks.");
  }

  const updateLogger = logger || {
    info() {},
    warn() {},
    error() {}
  };
  let checking = false;
  let downloading = false;
  let downloaded = false;
  let lastErrorMessage = null;
  let attempt = null;
  let availablePrompt = null;
  let installTask = null;
  let installStarted = false;

  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = false;
  autoUpdater.logger = logger || null;

  async function showUnsupportedDialog(reason) {
    await dialog.showMessageBox({
      type: "info",
      buttons: ["OK"],
      defaultId: 0,
      title: "Updates Unavailable",
      message: "Update checks are unavailable in this runtime.",
      detail: reason
    });
  }

  function resetErrorState() {
    lastErrorMessage = null;
  }

  function showUpdateError(title, error) {
    const message = getErrorMessage(error);
    if (lastErrorMessage === message) {
      return;
    }

    lastErrorMessage = message;
    dialog.showErrorBox(title, message);
  }

  function promptToInstallDownloadedUpdate() {
    if (installStarted) return Promise.resolve();
    if (installTask) return installTask;
    // Acquire before running any dialog or user hook, including reentrant hooks.
    installTask = Promise.resolve().then(async () => {
      try {
        const result = await dialog.showMessageBox({
          type: "info",
          buttons: ["Restart and Install", "Later"],
          defaultId: 0,
          cancelId: 1,
          title: "Update Downloaded",
          message: "An update is ready to install.",
          detail: "Restart Desktop Django Starter to install the downloaded update."
        });
        if (result.response !== 0) return;
        await beforeInstall();
        autoUpdater.quitAndInstall();
        installStarted = true;
      } catch (error) {
        dialog.showErrorBox("Update Install Failed", getErrorMessage(error));
      } finally {
        installTask = null;
      }
    });
    return installTask;
  }

  async function downloadUpdate(owner) {
    if (attempt !== owner || downloading || downloaded) return;
    downloading = true;
    resetErrorState();
    try {
      await autoUpdater.downloadUpdate();
    } catch (error) {
      if (attempt !== owner) return;
      attempt = null;
      downloading = false;
      showUpdateError("Update Download Failed", error);
    }
  }

  async function checkForUpdates() {
    const support = getUpdateSupport({ app, platform, env });
    if (!support.supported) {
      await showUnsupportedDialog(support.reason);
      return null;
    }

    if (downloaded) {
      await promptToInstallDownloadedUpdate();
      return null;
    }

    if (checking || downloading) {
      await dialog.showMessageBox({
        type: "info",
        buttons: ["OK"],
        defaultId: 0,
        title: "Update Check Already Running",
        message: "An update check is already running.",
        detail: "Wait for the current update check or download to finish."
      });
      return null;
    }

    const owner = {};
    attempt = owner;
    checking = true;
    resetErrorState();
    try {
      const result = await autoUpdater.checkForUpdates();
      if (attempt === owner && !availablePrompt && !downloading) {
        checking = false;
        attempt = null;
      }
      return result;
    } catch (error) {
      if (attempt !== owner) return null;
      attempt = null;
      availablePrompt = null;
      checking = false;
      showUpdateError("Update Check Failed", error);
      return null;
    }
  }

  autoUpdater.on("checking-for-update", () => {
    updateLogger.info("Checking for Electron updates.");
  });

  autoUpdater.on("update-not-available", async () => {
    if (availablePrompt || downloading || downloaded) return;
    attempt = null;
    checking = false;
    await dialog.showMessageBox({
      type: "info",
      buttons: ["OK"],
      defaultId: 0,
      title: "No Update Available",
      message: "Desktop Django Starter is up to date.",
      detail: `Current version: ${app.getVersion()}`
    });
  });

  autoUpdater.on("update-available", async (info) => {
    if (availablePrompt || downloading || downloaded) return;
    const owner = attempt || {};
    attempt = owner;
    availablePrompt = owner;
    checking = true;
    try {
      const result = await dialog.showMessageBox({
        type: "info",
        buttons: ["Download", "Not Now"],
        defaultId: 0,
        cancelId: 1,
        title: "Update Available",
        message: `Desktop Django Starter ${getVersionLabel(info)} is available.`,
        detail: "Download the update now and install it after the download completes."
      });
      if (attempt !== owner) return;
      if (result.response === 0) await downloadUpdate(owner);
      else attempt = null;
    } catch (error) {
      if (attempt === owner) {
        attempt = null;
        showUpdateError("Update Check Failed", error);
      }
    } finally {
      if (availablePrompt === owner) {
        availablePrompt = null;
        checking = false;
      }
    }
  });

  autoUpdater.on("download-progress", (progress) => {
    if (!progress || typeof progress.percent !== "number") {
      return;
    }
    updateLogger.info(`Update download progress: ${progress.percent.toFixed(1)}%.`);
  });

  autoUpdater.on("update-downloaded", async () => {
    attempt = null;
    availablePrompt = null;
    checking = false;
    downloading = false;
    downloaded = true;
    await promptToInstallDownloadedUpdate();
  });

  autoUpdater.on("error", (error) => {
    const title = downloading ? "Update Download Failed" : "Update Check Failed";
    attempt = null;
    availablePrompt = null;
    checking = false;
    downloading = false;
    showUpdateError(title, error);
  });

  return {
    checkForUpdates,
    getState: () => ({ checking, downloading, downloaded })
  };
}

module.exports = {
  createElectronUpdateController,
  getErrorMessage,
  getUpdateSupport,
  getVersionLabel
};
