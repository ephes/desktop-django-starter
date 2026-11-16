import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { buildOutputRoots, snapshotArtifacts, resolveSmokeBinary, runPackagedSmoke, smokeTimeout } from "./packaged-smoke.mjs";

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

function shouldDisableUpdaterSigning(args) {
  return !process.env.TAURI_SIGNING_PRIVATE_KEY && !args.includes("--no-sign");
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

function resolveBuiltArtifacts(bundleRoot) {
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

const baseBuildArgs = hasBundleControlArg(forwardedArgs)
  ? forwardedArgs
  : [...defaultBundleArgs({ smokeTest }), ...forwardedArgs];
const buildArgs = shouldDisableUpdaterSigning(baseBuildArgs)
  ? ["--no-sign", ...baseBuildArgs]
  : baseBuildArgs;

if (buildArgs[0] === "--no-sign") {
  process.stdout.write(
    "Tauri updater signing is disabled for this local build because "
      + "`TAURI_SIGNING_PRIVATE_KEY` is not set.\n"
  );
}

function argumentValue(name, short) {
  const values = buildArgs.flatMap((arg, index) => arg === name || (short && arg === short) ? [buildArgs[index + 1]]
    : arg.startsWith(`${name}=`) ? [arg.slice(name.length + 1)]
    : short && arg.startsWith(short) ? [arg.slice(short.length).replace(/^=/, '')] : []);
  if (values.length > 1 || values.some(value => !value || value.startsWith('-'))) {
    throw new Error(`Ambiguous or missing ${name}`);
  }
  return values[0];
}
const metadata = spawnSync('cargo', ['metadata', '--format-version', '1', '--no-deps',
  '--manifest-path', path.join(tauriRoot, 'src-tauri/Cargo.toml')], {
  cwd: tauriRoot, encoding: 'utf8', maxBuffer: 4 * 1024 * 1024
});
if (metadata.error || metadata.status !== 0) throw new Error(`Unable to determine Cargo target directory: ${metadata.error?.message || metadata.stderr}`);
const profile = argumentValue('--profile') || (buildArgs.includes('--debug') || buildArgs.includes('-d') ? 'debug' : 'release');
const runnerTargetDir = argumentValue('--target-dir');
const layout = { tauriRoot,
  targetDirectory: runnerTargetDir ? path.resolve(tauriRoot, 'src-tauri', runnerTargetDir)
    : JSON.parse(metadata.stdout).target_directory,
  target: argumentValue('--target', '-t') || process.env.CARGO_BUILD_TARGET,
  profile: profile === 'dev' ? 'debug' : profile };
const bundleRoots = buildOutputRoots(layout);
const timeoutMs = smokeTest ? smokeTimeout() : undefined;
const before = smokeTest ? snapshotArtifacts(bundleRoots) : null;

run(npmCommand, ["run", "stage-backend"], { cwd: tauriRoot });
// The bundler recreates its outputs; older bundles in other triple/host roots are stale.
const buildStartedAt = Date.now() - 2000;
run(tauriBinary, ["build", ...buildArgs], { cwd: tauriRoot, env: process.env });
// Re-evaluate roots after the build to admit a newly created configured target.
const currentRoots = buildOutputRoots(layout);
const builtArtifacts = currentRoots.flatMap(root => resolveBuiltArtifacts(root))
  .filter(artifactPath => fs.statSync(artifactPath).mtimeMs >= buildStartedAt);
if (builtArtifacts.length > 0) {
  process.stdout.write("Built Tauri artifacts:\n");
  for (const artifactPath of builtArtifacts) process.stdout.write(`- ${artifactPath}\n`);
}
printWindowsValidationChecklist(builtArtifacts);
if (smokeTest) {
  const smokeBinary = resolveSmokeBinary(currentRoots, before);
  await runPackagedSmoke(smokeBinary.command, smokeBinary.args, {
    timeoutMs, cwd: repoRoot,
    env: { ...process.env, DESKTOP_DJANGO_SMOKE_TEST: "1" }
  });
}
