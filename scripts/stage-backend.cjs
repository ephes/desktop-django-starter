#!/usr/bin/env node

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const {
  DEFAULT_BUNDLED_PYTHON_VERSION,
  resolveBundledPythonExecutable,
  writeRuntimeManifest
} = require("./bundled-python.cjs");
const { materializeSymlinks } = require("./materialize-symlinks.cjs");
const { pruneBundledPythonRuntime } = require("./prune-bundled-python-runtime.cjs");

const repoRoot = path.resolve(__dirname, "..");
const stageRoot = path.join(repoRoot, ".stage");
const backendRoot = path.join(stageRoot, "backend");
const buildRoot = path.join(stageRoot, ".build");
const pythonInstallRoot = path.join(stageRoot, ".python-downloads");
const runtimeDataRoot = path.join(stageRoot, "runtime-data");
const uvCommand = process.platform === "win32" ? "uv.exe" : "uv";
const bundledPythonRequest = process.env.DESKTOP_DJANGO_BUNDLED_PYTHON_VERSION
  || DEFAULT_BUNDLED_PYTHON_VERSION;
const PACKAGED_STAGE_SECRET_KEY = "desktop-django-starter-packaged-stage-secret";
const PROCESS_GUARD_FILENAME = "desktop_process_guard.py";

function copyRequiredFiles() {
  fs.rmSync(stageRoot, { recursive: true, force: true });
  fs.mkdirSync(backendRoot, { recursive: true });
  fs.mkdirSync(buildRoot, { recursive: true });
  fs.mkdirSync(pythonInstallRoot, { recursive: true });
  fs.mkdirSync(runtimeDataRoot, { recursive: true });

  fs.cpSync(path.join(repoRoot, "manage.py"), path.join(backendRoot, "manage.py"));
  fs.cpSync(path.join(repoRoot, "src"), path.join(backendRoot, "src"), { recursive: true });
  copyProcessGuard();
}

function copyProcessGuard() {
  // The shells start every backend process through this launcher (job object
  // on Windows, exit when the shell's stdin pipe closes, orphan marker).
  fs.cpSync(
    path.join(__dirname, PROCESS_GUARD_FILENAME),
    path.join(backendRoot, PROCESS_GUARD_FILENAME)
  );
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    stdio: "inherit",
    ...options
  });

  if (result.error) {
    throw result.error;
  }

  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

function capture(command, args, options = {}) {
  const result = spawnSync(command, args, {
    encoding: "utf8",
    ...options
  });

  if (result.error) {
    throw result.error;
  }

  if (result.status !== 0) {
    process.stderr.write(result.stderr || "");
    process.exit(result.status ?? 1);
  }

  return result.stdout;
}

function findDownloadedRuntimeRoot() {
  const runtimeDirs = fs.readdirSync(pythonInstallRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && !entry.name.startsWith("."))
    .map((entry) => path.join(pythonInstallRoot, entry.name));

  if (runtimeDirs.length !== 1) {
    throw new Error(
      `Expected exactly one downloaded Python runtime in ${pythonInstallRoot}, found ${runtimeDirs.length}.`
    );
  }

  return runtimeDirs[0];
}

function stageBundledPythonRuntime() {
  run(
    uvCommand,
    [
      "python",
      "install",
      "--no-config",
      "--no-bin",
      "--install-dir",
      pythonInstallRoot,
      bundledPythonRequest
    ],
    { cwd: repoRoot }
  );

  fs.cpSync(findDownloadedRuntimeRoot(), path.join(backendRoot, "python"), {
    recursive: true,
    dereference: true
  });
  // uv's standalone runtimes can still leave link-shaped seams behind on some
  // platforms, so normalize the staged tree before packaging it as resources.
  materializeSymlinks(path.join(backendRoot, "python"));
  const removed = pruneBundledPythonRuntime(path.join(backendRoot, "python"));
  if (removed.length > 0) {
    process.stdout.write("Pruned bundled Python GUI artifacts:\n");
    for (const entry of removed) {
      process.stdout.write(`- ${entry}\n`);
    }
  }
  return resolveBundledPythonExecutable(backendRoot);
}

