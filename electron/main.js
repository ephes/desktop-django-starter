const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");

const {
  getRuntimeManifestPath,
  resolveBundledPythonExecutable
} = require("./scripts/bundled-python.cjs");

const HOST = "127.0.0.1";
const STARTUP_TIMEOUT_MS = 15000;
const POLL_INTERVAL_MS = 250;
// Local packaged-like runs still need a Django secret key, but we do not want
// this teaching slice to require end-user env setup before Electron can boot.
const PACKAGED_RUNTIME_SECRET_KEY = "desktop-django-starter-packaged-runtime-secret";

const repoRoot = path.resolve(__dirname, "..");

let djangoProcess = null;
let quitting = false;
let currentAppUrl = null;

function focusExistingWindow() {
  const existingWindow = BrowserWindow.getAllWindows()[0];
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
      : path.join(__dirname, ".stage", "backend");
  }

  return repoRoot;
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

function getHealthStatus(url) {
  return new Promise((resolve, reject) => {
    const request = http.get(`${url}/health/`, (response) => {
      response.resume();
      resolve(response.statusCode);
    });

    request.on("error", reject);
    request.setTimeout(1000, () => {
      request.destroy(new Error("Health check timed out."));
    });
  });
}

async function waitForDjango(url, timeoutMs = STARTUP_TIMEOUT_MS) {
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    try {
      const statusCode = await getHealthStatus(url);
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

function getDjangoEnvironment(port, runtimeMode, backendRoot) {
  const settingsModule = runtimeMode === "packaged"
    ? "desktop_django_starter.settings.packaged"
    : process.env.DJANGO_SETTINGS_MODULE || "desktop_django_starter.settings.local";

  const environment = {
    ...process.env,
    DJANGO_SETTINGS_MODULE: settingsModule,
    DESKTOP_DJANGO_APP_DATA_DIR: app.getPath("userData"),
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
    : "Run `npm --prefix electron run stage-backend` first.";

  throw new Error(
    `Packaged backend bundle is incomplete at ${backendRoot}.\nMissing:\n${missingPaths.join("\n")}\n\n${hint}`
  );
}

function runManageCommand(args, port, runtimeMode, backendRoot) {
  const invocation = buildManageInvocation(runtimeMode, backendRoot, args);

  return new Promise((resolve, reject) => {
    const child = spawn(invocation.command, invocation.args, {
      cwd: invocation.cwd,
      env: getDjangoEnvironment(port, runtimeMode, backendRoot),
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

function startDjangoServer(port, runtimeMode, backendRoot) {
  const invocation = buildManageInvocation(
    runtimeMode,
    backendRoot,
    ["runserver", `${HOST}:${port}`, "--noreload"]
  );

  return new Promise((resolve, reject) => {
    let spawnFailed = false;

    djangoProcess = spawn(invocation.command, invocation.args, {
      cwd: invocation.cwd,
      env: getDjangoEnvironment(port, runtimeMode, backendRoot),
      stdio: ["ignore", "pipe", "pipe"]
    });

    djangoProcess.stdout.on("data", (chunk) => {
      process.stdout.write(`[django] ${chunk}`);
    });

    djangoProcess.stderr.on("data", (chunk) => {
      process.stderr.write(`[django] ${chunk}`);
    });

    djangoProcess.once("error", (error) => {
      spawnFailed = true;
      djangoProcess = null;
      reject(new Error(`Failed to start Django: ${error.message}`));
    });

    djangoProcess.once("spawn", () => {
      resolve();
    });

    djangoProcess.once("exit", (code, signal) => {
      if (quitting || spawnFailed) {
        return;
      }

      dialog.showErrorBox(
        "Django exited",
        `The Django process stopped before the desktop app finished.\n\nCode: ${code}\nSignal: ${signal}`
      );
      app.quit();
    });
  });
}

function createWindow(url) {
  const win = new BrowserWindow({
    width: 1200,
    height: 840,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  currentAppUrl = url;

  win.once("ready-to-show", () => {
    win.show();
  });

  win.webContents.once("did-finish-load", () => {
    if (process.env.DESKTOP_DJANGO_SMOKE_TEST === "1") {
      setTimeout(() => app.quit(), 750);
    }
  });

  win.loadURL(url);
}

async function stopDjango() {
  if (!djangoProcess || djangoProcess.killed) {
    return;
  }

  const processToStop = djangoProcess;
  djangoProcess = null;

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

  if (runtimeMode === "packaged") {
    validatePackagedBackendRoot(backendRoot);
  }

  await runManageCommand(["migrate", "--noinput"], port, runtimeMode, backendRoot);
  await startDjangoServer(port, runtimeMode, backendRoot);
  await waitForDjango(baseUrl);
  createWindow(baseUrl);
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
    createWindow(currentAppUrl);
  }
});

app.whenReady()
  .then(async () => {
    try {
      await bootstrap();
    } catch (error) {
      dialog.showErrorBox(
        "Startup failed",
        error instanceof Error ? error.message : "Unknown startup failure."
      );
      app.quit();
    }
  });

app.on("will-quit", async (event) => {
  event.preventDefault();
  try {
    await stopDjango();
  } catch (_error) {
    // Continue quitting even if child-process cleanup fails.
  }
  app.exit(0);
});
