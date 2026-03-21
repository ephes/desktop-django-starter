#!/usr/bin/env node

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const electronRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(electronRoot, "..");
const stageRoot = path.join(electronRoot, ".stage");
const backendRoot = path.join(stageRoot, "backend");
const runtimeDataRoot = path.join(stageRoot, "runtime-data");
const uvCommand = process.platform === "win32" ? "uv.exe" : "uv";

function copyRequiredFiles() {
  fs.rmSync(stageRoot, { recursive: true, force: true });
  fs.mkdirSync(backendRoot, { recursive: true });
  fs.mkdirSync(runtimeDataRoot, { recursive: true });

  fs.cpSync(path.join(repoRoot, "manage.py"), path.join(backendRoot, "manage.py"));
  fs.cpSync(path.join(repoRoot, "src"), path.join(backendRoot, "src"), { recursive: true });
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

copyRequiredFiles();

run(
  uvCommand,
  ["run", "--project", repoRoot, "--no-sync", "python", "manage.py", "collectstatic", "--noinput"],
  {
    cwd: backendRoot,
    env: {
      ...process.env,
      DJANGO_SETTINGS_MODULE: "desktop_django_starter.settings.packaged",
      // Local staging keeps the packaged settings contract runnable without
      // forcing a one-off secret key export on every smoke run.
      DJANGO_SECRET_KEY: process.env.DJANGO_SECRET_KEY || "desktop-django-starter-packaged-stage-secret",
      DESKTOP_DJANGO_APP_DATA_DIR: runtimeDataRoot,
      DESKTOP_DJANGO_BUNDLE_DIR: backendRoot,
      PYTHONUNBUFFERED: "1"
    }
  }
);

process.stdout.write(`Staged backend bundle at ${backendRoot}\n`);
