const fs = require("node:fs");
const path = require("node:path");

function materializeSymlinks(rootPath) {
  if (!fs.existsSync(rootPath)) {
    return;
  }

  for (const entry of fs.readdirSync(rootPath, { withFileTypes: true })) {
    const entryPath = path.join(rootPath, entry.name);
    const stats = fs.lstatSync(entryPath);

    if (stats.isSymbolicLink()) {
      const targetPath = fs.readlinkSync(entryPath);
      const resolvedTarget = path.resolve(path.dirname(entryPath), targetPath);
      let targetStats;
      try {
        targetStats = fs.statSync(resolvedTarget);
      } catch (error) {
        if (error && error.code === "ENOENT") {
          throw new Error(`Broken symlink in staged runtime: ${entryPath} -> ${targetPath}`);
        }
        throw error;
      }

      fs.rmSync(entryPath, { recursive: true, force: true });

      if (targetStats.isDirectory()) {
        fs.cpSync(resolvedTarget, entryPath, { recursive: true, dereference: true });
        materializeSymlinks(entryPath);
        continue;
      }

      fs.copyFileSync(resolvedTarget, entryPath);
      fs.chmodSync(entryPath, targetStats.mode);
      continue;
    }

    if (stats.isDirectory()) {
      materializeSymlinks(entryPath);
    }
  }
}

module.exports = {
  materializeSymlinks
};
