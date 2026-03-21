const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron");
const { spawn } = require("node:child_process");
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");

const HOST = "127.0.0.1";
const STARTUP_TIMEOUT_MS = 15000;
const POLL_INTERVAL_MS = 250;

const repoRoot = path.resolve(__dirname, "..");

let djangoProcess = null;
let quitting = false;
let currentAppUrl = null;

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

function getDjangoEnvironment(port) {
  return {
    ...process.env,
    DJANGO_SETTINGS_MODULE: process.env.DJANGO_SETTINGS_MODULE || "desktop_django_starter.settings.local",
    DESKTOP_DJANGO_APP_DATA_DIR: app.getPath("userData"),
    DESKTOP_DJANGO_HOST: HOST,
    DESKTOP_DJANGO_PORT: String(port),
    PYTHONUNBUFFERED: "1"
  };
}

function getPythonCommand() {
  if (process.env.DESKTOP_DJANGO_PYTHON) {
    return process.env.DESKTOP_DJANGO_PYTHON;
  }

  if (app.isPackaged) {
    throw new Error(
      "Packaged Python runtime launching is not implemented yet. Use the development workflow for this slice."
    );
  }

  return process.platform === "win32" ? "uv.exe" : "uv";
}

function runManageCommand(args, port) {
  const command = getPythonCommand();

  return new Promise((resolve, reject) => {
    const child = spawn(command, ["run", "python", "manage.py", ...args], {
      cwd: repoRoot,
      env: getDjangoEnvironment(port),
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

function startDjangoServer(port) {
  const command = getPythonCommand();

  return new Promise((resolve, reject) => {
    let spawnFailed = false;

    djangoProcess = spawn(
      command,
      ["run", "python", "manage.py", "runserver", `${HOST}:${port}`, "--noreload"],
      {
        cwd: repoRoot,
        env: getDjangoEnvironment(port),
        stdio: ["ignore", "pipe", "pipe"]
      }
    );

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
  const port = await getOpenPort();
  const baseUrl = `http://${HOST}:${port}`;

  await runManageCommand(["migrate", "--noinput"], port);
  await startDjangoServer(port);
  await waitForDjango(baseUrl);
  createWindow(baseUrl);
}

ipcMain.handle("desktop:open-app-data-directory", async () => {
  const folderPath = app.getPath("userData");
  await shell.openPath(folderPath);
  return { path: folderPath };
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
