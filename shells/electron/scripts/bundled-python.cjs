const fs = require("node:fs");
const path = require("node:path");

const candidatePaths = [
  path.join(__dirname, "shared", "bundled-python.cjs"),
  path.resolve(__dirname, "../../../scripts/bundled-python.cjs"),
];

let resolvedPath = null;

for (const candidatePath of candidatePaths) {
  if (fs.existsSync(candidatePath)) {
    resolvedPath = candidatePath;
    break;
  }
}

if (!resolvedPath) {
  throw new Error("Unable to locate the shared bundled Python helper.");
}

module.exports = require(resolvedPath);
