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

for (const operation of ['copyFileSync', 'cpSync', 'chmodSync']) {
  test(`materialization preserves original link when ${operation} fails`, () => {
    withTempRoot(root => {
      const target = path.join(root, 'target');
      const bundle = path.join(root, 'bundle');
      const link = path.join(bundle, 'python');
      fs.mkdirSync(bundle);
      if (operation === 'cpSync') {
        fs.mkdirSync(target);
        fs.writeFileSync(path.join(target, 'marker'), 'target');
      } else {
        fs.writeFileSync(target, 'target');
      }
      fs.symlinkSync(target, link, operation === 'cpSync' ? 'junction' : 'file');
      const original = fs[operation];
      let injected = 0;
      fs[operation] = (source, destination) => {
        injected++;
        if (operation === 'cpSync') {
          fs.mkdirSync(destination, { recursive: true });
          fs.writeFileSync(path.join(destination, 'partial'), 'partial');
        } else if (operation === 'copyFileSync') {
          fs.writeFileSync(destination, 'partial');
        }
        throw new Error(`injected ${operation}`);
      };
      try {
        assert.throws(() => materializeSymlinks(bundle), /injected/);
      } finally {
        fs[operation] = original;
      }
      assert.equal(injected, 1);
      assert.ok(fs.lstatSync(link).isSymbolicLink());
      assert.equal(fs.realpathSync(link), fs.realpathSync(target));
      assert.deepEqual(fs.readdirSync(bundle), ['python']);
      assert.equal(fs.readFileSync(operation === 'cpSync' ? path.join(target, 'marker') : target, 'utf8'), 'target');
    });
  });
}

test('materialization keeps executable permissions', () => withTempRoot(root => {
  const target = path.join(root, 'target');
  const bundle = path.join(root, 'bundle');
  fs.mkdirSync(bundle);
  fs.writeFileSync(target, 'executable');
  fs.chmodSync(target, 0o755);
  const expected = fs.statSync(target).mode & 0o777;
  fs.symlinkSync(target, path.join(bundle, 'python'), 'file');
  materializeSymlinks(bundle);
  assert.equal(fs.statSync(path.join(bundle, 'python')).mode & 0o777, expected);
}));


for (const kind of ['file', 'directory']) {
  test(`materialization restores ${kind} link if publication fails`, () => withTempRoot(root => {
    const target = path.join(root, 'target');
    const bundle = path.join(root, 'bundle');
    const link = path.join(bundle, 'python');
    fs.mkdirSync(bundle);
    if (kind === 'directory') fs.mkdirSync(target);
    else fs.writeFileSync(target, 'target');
    fs.symlinkSync(target, link, kind === 'directory' ? 'junction' : 'file');
    const originalRename = fs.renameSync;
    let injected = false;
    fs.renameSync = (source, destination) => {
      if (destination === link && !injected) {
        injected = true;
        throw new Error('injected publication failure');
      }
      return originalRename(source, destination);
    };
    try {
      assert.throws(() => materializeSymlinks(bundle), /injected publication failure/);
    } finally {
      fs.renameSync = originalRename;
    }
    assert.equal(injected, true);
    assert.ok(fs.lstatSync(link).isSymbolicLink());
    assert.equal(fs.realpathSync(link), fs.realpathSync(target));
    assert.deepEqual(fs.readdirSync(bundle), ['python']);
  }));
}
