const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const assert = require("node:assert/strict");

const {
  buildRuntimeManifest,
  fromManifestPath,
  getBundledPythonCandidates,
  getVersionedBundledPythonCandidates,
  loadRuntimeManifest,
  resolveBundledPythonExecutable,
  toManifestPath,
  writeRuntimeManifest
} = require("./bundled-python.cjs");

function withTempBackend(testFn) {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "desktop-django-starter-"));
  try {
    return testFn(tempRoot);
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
}

test("buildRuntimeManifest records backend-relative launcher paths", () => {
  withTempBackend((backendRoot) => {
    const runtimeInfo = {
      version: "3.12.13",
      root: path.join(backendRoot, "python"),
      executable: path.join(backendRoot, "python", "bin", "python3"),
      purelib: path.join(backendRoot, "python", "lib", "python3.12", "site-packages"),
      scripts: path.join(backendRoot, "python", "bin")
    };

    const manifest = buildRuntimeManifest(backendRoot, runtimeInfo);

    assert.equal(manifest.python.root, "python");
    assert.equal(manifest.python.executable, "python/bin/python3");
    assert.equal(
      manifest.python.purelib,
      "python/lib/python3.12/site-packages"
    );
    assert.equal(manifest.launcher.managePy, "manage.py");
    assert.equal(manifest.launcher.sourceRoot, "src");
  });
});

test("manifest paths use forward slashes and round-trip on read", () => {
  withTempBackend((backendRoot) => {
    const executable = path.join(backendRoot, "python", "bin", "python3");

    assert.equal(toManifestPath(backendRoot, executable), "python/bin/python3");
    assert.equal(fromManifestPath(backendRoot, "python/bin/python3"), executable);
  });
});

test("resolveBundledPythonExecutable prefers the staged manifest", () => {
  withTempBackend((backendRoot) => {
    const executable = path.join(backendRoot, "python", "bin", "python3");
    fs.mkdirSync(path.dirname(executable), { recursive: true });
    fs.writeFileSync(executable, "");

    writeRuntimeManifest(backendRoot, {
      version: "3.12.13",
      root: path.join(backendRoot, "python"),
      executable,
      purelib: path.join(backendRoot, "python", "lib", "python3.12", "site-packages"),
      scripts: path.join(backendRoot, "python", "bin")
    });

    const resolved = resolveBundledPythonExecutable(backendRoot, process.platform);

    assert.equal(resolved, executable);
    assert.equal(loadRuntimeManifest(backendRoot).python.executable, "python/bin/python3");
  });
});

test("getBundledPythonCandidates retains Windows and POSIX fallback paths", () => {
  withTempBackend((backendRoot) => {
    assert.deepEqual(getBundledPythonCandidates(backendRoot, "win32"), [
      path.join(backendRoot, "python", "python.exe"),
      path.join(backendRoot, "python", "Scripts", "python.exe")
    ]);
    assert.deepEqual(getBundledPythonCandidates(backendRoot, "linux"), [
      path.join(backendRoot, "python", "bin", "python3"),
      path.join(backendRoot, "python", "bin", "python")
    ]);
  });
});

test("resolveBundledPythonExecutable prefers a versioned staged binary", () => {
  withTempBackend((backendRoot) => {
    const binRoot = path.join(backendRoot, "python", "bin");
    const versionedExecutable = path.join(binRoot, "python3.12");
    const olderExecutable = path.join(binRoot, "python3.9");
    fs.mkdirSync(binRoot, { recursive: true });
    fs.writeFileSync(versionedExecutable, "");
    fs.writeFileSync(olderExecutable, "");

    assert.deepEqual(getVersionedBundledPythonCandidates(backendRoot, "linux"), [
      versionedExecutable,
      olderExecutable
    ]);
    assert.equal(resolveBundledPythonExecutable(backendRoot, "linux"), versionedExecutable);
  });
});

test("resolveBundledPythonExecutable throws when the manifest target is missing", () => {
  withTempBackend((backendRoot) => {
    writeRuntimeManifest(backendRoot, {
      version: "3.12.13",
      root: path.join(backendRoot, "python"),
      executable: path.join(backendRoot, "python", "bin", "python3"),
      purelib: path.join(backendRoot, "python", "lib", "python3.12", "site-packages"),
      scripts: path.join(backendRoot, "python", "bin")
    });

    assert.throws(
      () => resolveBundledPythonExecutable(backendRoot, process.platform),
      /Bundled Python manifest points to a missing interpreter/
    );
  });
});
