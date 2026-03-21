const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const assert = require("node:assert/strict");

const { materializeSymlinks } = require("./materialize-symlinks.cjs");

function withTempRoot(testFn) {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "desktop-django-starter-symlink-"));
  try {
    return testFn(tempRoot);
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
}

test("materializeSymlinks replaces file symlinks with copied files", () => {
  withTempRoot((rootPath) => {
    const sourceDir = path.join(rootPath, "source");
    const bundleDir = path.join(rootPath, "bundle");
    const sourceFile = path.join(sourceDir, "python3");
    const linkPath = path.join(bundleDir, "python");

    fs.mkdirSync(sourceDir, { recursive: true });
    fs.mkdirSync(bundleDir, { recursive: true });
    fs.writeFileSync(sourceFile, "python-binary");
    fs.symlinkSync(sourceFile, linkPath);

    materializeSymlinks(bundleDir);

    assert.equal(fs.lstatSync(linkPath).isSymbolicLink(), false);
    assert.equal(fs.readFileSync(linkPath, "utf8"), "python-binary");
  });
});

test("materializeSymlinks replaces directory symlinks and nested links", () => {
  withTempRoot((rootPath) => {
    const sourceDir = path.join(rootPath, "source");
    const sourcePackageDir = path.join(sourceDir, "package");
    const sourceFile = path.join(sourcePackageDir, "python3.12");
    const nestedLink = path.join(sourcePackageDir, "python3");
    const bundleDir = path.join(rootPath, "bundle");
    const linkPath = path.join(bundleDir, "python");

    fs.mkdirSync(sourcePackageDir, { recursive: true });
    fs.mkdirSync(bundleDir, { recursive: true });
    fs.writeFileSync(sourceFile, "python-runtime");
    fs.symlinkSync(sourceFile, nestedLink);
    fs.symlinkSync(sourcePackageDir, linkPath);

    materializeSymlinks(bundleDir);

    assert.equal(fs.lstatSync(linkPath).isSymbolicLink(), false);
    assert.equal(fs.lstatSync(path.join(linkPath, "python3")).isSymbolicLink(), false);
    assert.equal(fs.readFileSync(path.join(linkPath, "python3"), "utf8"), "python-runtime");
  });
});

test("materializeSymlinks raises a clear error for broken symlinks", () => {
  withTempRoot((rootPath) => {
    const bundleDir = path.join(rootPath, "bundle");
    const linkPath = path.join(bundleDir, "python");

    fs.mkdirSync(bundleDir, { recursive: true });
    fs.symlinkSync(path.join(rootPath, "missing-python"), linkPath);

    assert.throws(
      () => materializeSymlinks(bundleDir),
      /Broken symlink in staged runtime/
    );
  });
});

test("materializeSymlinks leaves normal files untouched", () => {
  withTempRoot((rootPath) => {
    const bundleDir = path.join(rootPath, "bundle");
    const filePath = path.join(bundleDir, "runtime-manifest.json");

    fs.mkdirSync(bundleDir, { recursive: true });
    fs.writeFileSync(filePath, "{\"schemaVersion\":1}\n");

    materializeSymlinks(bundleDir);

    assert.equal(fs.readFileSync(filePath, "utf8"), "{\"schemaVersion\":1}\n");
  });
});
