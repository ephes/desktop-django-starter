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
            str(ROOT / "scripts" / "write-checksums.py"),
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


def test_prune_bundled_python_runtime_removes_tk_and_idle_artifacts(tmp_path: Path) -> None:
    python_root = tmp_path / "python"
    idle_binary = python_root / "bin" / "idle3.14"
    tkinter_package = python_root / "lib" / "python3.14" / "tkinter" / "__init__.py"
    idlelib_package = python_root / "lib" / "python3.14" / "idlelib" / "__init__.py"
    dynload_name = "_tkinter.cpython-314-x86_64-linux-gnu.so"
    dynload_extension = python_root / "lib" / "python3.14" / "lib-dynload" / dynload_name
    tcl_library = python_root / "lib" / "libtcl9.0.so"
    tcl_tree = python_root / "lib" / "tcl9.0" / "init.tcl"
    unrelated = python_root / "lib" / "python3.14" / "site-packages" / "django" / "__init__.py"

    for path in [
        idle_binary,
        tkinter_package,
        idlelib_package,
        dynload_extension,
        tcl_library,
        tcl_tree,
        unrelated,
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder", encoding="utf-8")

    completed = subprocess.run(
        [
            "node",
            "-e",
            (
                "const { pruneBundledPythonRuntime } = require(process.argv[1]); "
                "const removed = pruneBundledPythonRuntime(process.argv[2]); "
                "process.stdout.write(JSON.stringify(removed));"
            ),
            str(ROOT / "scripts" / "prune-bundled-python-runtime.cjs"),
            str(python_root),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "bin/idle3.14" in completed.stdout
    assert "lib/libtcl9.0.so" in completed.stdout
    assert not idle_binary.exists()
    assert not tkinter_package.exists()
    assert not idlelib_package.exists()
    assert not dynload_extension.exists()
    assert not tcl_library.exists()
    assert not tcl_tree.exists()
    assert unrelated.exists()
