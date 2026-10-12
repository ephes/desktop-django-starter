import hashlib
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/write-checksums.py"


def run_manifest(output, *patterns):
    args = [sys.executable, str(SCRIPT), "--output", str(output)]
    for pattern in patterns:
        args.extend(["--glob", str(pattern)])
    return subprocess.run(args, capture_output=True, text=True)


@pytest.mark.parametrize("alias", ["direct", "symlink", "hardlink"])
def test_refuses_output_identity(tmp_path, alias):
    output = tmp_path / "checksums.txt"
    output.write_text("previous manifest\n")
    source = output
    if alias != "direct":
        source = tmp_path / "alias.txt"
        if alias == "symlink":
            try:
                source.symlink_to(output)
            except OSError:
                pytest.skip("symlink creation unavailable")
        else:
            source.hardlink_to(output)
    result = run_manifest(output, tmp_path / "*" if alias == "direct" else source)
    assert result.returncode != 0
    assert "Manifest output is also an input" in result.stderr
    assert output.read_text() == "previous manifest\n"


def test_refuses_ambiguous_names(tmp_path):
    output = tmp_path / "checksums.txt"
    output.write_text("previous manifest\n")
    for folder in ("a", "b"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "app.zip").write_bytes(folder.encode())
    result = run_manifest(output, tmp_path / "*/*.zip")
    assert result.returncode != 0
    assert "Ambiguous artifact basename" in result.stderr
    assert output.read_text() == "previous manifest\n"


def test_normal_manifest_is_verifiable_and_deterministic(tmp_path):
    output = tmp_path / "checksums.txt"
    for name in ("app.zip", "app.dmg"):
        (tmp_path / name).write_bytes(name.encode())
    result = run_manifest(output, tmp_path / "app.*", tmp_path / "app.zip")
    assert result.returncode == 0, result.stderr
    assert output.read_text().splitlines() == [
        f"{hashlib.sha256(name.encode()).hexdigest()}  {name}"
        for name in ("app.dmg", "app.zip")
    ]


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes and filenames")
@pytest.mark.parametrize("name", ["app\n.zip", "app\r.zip", "app\\.zip"])
def test_refuses_unrepresentable_names(tmp_path, name):
    output = tmp_path / "checksums.txt"
    output.write_text("previous")
    source = tmp_path / name
    source.write_bytes(b"artifact")
    result = run_manifest(output, source)
    assert "Unsupported artifact basename" in result.stderr
    assert output.read_text() == "previous"


def test_hash_failure_preserves_manifest(tmp_path):
    output = tmp_path / "checksums.txt"
    output.write_text("previous")
    directory = tmp_path / "directory.zip"
    directory.mkdir()
    assert run_manifest(output, directory).returncode != 0
    assert output.read_text() == "previous"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["checksums.txt", "directory.zip"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_replacement_preserves_mode_and_symlink(tmp_path):
    target = tmp_path / "target.txt"
    target.write_text("previous")
    target.chmod(0o640)
    output = tmp_path / "checksums.txt"
    output.symlink_to(target)
    source = tmp_path / "app.zip"
    source.write_bytes(b"artifact")
    assert run_manifest(output, source).returncode == 0
    assert output.is_symlink()
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    assert "app.zip" in target.read_text()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["app.zip", "checksums.txt", "target.txt"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_new_manifest_obeys_umask(tmp_path):
    source = tmp_path / "app.zip"
    source.write_bytes(b"artifact")
    output = tmp_path / "checksums.txt"
    old_mask = os.umask(0o027)
    try:
        assert run_manifest(output, source).returncode == 0
    finally:
        os.umask(old_mask)
    assert stat.S_IMODE(output.stat().st_mode) == 0o640
