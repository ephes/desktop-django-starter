const fs = require("node:fs");
const path = require("node:path");

const DEFAULT_BUNDLED_PYTHON_VERSION = "3.14";
const MAX_MANIFEST_BYTES = 64 * 1024;
const RUNTIME_MANIFEST_FILENAME = "runtime-manifest.json";

function toManifestPath(backendRoot, targetPath) {
  return path.relative(backendRoot, targetPath).split(path.sep).join("/");
}

function fromManifestPath(backendRoot, targetPath) {
  if (typeof targetPath !== "string" || targetPath.split("/").some(component =>
    !component || component === "." || component === ".." ||
    /[<>:"\\|?*\x00-\x1f\x7f-\x9f]/.test(component) || /[. ]$/.test(component))) {
    throw new Error("Invalid runtime manifest: expected a portable relative path.");
  }
  return path.resolve(backendRoot, ...targetPath.split("/"));
}

function getRuntimeManifestPath(backendRoot) {
  return path.join(backendRoot, RUNTIME_MANIFEST_FILENAME);
}

function getBundledPythonCandidates(backendRoot, platform = process.platform) {
  if (platform === "win32") {
    return [
      path.join(backendRoot, "python", "python.exe"),
      path.join(backendRoot, "python", "Scripts", "python.exe")
    ];
  }

  return [
    path.join(backendRoot, "python", "bin", "python3"),
    path.join(backendRoot, "python", "bin", "python")
  ];
}

function getVersionedBundledPythonCandidates(backendRoot, platform = process.platform) {
  if (platform === "win32") {
    return [];
  }

  const binRoot = path.join(backendRoot, "python", "bin");
  if (!fs.existsSync(binRoot)) {
    return [];
  }

  return fs.readdirSync(binRoot, { withFileTypes: true })
    .filter((entry) => entry.isFile() && /^python\d+\.\d+$/.test(entry.name))
    .map((entry) => ({
      executable: path.join(binRoot, entry.name),
      version: entry.name.replace(/^python/, "").split(".").map((segment) => Number(segment))
    }))
    .sort((left, right) => {
      const maxLength = Math.max(left.version.length, right.version.length);
      for (let index = 0; index < maxLength; index += 1) {
        const leftPart = left.version[index] ?? 0;
        const rightPart = right.version[index] ?? 0;
        if (leftPart !== rightPart) {
          return rightPart - leftPart;
        }
      }

      return 0;
    })
    .map((entry) => entry.executable);
}

function contained(root, target) {
  const relative = path.relative(root, target);
  return relative !== "" && !relative.startsWith(`..${path.sep}`) && relative !== ".."
    && !path.isAbsolute(relative);
}

function validateRuntimeManifest(manifest, backendRoot) {
  const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
  if (!object(manifest) || manifest.schemaVersion !== 1 || !object(manifest.python)
      || !object(manifest.launcher)) throw new Error("Unsupported schema or missing objects.");
  const python = manifest.python;
  if (typeof python.version !== "string" || !python.version.trim() || python.root !== "python") {
    throw new Error("Expected Python version and python runtime root.");
  }
  const runtimeRoot = fromManifestPath(backendRoot, python.root);
  for (const key of ["executable", "purelib", "scripts"]) {
    if (!contained(runtimeRoot, fromManifestPath(backendRoot, python[key]))) {
      throw new Error(`Python ${key} must be inside python/.`);
    }
  }
  const launcher = manifest.launcher;
  if (launcher.cwd !== "." || typeof launcher.settingsModule !== "string" || !launcher.settingsModule
      || !Array.isArray(launcher.environment) || !launcher.environment.every(item => typeof item === "string")) {
    throw new Error("Invalid launcher fields.");
  }
  for (const key of ["managePy", "sourceRoot"]) fromManifestPath(backendRoot, launcher[key]);
  return manifest;
}

function loadRuntimeManifest(backendRoot) {
  const manifestPath = getRuntimeManifestPath(backendRoot);
  let descriptor;
  try {
    let stats;
    try { stats = fs.lstatSync(manifestPath); }
    catch (error) { if (error.code === "ENOENT") return null; throw error; }
    if (!stats.isFile() || stats.size > MAX_MANIFEST_BYTES) throw new Error("Expected a regular file of at most 65536 bytes.");
    descriptor = fs.openSync(manifestPath, fs.constants.O_RDONLY | fs.constants.O_NONBLOCK | (fs.constants.O_NOFOLLOW || 0));
    stats = fs.fstatSync(descriptor);
    if (!stats.isFile() || stats.size > MAX_MANIFEST_BYTES) throw new Error("Expected a bounded regular file.");
    const buffer = Buffer.alloc(MAX_MANIFEST_BYTES + 1);
    let length = 0;
    while (length < buffer.length) {
      const count = fs.readSync(descriptor, buffer, length, buffer.length - length, null);
      if (!count) break;
      length += count;
    }
    if (length > MAX_MANIFEST_BYTES) throw new Error("Manifest exceeds 65536 bytes.");
    return validateRuntimeManifest(JSON.parse(buffer.subarray(0, length).toString("utf8")), backendRoot);
  } catch (error) {
    throw new Error(`Invalid runtime manifest ${manifestPath}: ${error.message}`, { cause: error });
  } finally {
    if (descriptor !== undefined) fs.closeSync(descriptor);
  }
}

function usableInterpreter(backendRoot, executable, platform) {
  const runtimeRoot = path.join(backendRoot, "python");
  const realRuntime = fs.realpathSync(runtimeRoot);
  if (realRuntime !== path.join(fs.realpathSync(backendRoot), "python")
      || !contained(realRuntime, fs.realpathSync(executable)) || !fs.statSync(executable).isFile()) {
    throw new Error("Interpreter must be a regular file contained in the bundled runtime.");
  }
  fs.accessSync(executable, platform === "win32" ? fs.constants.R_OK : fs.constants.X_OK);
  return executable;
}

function resolveBundledPythonExecutable(backendRoot, platform = process.platform) {
  const manifest = loadRuntimeManifest(backendRoot);
  if (manifest) {
    const executable = fromManifestPath(backendRoot, manifest.python.executable);
    try { return usableInterpreter(backendRoot, executable, platform); }
    catch (error) {
      throw new Error(`Invalid runtime manifest: Bundled Python manifest points to a missing interpreter or unusable interpreter: ${executable}`, { cause: error });
    }
  }
  for (const candidate of [
    ...getVersionedBundledPythonCandidates(backendRoot, platform),
    ...getBundledPythonCandidates(backendRoot, platform)
  ]) {
    try { return usableInterpreter(backendRoot, candidate, platform); }
    catch { /* Only absent manifests admit legacy discovery, with the same file boundary. */ }
  }
  throw new Error(`No bundled Python runtime found under ${path.join(backendRoot, "python")}.`);
}

function buildRuntimeManifest(backendRoot, runtimeInfo) {
  return {
    schemaVersion: 1,
    python: {
      version: runtimeInfo.version,
      root: toManifestPath(backendRoot, runtimeInfo.root),
      executable: toManifestPath(backendRoot, runtimeInfo.executable),
      purelib: toManifestPath(backendRoot, runtimeInfo.purelib),
      scripts: toManifestPath(backendRoot, runtimeInfo.scripts)
    },
    launcher: {
      cwd: ".",
      managePy: "manage.py",
      sourceRoot: "src",
      // Consumers should derive DJANGO_SETTINGS_MODULE from this
      // structural value instead of treating it as external input.
      settingsModule: "desktop_django_starter.settings.packaged",
      environment: [
        "DESKTOP_DJANGO_APP_DATA_DIR",
        "DESKTOP_DJANGO_AUTH_TOKEN",
        "DESKTOP_DJANGO_BUNDLE_DIR",
        "DESKTOP_DJANGO_HOST",
        "DESKTOP_DJANGO_PORT",
        "PYTHONUNBUFFERED"
      ]
    }
  };
}

function writeRuntimeManifest(backendRoot, runtimeInfo) {
  const manifestPath = getRuntimeManifestPath(backendRoot);
  const manifest = buildRuntimeManifest(backendRoot, runtimeInfo);
  fs.writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
  return manifestPath;
}

module.exports = {
  DEFAULT_BUNDLED_PYTHON_VERSION,
  buildRuntimeManifest,
  fromManifestPath,
  getBundledPythonCandidates,
  getVersionedBundledPythonCandidates,
  getRuntimeManifestPath,
  loadRuntimeManifest,
  resolveBundledPythonExecutable,
  toManifestPath,
  writeRuntimeManifest
};
