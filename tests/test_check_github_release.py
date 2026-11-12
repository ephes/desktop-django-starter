"""Exercise the release CLI with synthetic responses; never invoke gh."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check-github-release.py"
TAG = "v1.2.3"
# Deliberately independent of the helper's expected_assets implementation.
ASSETS = [
    "desktop-django-starter-macos-1.2.3-arm64.dmg",
    "desktop-django-starter-macos-1.2.3-arm64.dmg.blockmap",
    "desktop-django-starter-macos-1.2.3-arm64.zip",
    "desktop-django-starter-macos-1.2.3-arm64.zip.blockmap",
    "desktop-django-starter-windows-1.2.3-x64.exe",
    "desktop-django-starter-windows-1.2.3-x64.exe.blockmap",
    "desktop-django-starter-linux-1.2.3-x86_64.AppImage",
    "latest-mac.yml",
    "latest.yml",
    "latest-linux.yml",
]


@pytest.fixture
def release_cli():
    spec = importlib.util.spec_from_file_location("check_github_release", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def drive(monkeypatch, cli, *, publish=False, draft=True, assets=None):
    """Patch the subprocess boundary so even a broken gate cannot edit a release."""
    calls = []
    payload = {
        "isDraft": draft,
        "assets": [{"name": name, "size": 42} for name in ASSETS] if assets is None else assets,
    }

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), TAG, *(["--publish"] if publish else [])])
    return calls


@pytest.mark.parametrize("publish,draft", [(False, True), (False, False), (True, False)])
def test_complete_read_only_or_already_published(monkeypatch, release_cli, capsys, publish, draft):
    calls = drive(monkeypatch, release_cli, publish=publish, draft=draft)
    assert release_cli.main() == 0
    assert calls == [["gh", "release", "view", TAG, "--json", "isDraft,assets"]]
    output = capsys.readouterr().out
    assert "full hosted Electron asset set" in output
    assert ("still a draft" if draft else "already published") in output


def test_explicit_publish_edits_draft_once(monkeypatch, release_cli, capsys):
    calls = drive(monkeypatch, release_cli, publish=True)
    assert release_cli.main() == 0
    assert calls == [
        ["gh", "release", "view", TAG, "--json", "isDraft,assets"],
        ["gh", "release", "edit", TAG, "--draft=false"],
    ]
    assert f"Published release {TAG}" in capsys.readouterr().out


@pytest.mark.parametrize("missing", ASSETS)
@pytest.mark.parametrize("publish", [False, True])
def test_each_missing_asset_blocks_edit(monkeypatch, release_cli, capsys, missing, publish):
    calls = drive(
        monkeypatch,
        release_cli,
        publish=publish,
        assets=[{"name": name, "size": 42} for name in ASSETS if name != missing],
    )
    assert release_cli.main() == 1
    assert len(calls) == 1
    assert f"- {missing}" in capsys.readouterr().out


@pytest.mark.parametrize("stage", ["view", "edit"])
@pytest.mark.parametrize("failure", ["launch", "timeout", "exit", "decode"])
def test_gh_failures_are_bounded_nonzero_without_retry(
    monkeypatch,
    release_cli,
    capsys,
    stage,
    failure,
):
    calls = drive(monkeypatch, release_cli, publish=True)
    successful_run = release_cli.subprocess.run

    def failing_run(command, **kwargs):
        assert kwargs.get("timeout") == 30
        if command[2] != stage:
            return successful_run(command, **kwargs)
        calls.append(command)
        if failure == "launch":
            raise FileNotFoundError("gh missing")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, 30, stderr=b"partial detail")
        if failure == "decode":
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")
        raise subprocess.CalledProcessError(2, command, stderr="useful detail " + "x" * 5000)

    monkeypatch.setattr(release_cli.subprocess, "run", failing_run)
    assert release_cli.main() == 1
    assert len(calls) == (1 if stage == "view" else 2)
    output = capsys.readouterr()
    assert "Traceback" not in output.err
    assert "Published release" not in output.out
    assert 0 < len(output.err) < 1100
    if failure == "exit":
        assert "useful detail" in output.err
    if stage == "edit":
        assert "uncertain" in output.err.lower()
        assert "verify" in output.err.lower()


@pytest.mark.parametrize(
    "payload",
    [
        "{",
        "null",
        "[]",
        "{}",
        '{"isDraft": "false", "assets": []}',
        '{"isDraft": true, "assets": {}}',
        '{"isDraft": true, "assets": [null]}',
        '{"isDraft": true, "assets": [{}]}',
        '{"isDraft": true, "assets": [{"name": 1}]}',
        '{"isDraft": true, "assets": [{"name": ""}]}',
    ],
)
def test_invalid_view_json_or_schema_never_edits(monkeypatch, release_cli, capsys, payload):
    calls = drive(monkeypatch, release_cli, publish=True)

    def invalid_view(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, payload, "")

    monkeypatch.setattr(release_cli.subprocess, "run", invalid_view)
    assert release_cli.main() == 1
    assert len(calls) == 1
    output = capsys.readouterr()
    assert "Traceback" not in output.err
    assert "invalid" in output.err.lower()


@pytest.mark.parametrize("name", ASSETS)
@pytest.mark.parametrize("size", [0, -1, None, True, "42", 1.5])
def test_invalid_expected_asset_size_blocks_edit(monkeypatch, release_cli, capsys, name, size):
    calls = drive(
        monkeypatch,
        release_cli,
        publish=True,
        assets=[{"name": asset, "size": size if asset == name else 42} for asset in ASSETS],
    )
    assert release_cli.main() == 1
    assert len(calls) == 1
    output = capsys.readouterr().out
    assert "empty or invalid size" in output
    assert f"- {name}" in output
    assert "is missing" not in output


def test_missing_size_is_invalid(monkeypatch, release_cli, capsys):
    calls = drive(
        monkeypatch,
        release_cli,
        publish=True,
        assets=[{"name": name} for name in ASSETS],
    )
    assert release_cli.main() == 1
    assert len(calls) == 1
    assert "empty or invalid size" in capsys.readouterr().out


def test_missing_and_invalid_assets_reported_separately(monkeypatch, release_cli, capsys):
    calls = drive(
        monkeypatch,
        release_cli,
        publish=True,
        assets=[{"name": name, "size": 0} for name in ASSETS[1:]],
    )
    assert release_cli.main() == 1
    assert len(calls) == 1
    output = capsys.readouterr().out
    assert "is missing 1 expected asset(s)" in output
    assert "9 expected asset(s) with empty or invalid size" in output
