const fs = require("node:fs");
const path = require("node:path");

// Budgets count expanded paths, so shared directory links consume work per copy.
function preflightRuntime(rootPath, { maxEntries = 200000, maxBytes = 2 * 1024 ** 3, maxDepth = 256 } = {}) {
  const runtimeRoot = fs.realpathSync(rootPath);
  let entries = 0;
  let bytes = 0;
  const ancestors = new Set();
  function visit(entryPath, depth) {
    if (++entries > maxEntries || depth > maxDepth) throw new Error("Runtime materialization entry/depth budget exceeded.");
    let realPath;
    try { realPath = fs.realpathSync(entryPath); }
    catch (error) {
      throw new Error(`Broken symlink in staged runtime or symlink cycle: ${entryPath}`, { cause: error });
    }
    const stats = fs.statSync(realPath);
    if (stats.isDirectory()) {
      const relative = path.relative(runtimeRoot, realPath);
      if (relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
        throw new Error(`Directory target outside runtime: ${entryPath} -> ${realPath}`);
      }
      if (ancestors.has(realPath)) throw new Error(`Directory symlink cycle in staged runtime: ${entryPath}`);
      ancestors.add(realPath);
      const directory = fs.opendirSync(realPath);
      try {
        let entry;
        while ((entry = directory.readSync()) !== null) visit(path.join(realPath, entry.name), depth + 1);
      } finally {
        directory.closeSync();
        ancestors.delete(realPath);
      }
    } else if (stats.isFile()) {
      bytes += stats.size;
      if (bytes > maxBytes) throw new Error("Runtime materialization byte budget exceeded.");
    } else throw new Error(`Unsupported runtime entry: ${entryPath}`);
  }
  visit(runtimeRoot, 0);
}

function materializeSymlinks(rootPath, limits) {
  if (!fs.existsSync(rootPath)) return;
  preflightRuntime(rootPath, limits);
  materializeDirectory(rootPath);
}

function materializeDirectory(rootPath) {
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
      let committed = false;
      let primaryError;
      try {
        if (targetStats.isDirectory()) {
          fs.cpSync(resolvedTarget, replacement, { recursive: true, dereference: true });
        } else {
          fs.copyFileSync(resolvedTarget, replacement);
        }
        fs.chmodSync(replacement, targetStats.mode);

        // Directory copies cannot portably rename over a directory symlink.
        // Retain the original link until the completed copy has been published.
        fs.renameSync(entryPath, original);
        try {
          fs.renameSync(replacement, entryPath);
          committed = true;
        } catch (error) {
          try {
            fs.renameSync(original, entryPath);
          } catch (restoreError) {
            preserveTemporary = true;
            error.rollbackError = restoreError;
            error.originalPath = original;
            error.temporaryRoot = temporaryRoot;
            error.message += ` Materialization rollback failed; original link kept at ${original}.`;
          }
          throw error;
        }
      } catch (error) {
        primaryError = error;
        error.committed = false;
        error.temporaryRoot = temporaryRoot;
        throw error;
      } finally {
        if (!preserveTemporary) {
          try { fs.rmSync(temporaryRoot, { recursive: true, force: true }); }
          catch (cleanupError) {
            if (primaryError) {
              primaryError.cleanupErrors = [{ path: temporaryRoot, error: cleanupError }];
              primaryError.message += ` Cleanup failed; owned temporary tree remains at ${temporaryRoot}: ${cleanupError.message}`;
            } else {
              const error = new Error(`Materialization committed at ${entryPath}; cleanup failed; owned temporary tree remains at ${temporaryRoot}: ${cleanupError.message}`, { cause: cleanupError });
              error.committed = committed;
              error.temporaryRoot = temporaryRoot;
              error.cleanupErrors = [{ path: temporaryRoot, error: cleanupError }];
              throw error;
            }
          }
        }
      }
      continue;
    }

    if (stats.isDirectory()) {
      materializeDirectory(entryPath);
    }
  }
}

module.exports = {
  materializeSymlinks,
  preflightRuntime
};
