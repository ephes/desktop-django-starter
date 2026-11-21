import hashlib
import importlib.util
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/write-checksums.py"


@pytest.fixture
def checksum_script():
    spec = importlib.util.spec_from_file_location("write_checksums", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        f"{hashlib.sha256(name.encode()).hexdigest()}  {name}" for name in ("app.dmg", "app.zip")
    ]


def test_stable_artifact_symlink_keeps_its_manifest_name(tmp_path):
    source = tmp_path / "app.zip"
    source.write_bytes(b"artifact")
    alias = tmp_path / "alias.zip"
    try:
        alias.symlink_to(source)
    except OSError:
        pytest.skip("symlink creation unavailable")

    output = tmp_path / "checksums.txt"
    result = run_manifest(output, alias, source)
    assert result.returncode == 0, result.stderr
    assert output.read_text() == f"{hashlib.sha256(b'artifact').hexdigest()}  alias.zip\n"


def test_glob_ignores_symlink_loop_alongside_regular_artifact(tmp_path):
    source = tmp_path / "app.zip"
    source.write_bytes(b"artifact")
    loop = tmp_path / "loop.zip"
    try:
        loop.symlink_to(loop.name)
    except OSError:
        pytest.skip("symlink creation unavailable")

    output = tmp_path / "checksums.txt"
    result = run_manifest(output, tmp_path / "*.zip")
    assert result.returncode == 0, result.stderr
    assert output.read_text() == f"{hashlib.sha256(b'artifact').hexdigest()}  app.zip\n"


@pytest.mark.skipif(os.name == "nt", reason="Windows prevents replacing an open source file")
def test_refuses_artifact_replaced_during_hash(tmp_path, monkeypatch, checksum_script):
    source = tmp_path / "app.zip"
    source.write_bytes(b"artifact")
    replacement = tmp_path / "new.zip"
    replacement.write_bytes(b"new data")
    output = tmp_path / "checksums.txt"
    output.write_bytes(b"previous manifest\n")
    digest = hashlib.sha256()

    class ReplacingDigest:
        def update(self, chunk):
            digest.update(chunk)
            replacement.replace(source)

        hexdigest = digest.hexdigest

    monkeypatch.setattr(checksum_script.hashlib, "sha256", ReplacingDigest)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--glob", str(source), "--output", str(output)])
    with pytest.raises(SystemExit, match="Artifact changed"):
        checksum_script.main()
    assert output.read_bytes() == b"previous manifest\n"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["app.zip", "checksums.txt"]


def test_refuses_earlier_artifact_changed_during_later_hash(tmp_path, monkeypatch, checksum_script):
    first = tmp_path / "a.zip"
    first.write_bytes(b"first")
    second = tmp_path / "b.zip"
    second.write_bytes(b"second")
    output = tmp_path / "checksums.txt"
    output.write_bytes(b"previous manifest\n")
    sha256 = hashlib.sha256

    class UpdatingDigest:
        def __init__(self):
            self.digest = sha256()

        def update(self, chunk):
            self.digest.update(chunk)
            if chunk == b"second":
                first.write_bytes(b"updated first")

        def hexdigest(self):
            return self.digest.hexdigest()

    monkeypatch.setattr(checksum_script.hashlib, "sha256", UpdatingDigest)
    monkeypatch.setattr(
        sys, "argv", [str(SCRIPT), "--glob", str(tmp_path / "*.zip"), "--output", str(output)]
    )
    with pytest.raises(SystemExit, match="Artifact changed"):
        checksum_script.main()
    assert output.read_bytes() == b"previous manifest\n"


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


@pytest.mark.parametrize("unsuitable", ["missing", "directory"])
def test_each_pattern_requires_a_regular_artifact(tmp_path, unsuitable):
    source = tmp_path / "app.zip"
    source.write_bytes(b"installer")
    output = tmp_path / "checksums.txt"
    output.write_text("previous manifest\n")
    metadata = tmp_path / "latest.yml"
    if unsuitable == "directory":
        metadata.mkdir()
    result = run_manifest(output, tmp_path / "*.zip", metadata)
    assert result.returncode != 0
    assert "No artifacts matched" in result.stderr
    assert str(metadata) in result.stderr
    assert output.read_text() == "previous manifest\n"


def test_all_unmatched_patterns_are_reported(tmp_path):
    output = tmp_path / "checksums.txt"
    (tmp_path / "app.zip").write_bytes(b"installer")
    missing = [tmp_path / "*.yml", tmp_path / "*.blockmap"]
    result = run_manifest(output, tmp_path / "*.zip", *missing)
    assert result.returncode != 0
    assert all(str(pattern) in result.stderr for pattern in missing)
    assert not output.exists()


def test_optional_patterns_share_deduplication_and_allow_absence(tmp_path):
    source = tmp_path / "app.zip"
    source.write_bytes(b"installer")
    output = tmp_path / "checksums.txt"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--output",
            str(output),
            "--glob",
            str(source),
            "--optional-glob",
            str(tmp_path / "*.sig"),
            "--optional-glob",
            str(source),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert len(output.read_text().splitlines()) == 1


@pytest.mark.parametrize("optional_exists", [False, True])
def test_optional_patterns_cannot_bypass_required_inputs_or_output_safety(
    tmp_path, optional_exists
):
    source = tmp_path / "app.zip"
    source.write_bytes(b"installer")
    output = tmp_path / "checksums.txt"
    output.write_text("previous")
    required = source if optional_exists else tmp_path / "missing.yml"
    optional = output if optional_exists else source
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--output",
            str(output),
            "--glob",
            str(required),
            "--optional-glob",
            str(optional),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert ("Manifest output is also an input" if optional_exists else "No artifacts matched") in (
        result.stderr
    )
    assert output.read_text() == "previous"
