const fs = require("node:fs");
const path = require("node:path");

const candidatePaths = [
  path.join(__dirname, "shared", "materialize-symlinks.cjs"),
  path.resolve(__dirname, "../../../scripts/materialize-symlinks.cjs"),
];

let resolvedPath = null;

for (const candidatePath of candidatePaths) {
  if (fs.existsSync(candidatePath)) {
    resolvedPath = candidatePath;
    break;
  }
}

if (!resolvedPath) {
  throw new Error("Unable to locate the shared symlink materialization helper.");
}

module.exports = require(resolvedPath);
