const fs = require("node:fs");
const path = require("node:path");

const DEFAULT_BUNDLED_PYTHON_VERSION = "3.12";
const RUNTIME_MANIFEST_FILENAME = "runtime-manifest.json";

function toManifestPath(backendRoot, targetPath) {
  return path.relative(backendRoot, targetPath).split(path.sep).join("/");
}

function fromManifestPath(backendRoot, targetPath) {
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

function loadRuntimeManifest(backendRoot) {
  const manifestPath = getRuntimeManifestPath(backendRoot);
  if (!fs.existsSync(manifestPath)) {
    return null;
  }

  return JSON.parse(fs.readFileSync(manifestPath, "utf8"));
}

function resolveBundledPythonExecutable(backendRoot, platform = process.platform) {
  const manifest = loadRuntimeManifest(backendRoot);
  if (manifest?.python?.executable) {
    const manifestExecutable = fromManifestPath(backendRoot, manifest.python.executable);
    if (fs.existsSync(manifestExecutable)) {
      return manifestExecutable;
    }

    throw new Error(
      `Bundled Python manifest points to a missing interpreter: ${manifestExecutable}`
    );
  }

  const bundledPython = [
    ...getVersionedBundledPythonCandidates(backendRoot, platform),
    ...getBundledPythonCandidates(backendRoot, platform)
  ]
    .find((candidate) => fs.existsSync(candidate));
  if (bundledPython) {
    return bundledPython;
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
        "DESKTOP_DJANGO_BUNDLE_DIR",
        "DESKTOP_DJANGO_HOST",
        "DESKTOP_DJANGO_PORT",
        "DJANGO_SECRET_KEY",
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
