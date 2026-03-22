from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_write_checksums_cli_writes_sha256_manifest(tmp_path: Path) -> None:
    first = tmp_path / "desktop-django-starter-a.dmg"
    second = tmp_path / "desktop-django-starter-b.dmg"
    first.write_bytes(b"first artifact\n")
    second.write_bytes(b"second artifact\n")
    output = tmp_path / "checksums.txt"

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "electron" / "scripts" / "write-checksums.py"),
            "--glob",
            str(tmp_path / "*.dmg"),
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    lines = output.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert lines[0].endswith("  desktop-django-starter-a.dmg")
    assert lines[1].endswith("  desktop-django-starter-b.dmg")
    assert all(len(line.split("  ")[0]) == 64 for line in lines)
    assert "Wrote" in completed.stdout
