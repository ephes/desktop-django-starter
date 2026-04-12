const { app, BrowserWindow, dialog, ipcMain, Menu, nativeImage, shell } = require("electron");
const { autoUpdater } = require("electron-updater");
const { spawn } = require("node:child_process");
const crypto = require("node:crypto");
const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");

const {
  getRuntimeManifestPath,
  resolveBundledPythonExecutable
} = require("./scripts/bundled-python.cjs");
const {
  buildDesktopAuthHeaders,
  desktopAuthHeadersForRequest,
  getDesktopAuthWebRequestFilter
} = require("./scripts/auth-token.cjs");
const {
  getNavigationGuardAction,
  getWindowOpenGuardResponse
} = require("./scripts/window-guards.cjs");
const { shouldShowManagedProcessExitDialog } = require("./scripts/process-exit-policy.cjs");
const { createElectronUpdateController } = require("./scripts/updates.cjs");

const HOST = "127.0.0.1";
const STARTUP_TIMEOUT_MS = 15000;
const POLL_INTERVAL_MS = 250;
const MINIMUM_SPLASH_DURATION_MS = 2400;
const APP_ICON_PATH = path.join(__dirname, "assets", "icons", "app-icon.png");
// Local packaged-like runs still need a Django secret key, but we do not want
// this teaching slice to require end-user env setup before Electron can boot.
const PACKAGED_RUNTIME_SECRET_KEY = "desktop-django-starter-packaged-runtime-secret";

const repoRoot = path.resolve(__dirname, "..", "..");

let djangoProcess = null;
let taskWorkerProcess = null;
let quitting = false;
let currentAppUrl = null;
let currentAuthToken = null;
let mainWindow = null;
let splashWindow = null;
let splashShownAt = null;
let updateInstallInProgress = false;
const intentionallyStoppedManagedProcesses = new WeakSet();

function focusExistingWindow() {
  const existingWindow = mainWindow || splashWindow || BrowserWindow.getAllWindows()[0];
  if (!existingWindow) {
    return;
  }

  if (existingWindow.isMinimized()) {
    existingWindow.restore();
  }

  existingWindow.focus();
}

function getRuntimeMode() {
  if (process.env.DESKTOP_DJANGO_RUNTIME_MODE === "packaged") {
    return "packaged";
  }

  return app.isPackaged ? "packaged" : "development";
}

function getBackendRoot(runtimeMode) {
  if (process.env.DESKTOP_DJANGO_BACKEND_ROOT) {
    return path.resolve(process.env.DESKTOP_DJANGO_BACKEND_ROOT);
  }

  if (runtimeMode === "packaged") {
    return app.isPackaged
      ? path.join(process.resourcesPath, "backend")
      : path.join(repoRoot, ".stage", "backend");
  }

  return repoRoot;
}

function getSplashTemplatePath(backendRoot) {
  return path.join(backendRoot, "src", "desktop_django_starter", "templates", "splash.html");
}

function getWindowIconOptions() {
  if (process.platform === "darwin" || !fs.existsSync(APP_ICON_PATH)) {
    return {};
  }

  return { icon: APP_ICON_PATH };
}

function setApplicationIcon() {
  if (process.platform !== "darwin" || !app.dock || !fs.existsSync(APP_ICON_PATH)) {
    return;
  }

  const icon = nativeImage.createFromPath(APP_ICON_PATH);
  if (icon.isEmpty()) {
    return;
  }

  app.dock.setIcon(icon);
}

