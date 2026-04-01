#!/usr/bin/env node

const { spawn } = require("node:child_process");
const path = require("node:path");

const electronBinary = require("electron");
const electronRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(electronRoot, "..", "..");

const env = { ...process.env };

for (const argument of process.argv.slice(2)) {
  if (argument === "--runtime=packaged") {
    env.DESKTOP_DJANGO_RUNTIME_MODE = "packaged";
    continue;
  }

  if (argument === "--smoke-test") {
    env.DESKTOP_DJANGO_SMOKE_TEST = "1";
    continue;
  }

  process.stderr.write(`Unknown argument: ${argument}\n`);
  process.exit(1);
}

if (env.DESKTOP_DJANGO_RUNTIME_MODE === "packaged" && !env.DESKTOP_DJANGO_BACKEND_ROOT) {
  env.DESKTOP_DJANGO_BACKEND_ROOT = path.join(repoRoot, ".stage", "backend");
}

const child = spawn(electronBinary, ["."], {
  cwd: electronRoot,
  env,
  stdio: "inherit"
});

child.on("error", (error) => {
  process.stderr.write(`${error.message}\n`);
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }

  process.exit(code ?? 0);
});
