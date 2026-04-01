const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const electronRoot = path.resolve(__dirname, "..");
const iconDir = path.join(electronRoot, "assets", "icons");
const svgPath = path.join(iconDir, "flying-stable-app-icon.svg");
const pngPath = path.join(iconDir, "app-icon.png");
const icnsPath = path.join(iconDir, "app-icon.icns");

function requireCommand(command, installHint) {
  try {
    execFileSync(command, ["--version"], { stdio: "ignore" });
  } catch (_error) {
    throw new Error(`${command} is required to regenerate Electron app icons. ${installHint}`);
  }
}

function run(command, args) {
  execFileSync(command, args, { stdio: "inherit" });
}

function renderPng(size, outputPath) {
  run("rsvg-convert", [
    "--width", String(size),
    "--height", String(size),
    svgPath,
    "--output", outputPath
  ]);
}

function buildIcns() {
  if (os.platform() !== "darwin") {
    return;
  }

  const iconsetDir = path.join(iconDir, "app-icon.iconset");
  fs.rmSync(iconsetDir, { recursive: true, force: true });
  fs.mkdirSync(iconsetDir, { recursive: true });

  for (const size of [16, 32, 128, 256, 512]) {
    renderPng(size, path.join(iconsetDir, `icon_${size}x${size}.png`));
    renderPng(size * 2, path.join(iconsetDir, `icon_${size}x${size}@2x.png`));
  }

  run("iconutil", ["-c", "icns", iconsetDir, "-o", icnsPath]);
  fs.rmSync(iconsetDir, { recursive: true, force: true });
}

fs.mkdirSync(iconDir, { recursive: true });
requireCommand("rsvg-convert", "Install librsvg so `rsvg-convert` is available on PATH.");
renderPng(512, pngPath);
buildIcns();
