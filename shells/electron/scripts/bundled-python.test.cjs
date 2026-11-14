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
    fs.writeFileSync(executable, "", { mode: 0o755 });

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
    fs.writeFileSync(versionedExecutable, "", { mode: 0o755 });
    fs.writeFileSync(olderExecutable, "", { mode: 0o755 });

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

function validManifest(root) {
  return buildRuntimeManifest(root, {
    version: "3.14.3", root: path.join(root, "python"),
    executable: path.join(root, "python/bin/python3"),
    purelib: path.join(root, "python/lib/site-packages"), scripts: path.join(root, "python/bin")
  });
}

for (const value of ["../outside", "/usr/bin/python3", "C:/python.exe", "python/../outside", "python\\bin\\python", "python//bin/python", "python/bin/python:stream"]) {
  test(`manifest refuses nonportable executable ${value}`, () => withTempBackend(root => {
    const manifest = validManifest(root);
    manifest.python.executable = value;
    fs.writeFileSync(path.join(root, "runtime-manifest.json"), JSON.stringify(manifest));
    assert.throws(() => resolveBundledPythonExecutable(root), /Invalid runtime manifest/);
  }));
}

for (const kind of ["directory", "non-executable", "escaping-link", "escaping-root"]) {
  test(`manifest refuses ${kind} interpreter`, { skip: kind === "non-executable" && process.platform === "win32" }, () => withTempBackend(root => {
    const executable = path.join(root, "python/bin/python3");
    fs.mkdirSync(path.dirname(executable), { recursive: true });
    if (kind === "directory") fs.mkdirSync(executable);
    else if (kind === "escaping-link" || kind === "escaping-root") {
      const outside = path.join(root, "outside");
      fs.writeFileSync(outside, "outside", { mode: 0o755 });
      if (kind === "escaping-root") {
        fs.rmSync(path.join(root, "python"), { recursive: true });
        fs.mkdirSync(path.join(root, "external/bin"), { recursive: true });
        fs.copyFileSync(outside, path.join(root, "external/bin/python3"));
        fs.symlinkSync(path.join(root, "external"), path.join(root, "python"), "junction");
      } else fs.symlinkSync(outside, executable);
    } else fs.writeFileSync(executable, "x", { mode: 0o600 });
    fs.writeFileSync(path.join(root, "runtime-manifest.json"), JSON.stringify(validManifest(root)));
    assert.throws(() => resolveBundledPythonExecutable(root), /Invalid runtime manifest/);
  }));
}

for (const malformed of [null, [], {}, { schemaVersion: 2 }, { schemaVersion: 1, python: { executable: 12 } }]) {
  test(`existing malformed manifest never falls back: ${JSON.stringify(malformed)}`, () => withTempBackend(root => {
    fs.mkdirSync(path.join(root, "python/bin"), { recursive: true });
    fs.writeFileSync(path.join(root, "python/bin/python3"), "legacy", { mode: 0o755 });
    fs.writeFileSync(path.join(root, "runtime-manifest.json"), JSON.stringify(malformed));
    assert.throws(() => resolveBundledPythonExecutable(root), /Invalid runtime manifest/);
  }));
}

for (const kind of ["oversized", "directory", "symlink", "fifo", "broken-link"]) {
  test(`manifest rejects ${kind} file before reading`, () => withTempBackend(root => {
    const manifestPath = path.join(root, "runtime-manifest.json");
    if (kind === "directory") fs.mkdirSync(manifestPath);
    else if (kind === "fifo") {
      if (process.platform === "win32") return;
      require("node:child_process").execFileSync("mkfifo", [manifestPath]);
    } else if (kind.includes("link")) {
      const target = path.join(root, "target");
      if (kind !== "broken-link") fs.writeFileSync(target, JSON.stringify(validManifest(root)));
      fs.symlinkSync(target, manifestPath);
    } else fs.writeFileSync(manifestPath, " ".repeat(65537));
    assert.throws(() => loadRuntimeManifest(root), /Invalid runtime manifest/);
  }));
}

test("relocated manifest launches its own interpreter with internal symlink", () => withTempBackend(root => {
  if (process.platform === "win32") return;
  const source = path.join(root, "source");
  const relocated = path.join(root, "relocated");
  fs.mkdirSync(path.join(source, "python/bin"), { recursive: true });
  fs.writeFileSync(path.join(source, "python/bin/python3.14"), "#!/bin/sh\nprintf relocated", { mode: 0o755 });
  fs.symlinkSync("python3.14", path.join(source, "python/bin/python3"));
  fs.writeFileSync(path.join(source, "runtime-manifest.json"), JSON.stringify(validManifest(source)));
  fs.renameSync(source, relocated);
  const executable = resolveBundledPythonExecutable(relocated);
  assert.equal(require("node:child_process").execFileSync(executable, { encoding: "utf8" }), "relocated");
}));

for (const field of ["schemaVersion", "python", "executable", "purelib", "scripts", "launcher"]) {
  test(`complete manifest refuses invalid ${field} without legacy fallback`, () => withTempBackend(root => {
    const manifest = validManifest(root);
    if (field === "schemaVersion") manifest.schemaVersion = 2;
    else if (field === "python" || field === "launcher") manifest[field] = [];
    else manifest.python[field] = 12;
    fs.mkdirSync(path.join(root, "python/bin"), { recursive: true });
    fs.writeFileSync(path.join(root, "python/bin/python3"), "legacy", { mode: 0o755 });
    fs.writeFileSync(path.join(root, "runtime-manifest.json"), JSON.stringify(manifest));
    assert.throws(() => resolveBundledPythonExecutable(root), /Invalid runtime manifest/);
  }));
}

test("legacy discovery rejects directories and escaping interpreter links", () => withTempBackend(root => {
  const executable = path.join(root, "python/bin/python3");
  fs.mkdirSync(executable, { recursive: true });
  assert.throws(() => resolveBundledPythonExecutable(root), /No bundled Python/);
  fs.rmdirSync(executable);
  fs.writeFileSync(path.join(root, "external"), "external", { mode: 0o755 });
  fs.symlinkSync(path.join(root, "external"), executable);
  assert.throws(() => resolveBundledPythonExecutable(root), /No bundled Python/);
}));
