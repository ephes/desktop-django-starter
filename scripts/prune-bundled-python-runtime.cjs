const fs = require("node:fs");
const path = require("node:path");

function toPortableRelativePath(rootPath, targetPath) {
  return path.relative(rootPath, targetPath).split(path.sep).join("/");
}

function removeIfPresent(targetPath) {
  if (!fs.existsSync(targetPath)) {
    return false;
  }

  fs.rmSync(targetPath, { recursive: true, force: true });
  return true;
}

function pruneBundledPythonRuntime(pythonRoot) {
  const removed = [];
  const binRoot = path.join(pythonRoot, "bin");
  const libRoot = path.join(pythonRoot, "lib");

  if (fs.existsSync(binRoot)) {
    for (const entry of fs.readdirSync(binRoot)) {
      if (/^idle3(\.\d+)?$/.test(entry)) {
        const targetPath = path.join(binRoot, entry);
        if (removeIfPresent(targetPath)) {
          removed.push(toPortableRelativePath(pythonRoot, targetPath));
        }
      }
    }
  }

  if (fs.existsSync(libRoot)) {
    for (const entry of fs.readdirSync(libRoot)) {
      if (/^(tcl|tk)\d/.test(entry) || /^(itcl|thread)\d/.test(entry)) {
        const targetPath = path.join(libRoot, entry);
        if (removeIfPresent(targetPath)) {
          removed.push(toPortableRelativePath(pythonRoot, targetPath));
        }
      } else if (/^lib(tcl|tk|itcl)/.test(entry)) {
        const targetPath = path.join(libRoot, entry);
        if (removeIfPresent(targetPath)) {
          removed.push(toPortableRelativePath(pythonRoot, targetPath));
        }
      }
    }

    for (const entry of fs.readdirSync(libRoot, { withFileTypes: true })) {
      if (!entry.isDirectory() || !/^python\d+\.\d+$/.test(entry.name)) {
        continue;
      }

      const stdlibRoot = path.join(libRoot, entry.name);

      for (const candidate of ["idlelib", "tkinter"]) {
        const targetPath = path.join(stdlibRoot, candidate);
        if (removeIfPresent(targetPath)) {
          removed.push(toPortableRelativePath(pythonRoot, targetPath));
        }
      }

      const dynloadRoot = path.join(stdlibRoot, "lib-dynload");
      if (!fs.existsSync(dynloadRoot)) {
        continue;
      }

      for (const dynloadEntry of fs.readdirSync(dynloadRoot)) {
        if (!/^_tkinter\./.test(dynloadEntry)) {
          continue;
        }

        const targetPath = path.join(dynloadRoot, dynloadEntry);
        if (removeIfPresent(targetPath)) {
          removed.push(toPortableRelativePath(pythonRoot, targetPath));
        }
      }
    }
  }

  return removed.sort();
}

module.exports = {
  pruneBundledPythonRuntime
};