function buildApplicationMenu(updateController) {
  const template = [
    ...(process.platform === "darwin"
      ? [
          {
            label: app.name,
            submenu: [
              { role: "about" },
              { type: "separator" },
              { role: "services" },
              { type: "separator" },
              { role: "hide" },
              { role: "hideOthers" },
              { role: "unhide" },
              { type: "separator" },
              { role: "quit" }
            ]
          }
        ]
      : []),
    {
      label: "File",
      submenu: [
        process.platform === "darwin" ? { role: "close" } : { role: "quit" }
      ]
    },
    {
      label: "Edit",
      submenu: [
        { role: "undo" },
        { role: "redo" },
        { type: "separator" },
        { role: "cut" },
        { role: "copy" },
        { role: "paste" },
        ...(process.platform === "darwin"
          ? [
              { role: "pasteAndMatchStyle" },
              { role: "delete" },
              { role: "selectAll" },
              { type: "separator" },
              {
                label: "Speech",
                submenu: [
                  { role: "startSpeaking" },
                  { role: "stopSpeaking" }
                ]
              }
            ]
          : [
              { role: "delete" },
              { type: "separator" },
              { role: "selectAll" }
            ])
      ]
    },
    {
      label: "View",
      submenu: [
        { role: "reload" },
        { role: "forceReload" },
        { role: "toggleDevTools" },
        { type: "separator" },
        { role: "resetZoom" },
        { role: "zoomIn" },
        { role: "zoomOut" },
        { type: "separator" },
        { role: "togglefullscreen" }
      ]
    },
    {
      label: "Window",
      submenu: [
        { role: "minimize" },
        ...(process.platform === "darwin"
          ? [
              { role: "zoom" },
              { type: "separator" },
              { role: "front" }
            ]
          : [
              { role: "close" }
            ])
      ]
    },
    {
      role: "help",
      submenu: [
        {
          label: "Check for Updates...",
          click: () => {
            updateController.checkForUpdates().catch((error) => {
              dialog.showErrorBox(
                "Update Check Failed",
                error instanceof Error ? error.message : "Unknown update failure."
              );
            });
          }
        }
      ]
    }
  ];

  return Menu.buildFromTemplate(template);
}

function installApplicationMenu(updateController) {
  Menu.setApplicationMenu(buildApplicationMenu(updateController));
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function getOpenPort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();

    server.on("error", reject);
    server.listen(0, HOST, () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        server.close(() => reject(new Error("Unable to resolve a random localhost port.")));
        return;
      }

      const { port } = address;
      server.close((error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve(port);
      });
    });
  });
}

function getHealthStatus(url, authToken = "") {
  return new Promise((resolve, reject) => {
    const healthUrl = new URL("/health/", url);
    const request = http.get(
      healthUrl,
      { headers: buildDesktopAuthHeaders(authToken) },
      (response) => {
        response.resume();
        resolve(response.statusCode);
      }
    );

    request.on("error", reject);
    request.setTimeout(1000, () => {
      request.destroy(new Error("Health check timed out."));
    });
  });
}

async function waitForDjango(url, authToken = "", timeoutMs = STARTUP_TIMEOUT_MS) {
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    try {
      const statusCode = await getHealthStatus(url, authToken);
      if (statusCode === 200) {
        return;
      }
    } catch (_error) {
      // Poll until Django is ready or the timeout expires.
    }

    await sleep(POLL_INTERVAL_MS);
  }

  throw new Error(`Django did not become ready within ${timeoutMs}ms.`);
}

function getDjangoEnvironment(port, runtimeMode, backendRoot, authToken = "") {
  const settingsModule = runtimeMode === "packaged"
    ? "desktop_django_starter.settings.packaged"
    : process.env.DJANGO_SETTINGS_MODULE || "desktop_django_starter.settings.local";

  const environment = {
    ...process.env,
    DJANGO_SETTINGS_MODULE: settingsModule,
    DESKTOP_DJANGO_APP_DATA_DIR: app.getPath("userData"),
    DESKTOP_DJANGO_AUTH_TOKEN: authToken,
    DESKTOP_DJANGO_BUNDLE_DIR: backendRoot,
    DESKTOP_DJANGO_HOST: HOST,
    DESKTOP_DJANGO_PORT: String(port),
    PYTHONUNBUFFERED: "1"
  };

  if (runtimeMode === "packaged" && !environment.DJANGO_SECRET_KEY) {
    environment.DJANGO_SECRET_KEY = PACKAGED_RUNTIME_SECRET_KEY;
  }

  return environment;
}

function getPackagedDatabasePath(runtimeMode) {
  if (runtimeMode !== "packaged") {
    return null;
  }

  return path.join(app.getPath("userData"), "app.sqlite3");
}

