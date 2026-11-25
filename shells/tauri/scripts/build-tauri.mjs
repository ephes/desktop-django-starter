import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { buildOutputRoots, changedArtifacts, snapshotBundleArtifacts, snapshotArtifacts, resolveSmokeBinary, runPackagedSmoke, smokeTimeout } from "./packaged-smoke.mjs";

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

function matchesBuildArtifact(name, entry, root) {
  if (process.platform === "darwin") {
    return (entry.isFile() && name.startsWith(path.join(root, "dmg") + path.sep) && name.endsWith(".dmg"))
      || (entry.isDirectory() && name.startsWith(path.join(root, "macos") + path.sep) && name.endsWith(".app"));
  }

  if (process.platform === "win32") {
    return entry.isFile() && (
      (name.includes(`${path.sep}nsis${path.sep}`) && name.endsWith(".exe"))
      || (name.includes(`${path.sep}msi${path.sep}`) && name.endsWith(".msi"))
    );
  }

  return process.platform === "linux" && entry.isFile() && name.endsWith(".AppImage");
}

function printWindowsValidationChecklist(artifacts) {
  if (process.platform !== "win32") return;
  const installers = artifacts.filter(name => name.endsWith(".exe"));
  if (installers.length > 1) {
    throw new Error("Ambiguous current Windows NSIS installers; use an explicit target or a dedicated Cargo target directory");
  }
  if (installers.length === 0) return;

  process.stdout.write("\nWindows NSIS validation checklist:\n");
  process.stdout.write(`- Install the generated NSIS .exe from: ${installers[0]}\n`);
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
const beforeBuild = snapshotBundleArtifacts(bundleRoots, matchesBuildArtifact);
const beforeSmoke = smokeTest ? snapshotArtifacts(bundleRoots) : null;

run(npmCommand, ["run", "stage-backend"], { cwd: tauriRoot });
run(tauriBinary, ["build", ...buildArgs], { cwd: tauriRoot, env: process.env });
// Re-evaluate roots after the build to admit a newly created configured target.
const currentRoots = buildOutputRoots(layout);
const changed = changedArtifacts(beforeBuild, snapshotBundleArtifacts(currentRoots, matchesBuildArtifact));
const preferredExtension = process.platform === "darwin" ? ".dmg" : ".exe";
const builtArtifacts = [
  ...changed.filter(name => name.endsWith(preferredExtension)),
  ...changed.filter(name => !name.endsWith(preferredExtension)),
];
if (builtArtifacts.length > 0) {
  process.stdout.write("Built Tauri artifacts:\n");
  for (const artifactPath of builtArtifacts) process.stdout.write(`- ${artifactPath}\n`);
}
printWindowsValidationChecklist(builtArtifacts);
if (smokeTest) {
  const smokeBinary = resolveSmokeBinary(currentRoots, beforeSmoke);
  await runPackagedSmoke(smokeBinary.command, smokeBinary.args, {
    timeoutMs, cwd: repoRoot,
    env: { ...process.env, DESKTOP_DJANGO_SMOKE_TEST: "1" }
  });
}
