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

      const temporaryRoot = fs.mkdtempSync(path.join(rootPath, ".materialize-"));
      const replacement = path.join(temporaryRoot, "replacement");
      const original = path.join(temporaryRoot, "original");
      let preserveTemporary = false;
      try {
        if (targetStats.isDirectory()) {
          fs.cpSync(resolvedTarget, replacement, { recursive: true, dereference: true });
          materializeSymlinks(replacement);
        } else {
          fs.copyFileSync(resolvedTarget, replacement);
        }
        fs.chmodSync(replacement, targetStats.mode);

        // Directory copies cannot portably rename over a directory symlink.
        // Retain the original link until the completed copy has been published.
        fs.renameSync(entryPath, original);
        try {
          fs.renameSync(replacement, entryPath);
        } catch (error) {
          try {
            fs.renameSync(original, entryPath);
          } catch (restoreError) {
            preserveTemporary = true;
            throw new Error(`Materialization rollback failed; original link kept at ${original}.`, {
              cause: restoreError
            });
          }
          throw error;
        }
      } finally {
        if (!preserveTemporary) {
          fs.rmSync(temporaryRoot, { recursive: true, force: true });
        }
      }
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