function getPythonLaunchSpec(runtimeMode, backendRoot) {
  if (process.env.DESKTOP_DJANGO_PYTHON) {
    return {
      command: process.env.DESKTOP_DJANGO_PYTHON,
      prefixArgs: []
    };
  }

  if (runtimeMode === "packaged") {
    return {
      command: resolveBundledPythonExecutable(backendRoot),
      prefixArgs: []
    };
  }

  return {
    command: process.platform === "win32" ? "uv.exe" : "uv",
    prefixArgs: ["run", "python"]
  };
}

function buildManageInvocation(runtimeMode, backendRoot, manageArgs) {
  const { command, prefixArgs } = getPythonLaunchSpec(runtimeMode, backendRoot);

  return {
    command,
    cwd: backendRoot,
    args: [...prefixArgs, "manage.py", ...manageArgs]
  };
}

function validatePackagedBackendRoot(backendRoot) {
  const requiredPaths = [
    path.join(backendRoot, "manage.py"),
    path.join(backendRoot, "src", "desktop_django_starter"),
    path.join(backendRoot, "src", "example_app"),
    path.join(backendRoot, "src", "tasks_demo"),
    path.join(backendRoot, "staticfiles"),
    path.join(backendRoot, "python"),
    getRuntimeManifestPath(backendRoot)
  ];

  const missingPaths = requiredPaths.filter((requiredPath) => !fs.existsSync(requiredPath));
  if (missingPaths.length === 0) {
    return;
  }

  const hint = app.isPackaged
    ? "Expected packaged resources are missing."
    : "Run `npm --prefix shells/electron run stage-backend` first.";

  throw new Error(
    `Packaged backend bundle is incomplete at ${backendRoot}.\nMissing:\n${missingPaths.join("\n")}\n\n${hint}`
  );
}

function runManageCommand(args, port, runtimeMode, backendRoot, authToken) {
  const invocation = buildManageInvocation(runtimeMode, backendRoot, args);

  return new Promise((resolve, reject) => {
    const child = spawn(invocation.command, invocation.args, {
      cwd: invocation.cwd,
      env: getDjangoEnvironment(port, runtimeMode, backendRoot, authToken),
      stdio: ["ignore", "pipe", "pipe"]
    });

    let stderr = "";

    child.stdout.on("data", (chunk) => {
      process.stdout.write(`[django] ${chunk}`);
    });

    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
      process.stderr.write(`[django] ${chunk}`);
    });

    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) {
        resolve();
        return;
      }
      reject(new Error(stderr || `manage.py ${args.join(" ")} failed with exit code ${code}.`));
    });
  });
}

function startDjangoServer(port, runtimeMode, backendRoot, authToken) {
  return startManagedProcess({
    processName: "django",
    port,
    runtimeMode,
    backendRoot,
    authToken,
    manageArgs: ["runserver", `${HOST}:${port}`, "--noreload"],
    exitTitle: "Django exited",
    exitMessage: (code, signal) => (
      "The Django process stopped before the desktop app finished.\n\n"
      + `Code: ${code}\nSignal: ${signal}`
    )
  });
}

function startTaskWorker(port, runtimeMode, backendRoot, authToken) {
  return startManagedProcess({
    processName: "worker",
    port,
    runtimeMode,
    backendRoot,
    authToken,
    manageArgs: ["db_worker", "--queue-name", "default", "--worker-id", "desktop-django-starter"],
    exitTitle: "Task worker exited",
    exitMessage: (code, signal) => (
      "The background task worker stopped before the desktop app finished.\n\n"
      + `Code: ${code}\nSignal: ${signal}`
    )
  });
}

