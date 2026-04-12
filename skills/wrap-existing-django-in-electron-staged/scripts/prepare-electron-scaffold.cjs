#!/usr/bin/env node

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const IGNORED_DIRS = new Set([
  ".git",
  ".hg",
  ".svn",
  ".stage",
  ".venv",
  "build",
  "dist",
  "electron",
  "node_modules",
  "venv"
]);
const STARTER_TEMPLATE_CHECKSUMS = {
  "main.js": "dac21bc8fc6759c059969c4e52f3e18b791001a2a6c276617af9d1875bd9d2d9",
  "scripts/electron-builder-config.cjs": "bf3ed6ef9695d9791e8941c49653b485108379ad08431632c196c9921ddab92c",
  "scripts/launch-electron.cjs": "c383e90dc8ab279dcff53f4ba67375e17917bc7878df13a0a12e1b5244b9b0da",
  "scripts/stage-backend.cjs": "949b7b53996d592ce22dfbe2c4746e81b50becf38e0ebfc6ee88b7d6837f873f",
  "scripts/bundled-python.cjs": "69008cc5b84665fc66b9aa3a6e81e8f3daee41ac208c533b78b9b7fd9274b071"
};

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(1);
}

function fileSha256(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function verifyStarterTemplateCompatibility(electronRoot) {
  const mismatches = [];

  for (const [relativePath, expectedSha256] of Object.entries(STARTER_TEMPLATE_CHECKSUMS)) {
    const absolutePath = path.join(electronRoot, relativePath);
    if (!fs.existsSync(absolutePath)) {
      mismatches.push(`${relativePath}: missing copied starter template`);
      continue;
    }

    const actualSha256 = fileSha256(absolutePath);
    if (actualSha256 !== expectedSha256) {
      mismatches.push(
        `${relativePath}: expected ${expectedSha256}, got ${actualSha256}`
      );
    }
  }

  if (mismatches.length > 0) {
    fail(
      "starter Electron template compatibility check failed before scaffolding.\n"
      + "The staged scaffold is pinned to the current starter Electron templates.\n"
      + "If these template changes are intentional, update the checksum guard and the"
      + " matching rewrite logic in prepare-electron-scaffold.cjs.\n"
      + mismatches.map((entry) => `- ${entry}`).join("\n")
    );
  }
}

function replaceRequired(source, searchValue, replaceValue, filePath) {
  if (!source.includes(searchValue)) {
    fail(`expected scaffold text not found in ${filePath}: ${searchValue}`);
  }

  return source.replace(searchValue, replaceValue);
}

function replaceAllRequired(source, searchValue, replaceValue, filePath) {
  if (!source.includes(searchValue)) {
    fail(`expected scaffold text not found in ${filePath}: ${searchValue}`);
  }

  return source.split(searchValue).join(replaceValue);
}

function normalizeRelative(filePath) {
  return filePath.split(path.sep).join("/");
}

function walkFiles(rootDir, callback, relativeDir = "") {
  for (const entry of fs.readdirSync(path.join(rootDir, relativeDir), { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (IGNORED_DIRS.has(entry.name)) {
        continue;
      }

      walkFiles(rootDir, callback, path.join(relativeDir, entry.name));
      continue;
    }

    callback(path.join(relativeDir, entry.name));
  }
}

function readProjectName(targetRoot) {
  const pyprojectPath = path.join(targetRoot, "pyproject.toml");
  if (fs.existsSync(pyprojectPath)) {
    const pyproject = fs.readFileSync(pyprojectPath, "utf8");
    const projectSection = pyproject.match(/^\[project\][\s\S]*?(?=^\[|\s*$)/m);
    const nameMatch = projectSection?.[0]?.match(/^\s*name\s*=\s*"([^"]+)"/m);
    if (nameMatch?.[1]) {
      return nameMatch[1].trim();
    }
  }

  return path.basename(targetRoot).replace(/-(clean|tmp|temp|sandbox|worktree)$/i, "");
}

function toSlug(projectName) {
  return projectName
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    || "desktop-django-app";
}

function toProductName(projectName) {
  return projectName
    .replace(/[-_]+/g, " ")
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(" ");
}

function toAppId(slug) {
  const compact = slug.replace(/-/g, "");
  return `com.example.${compact || "desktopdjangoapp"}`;
}

function toIdentifier(slug) {
  return slug.replace(/-/g, "_") || "desktop_django_app";
}

function repoJoin(relativePath) {
  const normalized = normalizeRelative(relativePath);
  if (!normalized || normalized === ".") {
    return "repoRoot";
  }

  const parts = normalized.split("/").map((part) => JSON.stringify(part)).join(", ");
  return `path.join(repoRoot, ${parts})`;
}

function backendJoin(relativePath) {
  const normalized = normalizeRelative(relativePath);
  if (!normalized || normalized === ".") {
    return "backendRoot";
  }

  const parts = normalized.split("/").map((part) => JSON.stringify(part)).join(", ");
  return `path.join(backendRoot, ${parts})`;
}

function inferPackagedSettingsModule(developmentSettingsModule) {
  if (developmentSettingsModule.endsWith(".settings")) {
    return developmentSettingsModule.replace(/\.settings$/, ".packaged_settings");
  }

  return `${developmentSettingsModule}.packaged_settings`;
}

function inferProjectPackageModule(settingsModule) {
  const parts = settingsModule.split(".");
  if (parts.length < 2) {
    fail(`unable to infer package module from settings module: ${settingsModule}`);
  }

  return parts.slice(0, -1).join(".");
}

function inferSettingsLayout(targetRoot, manageRoot, settingsModule) {
  const settingsPath = resolveModuleFilePath(manageRoot, settingsModule);
  const settingsModulePath = resolveModulePath(manageRoot, settingsModule);
  const settingsDir = normalizeRelative(path.posix.dirname(settingsPath));
  const parts = settingsModule.split(".");

  if (parts.length < 2) {
    fail(`unable to infer settings layout from settings module: ${settingsModule}`);
  }

  const settingsContainerPath = parts.length <= 2 ? settingsModulePath : settingsDir;
  const settingsPackageInit = normalizeRelative(
    path.posix.join(settingsContainerPath, "__init__.py")
  );
  const usesSettingsPackage = fs.existsSync(path.join(targetRoot, settingsPackageInit));

  if (usesSettingsPackage) {
    if (parts.length < 3) {
      fail(`settings package layout is ambiguous for settings module: ${settingsModule}`);
    }

    const settingsContainerModule = parts.slice(0, -1).join(".");
    const projectPackageModule = parts.slice(0, -2).join(".");
    return {
      projectPackageModule,
      packagedSettingsModule: `${projectPackageModule}.packaged_settings`,
      settingsBaseModule: `${settingsContainerModule}.base`,
      settingsBasePath: resolveModuleFilePath(manageRoot, `${settingsContainerModule}.base`),
      settingsContainerModule
    };
  }

  const projectPackageModule = inferProjectPackageModule(settingsModule);
  return {
    projectPackageModule,
    packagedSettingsModule: inferPackagedSettingsModule(settingsModule),
    settingsBaseModule: settingsModule,
    settingsBasePath: settingsPath,
    settingsContainerModule: null
  };
}

function resolveModulePath(manageRoot, moduleName) {
  const normalizedRoot = manageRoot ? normalizeRelative(manageRoot) : "";
  const modulePath = moduleName.split(".").join("/");
  return normalizeRelative(
    normalizedRoot ? path.posix.join(normalizedRoot, modulePath) : modulePath
  );
}

function resolveModuleFilePath(manageRoot, moduleName) {
  return `${resolveModulePath(manageRoot, moduleName)}.py`;
}

function findManageCandidates(targetRoot) {
  const candidates = [];

  walkFiles(targetRoot, (relativePath) => {
    if (path.basename(relativePath) !== "manage.py") {
      return;
    }

    const normalizedPath = normalizeRelative(relativePath);
    const source = fs.readFileSync(path.join(targetRoot, relativePath), "utf8");
    const uncommentedSource = source
      .split("\n")
      .filter((line) => !line.trimStart().startsWith("#"))
      .join("\n");
    const settingsMatch = uncommentedSource.match(
      /os\.environ(?:\.setdefault|\[[^\]]+\]\s*=)\(\s*["']DJANGO_SETTINGS_MODULE["']\s*,\s*["']([^"']+)["']\s*\)|os\.environ\[\s*["']DJANGO_SETTINGS_MODULE["']\s*\]\s*=\s*["']([^"']+)["']/
    );
    const settingsModule = settingsMatch?.[1]?.trim() || settingsMatch?.[2]?.trim();

    candidates.push({
      relativePath: normalizedPath,
      settingsModule: settingsModule || null
    });
  });

  return candidates;
}

function inferTargetConfig(targetRoot) {
  const manageCandidates = findManageCandidates(targetRoot)
    .filter((candidate) => candidate.settingsModule);

  if (manageCandidates.length === 0) {
    fail(`unable to infer a usable manage.py from ${targetRoot}`);
  }

  manageCandidates.sort((left, right) => {
    const leftScore = /^tests?\./.test(left.settingsModule) ? 1 : 0;
    const rightScore = /^tests?\./.test(right.settingsModule) ? 1 : 0;
    if (leftScore !== rightScore) {
      return leftScore - rightScore;
    }

    return left.relativePath.localeCompare(right.relativePath);
  });

  const selectedManage = manageCandidates[0];
  const manageDir = path.posix.dirname(selectedManage.relativePath);
  const manageRoot = manageDir === "." ? "" : manageDir;
  const settingsLayout = inferSettingsLayout(targetRoot, manageRoot, selectedManage.settingsModule);
  const packagedRoots = [];

  if (manageRoot) {
    packagedRoots.push(manageRoot);
  }

  if (fs.existsSync(path.join(targetRoot, "src"))) {
    packagedRoots.push("src");
  }

  const seedDatabasePath = manageRoot
    ? path.posix.join(manageRoot, "db.sqlite3")
    : "db.sqlite3";
  const seedMediaPath = manageRoot
    ? path.posix.join(manageRoot, "media")
    : "media";

  return {
    developmentManagePath: selectedManage.relativePath,
    packagedManagePath: selectedManage.relativePath,
    developmentSettingsModule: selectedManage.settingsModule,
    packagedSettingsModule: settingsLayout.packagedSettingsModule,
    packageModule: settingsLayout.projectPackageModule,
    packagePath: resolveModulePath(manageRoot, settingsLayout.projectPackageModule),
    developmentSettingsPath: resolveModuleFilePath(manageRoot, selectedManage.settingsModule),
    packagedSettingsPath: resolveModuleFilePath(manageRoot, settingsLayout.packagedSettingsModule),
    settingsBaseModule: settingsLayout.settingsBaseModule,
    settingsBasePath: settingsLayout.settingsBasePath,
    settingsContainerModule: settingsLayout.settingsContainerModule,
    urlsPath: resolveModuleFilePath(manageRoot, `${settingsLayout.projectPackageModule}.urls`),
    desktopMiddlewarePath: resolveModuleFilePath(manageRoot, `${settingsLayout.projectPackageModule}.desktop_middleware`),
    desktopRuntimePath: resolveModuleFilePath(manageRoot, `${settingsLayout.projectPackageModule}.desktop_runtime`),
    packagedRoots,
    seedDatabasePath: fs.existsSync(path.join(targetRoot, seedDatabasePath)) ? seedDatabasePath : null,
    seedMediaPath: fs.existsSync(path.join(targetRoot, seedMediaPath)) ? seedMediaPath : null
  };
}

function updatePackageJson(electronRoot, projectName, slug) {
  const packageJsonPath = path.join(electronRoot, "package.json");
  const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, "utf8"));

  packageJson.name = `${slug}-electron`;
  packageJson.description = `Electron shell for the ${projectName} app.`;
  packageJson.scripts["stage-backend"] = "node ./scripts/stage-backend.cjs";

  fs.writeFileSync(packageJsonPath, `${JSON.stringify(packageJson, null, 2)}\n`);
}

function updateBuilderConfig(electronRoot, productName, slug) {
  const builderConfigPath = path.join(electronRoot, "scripts", "electron-builder-config.cjs");
  let source = fs.readFileSync(builderConfigPath, "utf8");

  source = replaceRequired(
    source,
    'appId: "io.github.joww12.desktop-django-starter",',
    `appId: "${toAppId(slug)}",`,
    builderConfigPath
  );
  source = replaceRequired(
    source,
    'productName: "Desktop Django Starter",',
    `productName: "${productName}",`,
    builderConfigPath
  );
  source = replaceRequired(
    source,
    'artifactName: "desktop-django-starter-macos-${version}-${arch}.${ext}",',
    `artifactName: "${slug}-macos-\${version}-\${arch}.\${ext}",`,
    builderConfigPath
  );
  source = replaceRequired(
    source,
    'artifactName: "desktop-django-starter-windows-${version}-${arch}.${ext}",',
    `artifactName: "${slug}-windows-\${version}-\${arch}.\${ext}",`,
    builderConfigPath
  );
  source = replaceRequired(
    source,
    'artifactName: "desktop-django-starter-linux-${version}-${arch}.${ext}"',
    `artifactName: "${slug}-linux-\${version}-\${arch}.\${ext}"`,
    builderConfigPath
  );
  source = replaceRequired(
    source,
    'from: "../../scripts",',
    'from: "./scripts",',
    builderConfigPath
  );
  source = replaceRequired(
    source,
    'from: "../../.stage/backend",',
    'from: "../.stage/backend",',
    builderConfigPath
  );

  fs.writeFileSync(builderConfigPath, source);
}

function writeWrappedSplash(electronRoot, productName) {
  const splashPath = path.join(electronRoot, "assets", "wrapped-splash.html");
  const escapedTitle = productName
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  const source = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${escapedTitle}</title>
  <style>
    :root {
      --canvas: #f7f4ee;
      --panel: #ffffff;
      --text: #302620;
      --muted: #8b8178;
      --accent: #b99152;
      --shadow: rgba(48, 38, 32, 0.12);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background:
        radial-gradient(circle at top, rgba(185, 145, 82, 0.14), transparent 40%),
        linear-gradient(180deg, #fbf9f5 0%, var(--canvas) 100%);
      color: var(--text);
      font-family: "Inter", "Helvetica Neue", Arial, sans-serif;
    }

    .panel {
      min-width: 18rem;
      padding: 2.5rem 2.75rem;
      border-radius: 1.5rem;
      background: color-mix(in srgb, var(--panel) 88%, transparent);
      box-shadow: 0 1.5rem 3rem var(--shadow);
      text-align: center;
    }

    .title {
      margin: 0;
      font-size: 1.2rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    .status {
      margin: 0.85rem 0 0;
      color: var(--muted);
      font-size: 0.9rem;
    }

    .loader {
      display: inline-flex;
      gap: 0.5rem;
      margin-top: 1.5rem;
    }

    .dot {
      width: 0.6rem;
      height: 0.6rem;
      border-radius: 999px;
      background: var(--accent);
      animation: pulse 1.2s ease-in-out infinite;
    }

    .dot:nth-child(2) { animation-delay: 0.15s; }
    .dot:nth-child(3) { animation-delay: 0.3s; }

    @keyframes pulse {
      0%, 80%, 100% { transform: translateY(0); opacity: 0.3; }
      40% { transform: translateY(-0.35rem); opacity: 1; }
    }
  </style>
</head>
<body>
  <main class="panel">
    <h1 class="title">${escapedTitle}</h1>
    <p class="status">Preparing the desktop shell…</p>
    <div class="loader" aria-hidden="true">
      <div class="dot"></div>
      <div class="dot"></div>
      <div class="dot"></div>
    </div>
  </main>
</body>
</html>
`;

  fs.writeFileSync(splashPath, source);
}

function updateLaunchScripts(electronRoot, targetConfig, slug) {
  const mainPath = path.join(electronRoot, "main.js");
  let mainSource = fs.readFileSync(mainPath, "utf8");
  mainSource = replaceRequired(
    mainSource,
    'const { app, BrowserWindow, dialog, ipcMain, nativeImage, shell } = require("electron");',
    'const { app, BrowserWindow, dialog, ipcMain, Menu, nativeImage, shell } = require("electron");',
    mainPath
  );
  mainSource = replaceRequired(
    mainSource,
    'function focusExistingWindow() {\n'
      + '  const existingWindow = mainWindow || splashWindow || BrowserWindow.getAllWindows()[0];\n'
      + '  if (!existingWindow) {\n'
      + '    return;\n'
      + '  }\n'
      + '\n'
      + '  if (existingWindow.isMinimized()) {\n'
      + '    existingWindow.restore();\n'
      + '  }\n'
      + '\n'
      + '  existingWindow.focus();\n'
      + '}\n',
    'function focusExistingWindow() {\n'
      + '  const existingWindow = mainWindow || splashWindow || BrowserWindow.getAllWindows()[0];\n'
      + '  if (!existingWindow) {\n'
      + '    return;\n'
      + '  }\n'
      + '\n'
      + '  if (existingWindow.isMinimized()) {\n'
      + '    existingWindow.restore();\n'
      + '  }\n'
      + '\n'
      + '  existingWindow.focus();\n'
      + '}\n'
      + '\n'
      + 'function getPrimaryAppUrl() {\n'
      + '  if (!currentAppUrl) {\n'
      + '    return null;\n'
      + '  }\n'
      + '\n'
      + '  return new URL("/", currentAppUrl).toString();\n'
      + '}\n'
      + '\n'
      + 'function navigateBack() {\n'
      + '  if (mainWindow && mainWindow.webContents.canGoBack()) {\n'
      + '    mainWindow.webContents.goBack();\n'
      + '  }\n'
      + '}\n'
      + '\n'
      + 'function navigateForward() {\n'
      + '  if (mainWindow && mainWindow.webContents.canGoForward()) {\n'
      + '    mainWindow.webContents.goForward();\n'
      + '  }\n'
      + '}\n'
      + '\n'
      + 'function navigateHome() {\n'
      + '  if (!mainWindow || mainWindow.isDestroyed()) {\n'
      + '    return;\n'
      + '  }\n'
      + '\n'
      + '  const homeUrl = getPrimaryAppUrl();\n'
      + '  if (homeUrl) {\n'
      + '    mainWindow.loadURL(homeUrl);\n'
      + '  }\n'
      + '}\n'
      + '\n'
      + 'function buildApplicationMenu() {\n'
      + '  const template = [\n'
      + '    ...(process.platform === "darwin" ? [{ role: "appMenu" }] : []),\n'
      + '    {\n'
      + '      label: "Navigate",\n'
      + '      submenu: [\n'
      + '        {\n'
      + '          label: "Home",\n'
      + '          accelerator: process.platform === "darwin" ? "Cmd+Shift+H" : "Alt+Home",\n'
      + '          click: () => navigateHome()\n'
      + '        },\n'
      + '        { type: "separator" },\n'
      + '        {\n'
      + '          label: "Back",\n'
      + '          accelerator: process.platform === "darwin" ? "Cmd+[" : "Alt+Left",\n'
      + '          click: () => navigateBack()\n'
      + '        },\n'
      + '        {\n'
      + '          label: "Forward",\n'
      + '          accelerator: process.platform === "darwin" ? "Cmd+]" : "Alt+Right",\n'
      + '          click: () => navigateForward()\n'
      + '        }\n'
      + '      ]\n'
      + '    },\n'
      + '    { role: "editMenu" },\n'
      + '    { role: "viewMenu" },\n'
      + '    { role: "windowMenu" }\n'
      + '  ];\n'
      + '\n'
      + '  return Menu.buildFromTemplate(template);\n'
      + '}\n'
      + '\n'
      + 'function applyApplicationMenu() {\n'
      + '  Menu.setApplicationMenu(buildApplicationMenu());\n'
      + '}\n',
    mainPath
  );
  mainSource = replaceRequired(
    mainSource,
    'const repoRoot = path.resolve(__dirname, "..", "..");',
    'const repoRoot = path.resolve(__dirname, "..");',
    mainPath
  );
  mainSource = replaceRequired(
    mainSource,
    '    : "Run `npm --prefix shells/electron run stage-backend` first.";',
    '    : "Run `npm --prefix electron run stage-backend` first.";',
    mainPath
  );
  mainSource = replaceRequired(
    mainSource,
    '  return path.join(backendRoot, "src", "desktop_django_starter", "templates", "splash.html");',
    '  return path.join(__dirname, "assets", "wrapped-splash.html");',
    mainPath
  );
  mainSource = replaceRequired(
    mainSource,
    '  const settingsModule = runtimeMode === "packaged"\n'
      + '    ? "desktop_django_starter.settings.packaged"\n'
      + '    : process.env.DJANGO_SETTINGS_MODULE || "desktop_django_starter.settings.local";',
    `  const settingsModule = runtimeMode === "packaged"\n`
      + `    ? "${targetConfig.packagedSettingsModule}"\n`
      + `    : process.env.DJANGO_SETTINGS_MODULE || "${targetConfig.developmentSettingsModule}";`,
    mainPath
  );
  mainSource = replaceRequired(
    mainSource,
    '  const environment = {\n'
      + '    ...process.env,\n'
      + '    DJANGO_SETTINGS_MODULE: settingsModule,\n'
      + '    DESKTOP_DJANGO_APP_DATA_DIR: app.getPath("userData"),\n'
      + '    DESKTOP_DJANGO_AUTH_TOKEN: authToken,\n'
      + '    DESKTOP_DJANGO_BUNDLE_DIR: backendRoot,\n'
      + '    DESKTOP_DJANGO_HOST: HOST,\n'
      + '    DESKTOP_DJANGO_PORT: String(port),\n'
      + '    PYTHONUNBUFFERED: "1"\n'
      + '  };',
    '  const environment = {\n'
      + '    ...process.env,\n'
      + '    DJANGO_SETTINGS_MODULE: settingsModule,\n'
      + '    DESKTOP_AUTO_LOGIN_ENABLED: process.env.DESKTOP_AUTO_LOGIN_ENABLED || "1",\n'
      + '    DESKTOP_AUTO_LOGIN_USERNAME: process.env.DESKTOP_AUTO_LOGIN_USERNAME || "",\n'
      + '    DESKTOP_DJANGO_APP_DATA_DIR: app.getPath("userData"),\n'
      + '    DESKTOP_DJANGO_AUTH_TOKEN: authToken,\n'
      + '    DESKTOP_DJANGO_BUNDLE_DIR: backendRoot,\n'
      + '    DESKTOP_DJANGO_HOST: HOST,\n'
      + '    DESKTOP_DJANGO_PORT: String(port),\n'
      + '    PYTHONUNBUFFERED: "1"\n'
      + '  };',
    mainPath
  );
  mainSource = replaceRequired(
    mainSource,
    'function buildManageInvocation(runtimeMode, backendRoot, manageArgs) {\n'
      + '  const { command, prefixArgs } = getPythonLaunchSpec(runtimeMode, backendRoot);\n'
      + '\n'
      + '  return {\n'
      + '    command,\n'
      + '    cwd: backendRoot,\n'
      + '    args: [...prefixArgs, "manage.py", ...manageArgs]\n'
      + '  };\n'
      + '}',
    'function getManagePyPath(_runtimeMode) {\n'
      + `  return ${JSON.stringify(targetConfig.packagedManagePath)};\n`
      + '}\n'
      + '\n'
      + 'function buildManageInvocation(runtimeMode, backendRoot, manageArgs) {\n'
      + '  const { command, prefixArgs } = getPythonLaunchSpec(runtimeMode, backendRoot);\n'
      + '\n'
      + '  return {\n'
      + '    command,\n'
      + '    cwd: backendRoot,\n'
      + '    args: [...prefixArgs, getManagePyPath(runtimeMode), ...manageArgs]\n'
      + '  };\n'
      + '}',
    mainPath
  );
  const packagedRequiredPaths = [
    `    ${backendJoin(targetConfig.packagedManagePath)},`,
    ...targetConfig.packagedRoots.map((relativePath) => `    ${backendJoin(relativePath)},`),
    '    path.join(backendRoot, "staticfiles"),',
    '    path.join(backendRoot, "python"),',
    "    getRuntimeManifestPath(backendRoot)"
  ].join("\n");
  mainSource = replaceRequired(
    mainSource,
    '  const requiredPaths = [\n'
      + '    path.join(backendRoot, "manage.py"),\n'
      + '    path.join(backendRoot, "src", "desktop_django_starter"),\n'
      + '    path.join(backendRoot, "src", "example_app"),\n'
      + '    path.join(backendRoot, "src", "tasks_demo"),\n'
      + '    path.join(backendRoot, "staticfiles"),\n'
      + '    path.join(backendRoot, "python"),\n'
      + '    getRuntimeManifestPath(backendRoot)\n'
      + '  ];',
    `  const requiredPaths = [\n${packagedRequiredPaths}\n  ];`,
    mainPath
  );
  mainSource = replaceRequired(
    mainSource,
    '    manageArgs: ["db_worker", "--queue-name", "default", "--worker-id", "desktop-django-starter"],',
    `    manageArgs: ["db_worker", "--queue-name", "default", "--worker-id", "${slug}"],`,
    mainPath
  );
  mainSource = replaceRequired(
    mainSource,
    '  // Start the worker only after Django is healthy so startup failures are\n'
      + '  // surfaced against a known-good migrated app database.\n'
      + '  await startTaskWorker(port, runtimeMode, backendRoot, authToken);',
    '  if (process.env.DESKTOP_DJANGO_ENABLE_TASK_WORKER === "1") {\n'
      + '    await startTaskWorker(port, runtimeMode, backendRoot, authToken);\n'
      + '  }',
    mainPath
  );
  mainSource = replaceAllRequired(
    mainSource,
    'backgroundColor: "#222121",',
    'backgroundColor: "#ffffff",',
    mainPath
  );
  mainSource = replaceRequired(
    mainSource,
    '  mainWindow = win;\n'
      + '  currentAppUrl = url;\n'
      + '  currentAuthToken = authToken;\n',
    '  mainWindow = win;\n'
      + '  currentAppUrl = url;\n'
      + '  currentAuthToken = authToken;\n'
      + '  applyApplicationMenu();\n',
    mainPath
  );
  mainSource = replaceRequired(
    mainSource,
    '      setApplicationIcon();\n'
      + '      await bootstrap();',
    '      setApplicationIcon();\n'
      + '      applyApplicationMenu();\n'
      + '      await bootstrap();',
    mainPath
  );
  fs.writeFileSync(mainPath, mainSource);

  const launchPath = path.join(electronRoot, "scripts", "launch-electron.cjs");
  let launchSource = fs.readFileSync(launchPath, "utf8");
  launchSource = replaceRequired(
    launchSource,
    'const repoRoot = path.resolve(electronRoot, "..", "..");',
    'const repoRoot = path.resolve(electronRoot, "..");',
    launchPath
  );
  fs.writeFileSync(launchPath, launchSource);
}

function updateStageBackendScript(electronRoot, targetConfig) {
  const stageBackendPath = path.join(electronRoot, "scripts", "stage-backend.cjs");
  let source = fs.readFileSync(stageBackendPath, "utf8");
  source = replaceRequired(
    source,
    'const repoRoot = path.resolve(__dirname, "..");',
    'const repoRoot = path.resolve(__dirname, "..", "..");',
    stageBackendPath
  );
  const stagedCopyLines = [
    `  fs.cpSync(${repoJoin(targetConfig.developmentManagePath)}, path.join(backendRoot, "manage.py"));`,
    ...targetConfig.packagedRoots.map((relativePath) => (
      `  fs.cpSync(${repoJoin(relativePath)}, ${backendJoin(relativePath)}, { recursive: true });`
    ))
  ].join("\n");
  source = replaceRequired(
    source,
    '  fs.cpSync(path.join(repoRoot, "manage.py"), path.join(backendRoot, "manage.py"));\n'
      + '  fs.cpSync(path.join(repoRoot, "src"), path.join(backendRoot, "src"), { recursive: true });',
    stagedCopyLines,
    stageBackendPath
  );
  source = replaceRequired(
    source,
    '      DJANGO_SETTINGS_MODULE: "desktop_django_starter.settings.packaged",',
    `      DJANGO_SETTINGS_MODULE: "${targetConfig.packagedSettingsModule}",`,
    stageBackendPath
  );
  source = replaceRequired(
    source,
    '  run(pythonExecutable, ["manage.py", ...args], {',
    `  run(pythonExecutable, [${JSON.stringify(targetConfig.packagedManagePath)}, ...args], {`,
    stageBackendPath
  );
  fs.writeFileSync(stageBackendPath, source);
}

function updateBundledPythonScript(electronRoot, targetConfig) {
  const bundledPythonPath = path.join(electronRoot, "scripts", "bundled-python.cjs");
  let source = fs.readFileSync(bundledPythonPath, "utf8");
  source = replaceRequired(
    source,
    '      settingsModule: "desktop_django_starter.settings.packaged",',
    `      settingsModule: "${targetConfig.packagedSettingsModule}",`,
    bundledPythonPath
  );
  fs.writeFileSync(bundledPythonPath, source);
}

function updateCopiedScriptTests(electronRoot, slug) {
  const scriptsRoot = path.join(electronRoot, "scripts");
  const underscoredSlug = toIdentifier(slug);

  for (const entry of fs.readdirSync(scriptsRoot, { withFileTypes: true })) {
    if (!entry.isFile() || !entry.name.endsWith(".test.cjs")) {
      continue;
    }

    const testPath = path.join(scriptsRoot, entry.name);
    let source = fs.readFileSync(testPath, "utf8");
    source = source.replaceAll("desktop-django-starter", slug);
    source = source.replaceAll("desktop_django_starter", underscoredSlug);
    source = source.replaceAll('from: "../../scripts"', 'from: "./scripts"');
    source = source.replaceAll('from: "../../.stage/backend"', 'from: "../.stage/backend"');
    fs.writeFileSync(testPath, source);
  }
}

function writeTargetMetadata(electronRoot, projectName, productName, slug, targetConfig) {
  const metadataPath = path.join(electronRoot, "wrap-target.json");
  const metadata = {
    schemaVersion: 1,
    project: {
      name: projectName,
      productName,
      slug
    },
    django: {
      developmentManagePath: targetConfig.developmentManagePath,
      packagedManagePath: targetConfig.packagedManagePath,
      developmentSettingsModule: targetConfig.developmentSettingsModule,
      packagedSettingsModule: targetConfig.packagedSettingsModule,
      packageModule: targetConfig.packageModule,
      packagePath: targetConfig.packagePath,
      developmentSettingsPath: targetConfig.developmentSettingsPath,
      packagedSettingsPath: targetConfig.packagedSettingsPath,
      settingsBaseModule: targetConfig.settingsBaseModule,
      settingsBasePath: targetConfig.settingsBasePath,
      settingsContainerModule: targetConfig.settingsContainerModule,
      urlsPath: targetConfig.urlsPath,
      desktopMiddlewarePath: targetConfig.desktopMiddlewarePath,
      desktopRuntimePath: targetConfig.desktopRuntimePath,
      packagedRoots: targetConfig.packagedRoots,
      seedDatabasePath: targetConfig.seedDatabasePath,
      seedMediaPath: targetConfig.seedMediaPath
    }
  };

  fs.writeFileSync(metadataPath, `${JSON.stringify(metadata, null, 2)}\n`);
}

function main() {
  const targetRoot = process.argv[2];
  if (!targetRoot) {
    fail("usage: prepare-electron-scaffold.cjs TARGET_REPO");
  }

  const resolvedTargetRoot = path.resolve(targetRoot);
  const electronRoot = path.join(resolvedTargetRoot, "electron");

  if (!fs.existsSync(electronRoot)) {
    fail(`electron scaffold not found: ${electronRoot}`);
  }

  verifyStarterTemplateCompatibility(electronRoot);

  const projectName = readProjectName(resolvedTargetRoot);
  const slug = toSlug(projectName);
  const productName = toProductName(projectName);
  const targetConfig = inferTargetConfig(resolvedTargetRoot);

  updatePackageJson(electronRoot, projectName, slug);
  updateBuilderConfig(electronRoot, productName, slug);
  writeWrappedSplash(electronRoot, productName);
  updateLaunchScripts(electronRoot, targetConfig, slug);
  updateStageBackendScript(electronRoot, targetConfig);
  updateBundledPythonScript(electronRoot, targetConfig);
  updateCopiedScriptTests(electronRoot, slug);
  writeTargetMetadata(electronRoot, projectName, productName, slug, targetConfig);

  process.stdout.write(`Prepared scaffold for ${projectName} in ${electronRoot}\n`);
}

main();
