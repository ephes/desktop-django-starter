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

function hasBundleControlArg(args) {
  return args.some((argument) => (
    argument === "--bundles"
    || argument === "-b"
    || argument.startsWith("--bundles=")
    || argument === "--no-bundle"
  ));
}

function defaultBundleArgs({ smokeTest: shouldSmokeTest }) {
  if (process.platform === "darwin") {
    return ["--bundles", shouldSmokeTest ? "app" : "dmg"];
  }

  if (process.platform === "win32") {
    return ["--bundles", "nsis"];
  }

  if (process.platform === "linux") {
    return ["--bundles", "appimage"];
  }

  return [];
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

function resolveBuiltArtifacts(profile) {
  const bundleRoot = path.join(tauriRoot, "src-tauri", "target", profile, "bundle");
  const dmgRoot = path.join(bundleRoot, "dmg");
  const macosRoot = path.join(bundleRoot, "macos");

  if (process.platform === "darwin") {
    return [
      ...listPaths(dmgRoot, (entryPath) => entryPath.endsWith(".dmg")),
      ...listPaths(macosRoot, (entryPath) => entryPath.endsWith(".app"))
    ];
  }

  if (process.platform === "win32") {
    return [
      ...listPaths(bundleRoot, (entryPath) => (
        entryPath.includes(`${path.sep}nsis${path.sep}`) && entryPath.endsWith(".exe")
      )),
      ...listPaths(bundleRoot, (entryPath) => (
        entryPath.includes(`${path.sep}msi${path.sep}`) && entryPath.endsWith(".msi")
      ))
    ];
  }

  if (process.platform === "linux") {
    return listPaths(bundleRoot, (entryPath) => entryPath.endsWith(".AppImage"));
  }

  return [];
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

  if (process.platform === "win32") {
    throw new Error(
      "Windows bundle smoke testing is not automated in this wrapper because Tauri emits "
      + "installers under target/<profile>/bundle/nsis/ or bundle/msi/ rather than a directly "
      + "runnable app bundle. Validate the generated installer on a Windows machine."
    );
  }

  throw new Error(`Unable to locate a runnable bundled Tauri app under ${bundleRoot}.`);
}

function printWindowsValidationChecklist(artifacts) {
  if (process.platform !== "win32" || artifacts.length === 0) {
    return;
  }

  process.stdout.write("\nWindows NSIS validation checklist:\n");
  process.stdout.write(`- Install the generated NSIS .exe from: ${artifacts[0]}\n`);
  process.stdout.write("- Launch the installed app on a real Windows machine.\n");
  process.stdout.write("- Confirm the splash appears, then the Django UI loads from localhost.\n");
  process.stdout.write("- Confirm app startup runs against the staged bundled runtime with no system Python dependency.\n");
  process.stdout.write("- Confirm closing the app stops the bundled Django and db_worker processes cleanly.\n");
  process.stdout.write("- Confirm writable app data persists across relaunches under the per-user app-data directory.\n");
}

const buildArgs = hasBundleControlArg(forwardedArgs)
  ? forwardedArgs
  : [...defaultBundleArgs({ smokeTest }), ...forwardedArgs];

run(npmCommand, ["run", "stage-backend"], {
  cwd: tauriRoot
});

run(tauriBinary, ["build", ...buildArgs], {
  cwd: tauriRoot,
  env: process.env
});

const profile = buildArgs.includes("--debug") ? "debug" : "release";
const builtArtifacts = resolveBuiltArtifacts(profile);

if (builtArtifacts.length > 0) {
  process.stdout.write("Built Tauri artifacts:\n");
  for (const artifactPath of builtArtifacts) {
    process.stdout.write(`- ${artifactPath}\n`);
  }
}

printWindowsValidationChecklist(builtArtifacts);

if (smokeTest) {
  const smokeBinary = resolveSmokeBinary(profile);

  run(smokeBinary.command, smokeBinary.args, {
    cwd: repoRoot,
    env: {
      ...process.env,
      DESKTOP_DJANGO_SMOKE_TEST: "1"
    }
  });
}