function startManagedProcess({
  processName,
  port,
  runtimeMode,
  backendRoot,
  authToken,
  manageArgs,
  exitTitle,
  exitMessage
}) {
  const invocation = buildManageInvocation(runtimeMode, backendRoot, manageArgs);

  return new Promise((resolve, reject) => {
    let spawnFailed = false;

    const child = spawn(invocation.command, invocation.args, {
      cwd: invocation.cwd,
      env: getDjangoEnvironment(port, runtimeMode, backendRoot, authToken),
      stdio: ["ignore", "pipe", "pipe"]
    });

    if (processName === "django") {
      djangoProcess = child;
    } else {
      taskWorkerProcess = child;
    }

    child.stdout.on("data", (chunk) => {
      process.stdout.write(`[${processName}] ${chunk}`);
    });

    child.stderr.on("data", (chunk) => {
      process.stderr.write(`[${processName}] ${chunk}`);
    });

    child.once("error", (error) => {
      spawnFailed = true;
      clearManagedProcess(processName, child);
      reject(new Error(`Failed to start ${processName}: ${error.message}`));
    });

    child.once("spawn", () => {
      resolve();
    });

    child.once("exit", (code, signal) => {
      clearManagedProcess(processName, child);
      if (!shouldShowManagedProcessExitDialog({
        quitting,
        spawnFailed,
        updateInstallInProgress,
        intentionalStopRequested: intentionallyStoppedManagedProcesses.has(child)
      })) {
        return;
      }

      dialog.showErrorBox(
        exitTitle,
        exitMessage(code, signal)
      );
      app.quit();
    });
  });
}

function clearManagedProcess(processName, child) {
  if (processName === "django" && djangoProcess === child) {
    djangoProcess = null;
  }

  if (processName === "worker" && taskWorkerProcess === child) {
    taskWorkerProcess = null;
  }
}

function closeSplashWindow() {
  if (!splashWindow || splashWindow.isDestroyed()) {
    splashWindow = null;
    splashShownAt = null;
    return;
  }

  const windowToClose = splashWindow;
  splashWindow = null;
  splashShownAt = null;
  windowToClose.destroy();
}

async function waitForMinimumSplashDuration() {
  if (typeof splashShownAt !== "number") {
    return;
  }

  const elapsedMs = Date.now() - splashShownAt;
  const remainingMs = MINIMUM_SPLASH_DURATION_MS - elapsedMs;
  if (remainingMs > 0) {
    await sleep(remainingMs);
  }
}

