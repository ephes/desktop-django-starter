import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const tauriRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(tauriRoot, "..", "..");
const tauriBinary = path.join(
  tauriRoot,
  "node_modules",
  ".bin",
  process.platform === "win32" ? "tauri.cmd" : "tauri"
);
const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";

let smokeTest = false;
const forwardedArgs = [];

for (const argument of process.argv.slice(2)) {
  if (argument === "--smoke-test") {
    smokeTest = true;
    continue;
  }

  forwardedArgs.push(argument);
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

function listPaths(root, predicate) {
  if (!fs.existsSync(root)) {
    return [];
  }

  const matches = [];

  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    const entryPath = path.join(root, entry.name);
    if (predicate(entryPath)) {
      matches.push(entryPath);
    }

    if (entry.isDirectory()) {
      matches.push(...listPaths(entryPath, predicate));
    }
  }

  return matches.sort();
}

function resolveSmokeBinary(profile) {
  const bundleRoot = path.join(tauriRoot, "src-tauri", "target", profile, "bundle");

  if (process.platform === "darwin") {
    const appBundles = listPaths(bundleRoot, (entryPath) => entryPath.endsWith(".app"));
    for (const appBundle of appBundles) {
      const macOsRoot = path.join(appBundle, "Contents", "MacOS");
      if (!fs.existsSync(macOsRoot)) {
        continue;
      }

      const binaries = fs.readdirSync(macOsRoot)
        .map((entry) => path.join(macOsRoot, entry))
        .filter((entry) => fs.statSync(entry).isFile());

      if (binaries.length > 0) {
        return {
          command: binaries[0],
          args: []
        };
      }
    }
  }

  if (process.platform === "linux") {
    const appImages = listPaths(bundleRoot, (entryPath) => entryPath.endsWith(".AppImage"));
    if (appImages.length > 0) {
      return {
        command: appImages[0],
        args: []
      };
    }
  }

  throw new Error(`Unable to locate a runnable bundled Tauri app under ${bundleRoot}.`);
}

run(npmCommand, ["run", "stage-backend"], {
  cwd: tauriRoot
});

run(tauriBinary, ["build", ...forwardedArgs], {
  cwd: tauriRoot,
  env: process.env
});

if (smokeTest) {
  const profile = forwardedArgs.includes("--debug") ? "debug" : "release";
  const smokeBinary = resolveSmokeBinary(profile);

  run(smokeBinary.command, smokeBinary.args, {
    cwd: repoRoot,
    env: {
      ...process.env,
      DESKTOP_DJANGO_SMOKE_TEST: "1"
    }
  });
}
