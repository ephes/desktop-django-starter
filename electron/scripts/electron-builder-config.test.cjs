const test = require("node:test");
const assert = require("node:assert/strict");

const config = require("../electron-builder.config.cjs");

test("electron-builder config ships the staged backend as a packaged resource", () => {
  assert.equal(config.directories.output, "dist");
  assert.deepEqual(config.files, [
    "main.js",
    "package.json",
    "preload.cjs",
    "scripts/bundled-python.cjs"
  ]);
  assert.deepEqual(config.extraResources, [
    {
      from: ".stage/backend",
      to: "backend",
      filter: ["**/*"]
    }
  ]);
});

test("electron-builder config keeps per-platform artifact names explicit", () => {
  assert.equal(config.mac.artifactName, "desktop-django-starter-macos-${version}-${arch}.${ext}");
  assert.equal(
    config.win.artifactName,
    "desktop-django-starter-windows-${version}-${arch}.${ext}"
  );
  assert.equal(
    config.linux.artifactName,
    "desktop-django-starter-linux-${version}-${arch}.${ext}"
  );
});
