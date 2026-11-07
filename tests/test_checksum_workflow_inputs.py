"""Run checked-in checksum argument sets against tiny synthetic build outputs."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/write-checksums.py"


def matrix_entry(workflow, platform):
    return next(
        entry
        for entry in workflow.split("          - os: ")[1:]
        if f"            platform: {platform}\n" in entry
    ).split("\n\n    steps:", 1)[0]


def run_arguments(tmp_path, arguments):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments, "--output", str(tmp_path / "checksums.txt")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )


def test_electron_linux_checksum_inputs_without_external_blockmap(tmp_path):
    workflow = (ROOT / ".github/workflows/desktop-packages.yml").read_text()
    entry = matrix_entry(workflow, "linux")
    checksum_args = entry.split("            checksum_args: >-\n", 1)[1].split(
        "            checksum_artifact_name:",
        1,
    )[0]
    patterns = re.findall(r'--glob "([^"]+)"', checksum_args)
    for name in ("synthetic.AppImage", "latest-linux.yml"):
        path = tmp_path / "shells/electron/dist" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic artifact")
    args = [part for pattern in patterns for part in ("--glob", pattern)]
    result = run_arguments(tmp_path, args)
    assert result.returncode == 0, result.stderr
    assert len((tmp_path / "checksums.txt").read_text().splitlines()) == 2


@pytest.mark.parametrize("platform", ["macos", "windows", "linux"])
@pytest.mark.parametrize("signed", [False, True])
def test_tauri_checksum_inputs_with_optional_signatures(tmp_path, platform, signed):
    workflow = (ROOT / ".github/workflows/tauri-packages.yml").read_text()
    entry = matrix_entry(workflow, platform)
    patterns = dict(re.findall(r"^            (\w+_glob): (.+)$", entry, re.M))
    for field, pattern in patterns.items():
        if field == "signature_glob" and not signed:
            continue
        artifact = tmp_path / pattern.replace("*", "synthetic")
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(b"synthetic artifact")
    step = workflow.split("      - name: Generate artifact checksums\n", 1)[1].split(
        "\n      - name:",
        1,
    )[0]
    flags = re.findall(r'--(glob|optional-glob) "\$\{\{ matrix\.(\w+_glob) \}\}"', step)
    assert len(flags) == 3
    args = [part for flag, field in flags for part in (f"--{flag}", patterns[field])]
    result = run_arguments(tmp_path, args)
    assert result.returncode == 0, result.stderr
    manifest = (tmp_path / "checksums.txt").read_text()
    assert (".sig" in manifest) == signed
    assert len(manifest.splitlines()) == (2 if platform == "macos" else 1) + signed
