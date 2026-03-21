module.exports = {
  appId: "io.github.joww12.desktop-django-starter",
  productName: "Desktop Django Starter",
  asar: true,
  npmRebuild: false,
  directories: {
    output: "dist"
  },
  files: [
    "main.js",
    "package.json",
    "preload.cjs",
    "scripts/bundled-python.cjs"
  ],
  extraResources: [
    {
      from: ".stage/backend",
      to: "backend",
      filter: ["**/*"]
    }
  ],
  mac: {
    category: "public.app-category.developer-tools",
    target: ["dmg"],
    artifactName: "desktop-django-starter-macos-${version}-${arch}.${ext}"
  },
  win: {
    target: ["nsis"],
    artifactName: "desktop-django-starter-windows-${version}-${arch}.${ext}"
  },
  nsis: {
    oneClick: false,
    perMachine: false,
    allowToChangeInstallationDirectory: true
  },
  linux: {
    category: "Development",
    target: ["AppImage"],
    artifactName: "desktop-django-starter-linux-${version}-${arch}.${ext}"
  }
};