function readRuntimeInfo(pythonExecutable) {
  const script = `
import json
import sys
import sysconfig

print(json.dumps({
    "version": sys.version.split()[0],
    "root": sysconfig.get_paths()["data"],
    "executable": sys.executable,
    "purelib": sysconfig.get_paths()["purelib"],
    "scripts": sysconfig.get_paths()["scripts"],
}))
`.trim();

  const output = capture(
    pythonExecutable,
    ["-c", script]
  );

  return JSON.parse(output);
}

function buildWheel() {
  run(uvCommand, ["build", "--wheel", "--out-dir", buildRoot], { cwd: repoRoot });

  const wheelName = fs.readdirSync(buildRoot).find((entry) => entry.endsWith(".whl"));
  if (!wheelName) {
    throw new Error(`No wheel was produced in ${buildRoot}.`);
  }

  return path.join(buildRoot, wheelName);
}

function exportLockedRequirements() {
  const lockPath = path.join(repoRoot, "uv.lock");
  if (!fs.existsSync(lockPath)) {
    return null;
  }

  const requirementsPath = path.join(buildRoot, "requirements.txt");
  run(
    uvCommand,
    [
      "export",
      "--frozen",
      "--no-dev",
      "--no-emit-project",
      "--format",
      "requirements.txt",
      "--output-file",
      requirementsPath
    ],
    { cwd: repoRoot }
  );
  return requirementsPath;
}

function installBundledPackages(pythonExecutable, wheelPath) {
  const pipInstall = [
    "pip",
    "install",
    "--no-config",
    "--python",
    pythonExecutable,
    "--system",
    "--break-system-packages"
  ];
  const requirementsPath = exportLockedRequirements();

  if (requirementsPath) {
    // Install exactly the versions and hashes from uv.lock, then the app wheel
    // without letting it pull anything else from the index.
    run(uvCommand, [...pipInstall, "--require-hashes", "-r", requirementsPath], { cwd: repoRoot });
    run(uvCommand, [...pipInstall, "--reinstall", "--no-deps", wheelPath], { cwd: repoRoot });
    return;
  }

  process.stderr.write(
    "warning: no uv.lock next to the project; resolving bundled dependencies from the index.\n"
  );
  run(uvCommand, [...pipInstall, "--reinstall", wheelPath], { cwd: repoRoot });
}

function runPackagedManageCommand(pythonExecutable, args) {
  run(pythonExecutable, ["manage.py", ...args], {
    cwd: backendRoot,
    env: {
      ...process.env,
      DJANGO_SETTINGS_MODULE: "desktop_django_starter.settings.packaged",
      // This stage-only fallback covers build-time manage.py commands so the
      // build never writes a per-install secret_key file into stage data.
      // Installed apps generate their own key in the app-data directory.
      DJANGO_SECRET_KEY: process.env.DJANGO_SECRET_KEY || PACKAGED_STAGE_SECRET_KEY,
      DESKTOP_DJANGO_APP_DATA_DIR: runtimeDataRoot,
      DESKTOP_DJANGO_BUNDLE_DIR: backendRoot,
      PYTHONUNBUFFERED: "1"
    }
  });
}

copyRequiredFiles();
const bundledPython = stageBundledPythonRuntime();
writeRuntimeManifest(backendRoot, readRuntimeInfo(bundledPython));
installBundledPackages(bundledPython, buildWheel());
runPackagedManageCommand(bundledPython, ["collectstatic", "--noinput"]);
fs.rmSync(buildRoot, { recursive: true, force: true });
fs.rmSync(pythonInstallRoot, { recursive: true, force: true });

process.stdout.write(`Staged backend bundle at ${backendRoot}\n`);