function createSplashWindow(backendRoot) {
  if (splashWindow && !splashWindow.isDestroyed()) {
    return splashWindow;
  }

  const win = new BrowserWindow({
    width: 560,
    height: 560,
    show: false,
    frame: false,
    resizable: false,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    autoHideMenuBar: true,
    backgroundColor: "#222121",
    ...getWindowIconOptions(),
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  splashWindow = win;

  win.on("closed", () => {
    if (splashWindow === win) {
      splashWindow = null;
    }
  });

  win.once("ready-to-show", () => {
    splashShownAt = Date.now();
    win.show();
  });

  win.loadFile(getSplashTemplatePath(backendRoot));
  return win;
}

function registerDesktopAuthHeaderInjection(win, url, authToken) {
  win.webContents.session.webRequest.onBeforeSendHeaders(
    getDesktopAuthWebRequestFilter(url),
    (details, callback) => {
      callback({
        requestHeaders: desktopAuthHeadersForRequest(details, url, authToken)
      });
    }
  );
}

function registerWindowNavigationGuards(win, url) {
  win.webContents.setWindowOpenHandler(({ url: targetUrl }) => {
    const guardResponse = getWindowOpenGuardResponse(targetUrl, url);
    if (guardResponse.openExternal) {
      shell.openExternal(targetUrl).catch(() => {});
    }
    return { action: guardResponse.action };
  });

  win.webContents.on("will-navigate", (event, targetUrl) => {
    const navigationAction = getNavigationGuardAction(targetUrl, url);
    if (navigationAction.allowNavigation) {
      return;
    }

    event.preventDefault();
    if (navigationAction.openExternal) {
      shell.openExternal(targetUrl).catch(() => {});
    }
  });
}

function createWindow(url, authToken) {
  const win = new BrowserWindow({
    width: 1200,
    height: 840,
    show: false,
    backgroundColor: "#222121",
    ...getWindowIconOptions(),
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  mainWindow = win;
  currentAppUrl = url;
  currentAuthToken = authToken;

  win.on("closed", () => {
    if (mainWindow === win) {
      mainWindow = null;
    }
  });

  win.once("ready-to-show", async () => {
    await waitForMinimumSplashDuration();
    win.show();
    closeSplashWindow();
  });

  win.webContents.once("did-finish-load", () => {
    if (process.env.DESKTOP_DJANGO_SMOKE_TEST === "1") {
      setTimeout(() => app.quit(), 750);
    }
  });

  registerDesktopAuthHeaderInjection(win, url, authToken);
  registerWindowNavigationGuards(win, url);
  win.loadURL(url);
}

async function stopDjango() {
  const processToStop = djangoProcess;
  djangoProcess = null;
  await stopManagedProcess(processToStop);
}

async function stopTaskWorker() {
  const processToStop = taskWorkerProcess;
  taskWorkerProcess = null;
  await stopManagedProcess(processToStop);
}

async function stopManagedProcess(processToStop) {
  if (!processToStop || processToStop.killed) {
    return;
  }

  intentionallyStoppedManagedProcesses.add(processToStop);

  if (process.platform === "win32") {
    await new Promise((resolve) => {
      const killer = spawn("taskkill", ["/pid", String(processToStop.pid), "/t", "/f"], {
        stdio: "ignore"
      });

      killer.on("error", () => resolve());
      killer.on("exit", () => resolve());
    });
    return;
  }

  await new Promise((resolve) => {
    let resolved = false;

    processToStop.once("exit", () => {
      resolved = true;
      resolve();
    });

    processToStop.kill("SIGTERM");

    setTimeout(() => {
      if (resolved) {
        return;
      }
      processToStop.kill("SIGKILL");
      resolve();
    }, 2000);
  });
}

async function bootstrap() {
  const runtimeMode = getRuntimeMode();
  const backendRoot = getBackendRoot(runtimeMode);
  const port = await getOpenPort();
  const baseUrl = `http://${HOST}:${port}`;
  const authToken = crypto.randomBytes(32).toString("hex");
  const packagedDatabasePath = getPackagedDatabasePath(runtimeMode);
  const shouldSeedDemoContent = packagedDatabasePath !== null && !fs.existsSync(packagedDatabasePath);

  createSplashWindow(backendRoot);

  if (runtimeMode === "packaged") {
    validatePackagedBackendRoot(backendRoot);
  }

  await runManageCommand(["migrate", "--noinput"], port, runtimeMode, backendRoot, authToken);
  if (shouldSeedDemoContent) {
    await runManageCommand(["seed_demo_content"], port, runtimeMode, backendRoot, authToken);
  }
  await startDjangoServer(port, runtimeMode, backendRoot, authToken);
  await waitForDjango(baseUrl, authToken);
  // Start the worker only after Django is healthy so startup failures are
  // surfaced against a known-good migrated app database.
  await startTaskWorker(port, runtimeMode, backendRoot, authToken);
  createWindow(baseUrl, authToken);
}

async function prepareForUpdateInstall() {
  // Mark the updater handoff before stopping child processes so their expected
  // exits do not surface as false-positive crash dialogs.
  updateInstallInProgress = true;
  await stopTaskWorker();
  await stopDjango();
}

ipcMain.handle("desktop:open-app-data-directory", async () => {
  const folderPath = app.getPath("userData");
  await shell.openPath(folderPath);
  return { path: folderPath };
});

// Keep the packaged desktop shell single-instance so a second launch does not
// race the backend bootstrap path and run migrations against the same SQLite DB.
const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) {
  app.quit();
}

app.on("second-instance", () => {
  focusExistingWindow();
});

app.on("before-quit", () => {
  quitting = true;
});

app.on("window-all-closed", () => {
  app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0 && currentAppUrl) {
    createWindow(currentAppUrl, currentAuthToken);
  }
});

app.whenReady()
  .then(async () => {
    try {
      setApplicationIcon();
      installApplicationMenu(createElectronUpdateController({
        app,
        autoUpdater,
        dialog,
        beforeInstall: prepareForUpdateInstall
      }));
      await bootstrap();
    } catch (error) {
      closeSplashWindow();
      dialog.showErrorBox(
        "Startup failed",
        error instanceof Error ? error.message : "Unknown startup failure."
      );
      app.quit();
    }
  });

app.on("will-quit", async (event) => {
  if (updateInstallInProgress) {
    return;
  }

  event.preventDefault();
  try {
    await stopTaskWorker();
    await stopDjango();
  } catch (_error) {
    // Continue quitting even if child-process cleanup fails.
  }
  app.exit(0);
});
