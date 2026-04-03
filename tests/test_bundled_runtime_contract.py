import json
import subprocess
from pathlib import Path


def test_bundled_runtime_manifest_contract(tmp_path: Path) -> None:
    backend_root = tmp_path / "backend"
    python_executable = backend_root / "python" / "bin" / "python3"
    python_executable.parent.mkdir(parents=True)
    python_executable.write_text("", encoding="utf-8")

    script = """
const fs = require("node:fs");
const path = require("node:path");
const runtime = require(process.argv[2]);
const backendRoot = process.argv[1];
const executable = path.join(backendRoot, "python", "bin", "python3");

runtime.writeRuntimeManifest(backendRoot, {
  version: "3.14.3",
  root: path.join(backendRoot, "python"),
  executable,
  purelib: path.join(backendRoot, "python", "lib", "python3.14", "site-packages"),
  scripts: path.join(backendRoot, "python", "bin")
});

process.stdout.write(JSON.stringify({
  manifest: runtime.loadRuntimeManifest(backendRoot),
  resolved: runtime.resolveBundledPythonExecutable(backendRoot, process.platform)
}));
"""

    result = subprocess.run(
        [
            "node",
            "-e",
            script,
            str(backend_root),
            str(Path("scripts/bundled-python.cjs").resolve()),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["manifest"]["python"]["executable"] == "python/bin/python3"
    assert payload["manifest"]["launcher"]["settingsModule"] == (
        "desktop_django_starter.settings.packaged"
    )
    assert Path(payload["resolved"]) == python_executable
