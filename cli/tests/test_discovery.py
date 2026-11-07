"""Exercise temporary project discovery through actual CLI preflight."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from dds import wrap
from dds.cli import main

EXCLUDED = (
    ".git",
    ".hidden",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    "outer/.cache/project",
)


def discovered_path(relative):
    return os.path.join(".", *relative.split("/"))


@pytest.fixture
def preflight(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    skill = tmp_path / "assets/SKILL.md"
    skill.parent.mkdir()
    skill.write_text("synthetic skill", encoding="utf-8")
    prompt = skill.with_name("prompt.md")
    prompt.write_text("synthetic prompt", encoding="utf-8")
    monkeypatch.setattr(wrap, "SKILL_PATH", skill)
    monkeypatch.setattr(wrap, "PROMPT_TEMPLATE", prompt)
    monkeypatch.setattr(wrap.shutil, "which", lambda name: f"/fake/{name}")
    git_calls = []
    launches = []

    def git(command, **kwargs):
        assert command in (["git", "rev-parse", "--git-dir"], ["git", "status", "--porcelain"])
        git_calls.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(wrap.subprocess, "run", git)
    monkeypatch.setattr(wrap.subprocess, "Popen", lambda *a, **k: pytest.fail("unexpected child"))
    monkeypatch.setattr(wrap, "_run_claude", lambda *args: launches.append("claude"))
    monkeypatch.setattr(wrap.os, "execvp", lambda name, argv: launches.append(name))
    monkeypatch.setattr(wrap, "run_init", lambda *a, **k: pytest.fail("setup invoked"))
    return tmp_path, git_calls, launches


def plant(root, paths):
    for relative in paths:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic manage.py", encoding="utf-8")


@pytest.mark.parametrize(
    ("paths", "expected"),
    [
        ([], []),
        (["manage.py"], ["manage.py"]),
        (["src/nested/project/manage.py"], ["src/nested/project/manage.py"]),
        ([f"{directory}/manage.py" for directory in EXCLUDED], []),
        (
            ["z/project/manage.py", "a/project/manage.py", "manage.py"],
            ["manage.py", "a/project/manage.py", "z/project/manage.py"],
        ),
        (["real/manage.py", "real/env/manage.py", "real/.hidden/manage.py"], ["real/manage.py"]),
    ],
)
def test_discovery_returns_exact_sorted_roots(preflight, paths, expected):
    root, _, launches = preflight
    plant(root, paths)
    assert wrap._find_manage_py() == sorted(discovered_path(path) for path in expected)
    assert not launches


@pytest.mark.parametrize("directory", [None, *EXCLUDED])
@pytest.mark.parametrize("harness", ["claude", "pi", "codex"])
@pytest.mark.parametrize("force", [False, True])
def test_failed_discovery_blocks_every_harness(preflight, capsys, directory, harness, force):
    root, calls, launches = preflight
    if directory:
        plant(root, [f"{directory}/manage.py"])
    args = ["wrap", "--run", "--harness", harness] + (["--force"] if force else [])
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 1
    output = capsys.readouterr()
    assert "No manage.py found (is this a Django project?)" in output.err
    assert "Preflight failed (1 error(s))" in output.out
    assert len(calls) == 2
    assert not launches


@pytest.mark.parametrize("harness", ["claude", "pi", "codex"])
def test_multiple_projects_remain_inspectable(preflight, capsys, harness):
    root, _, launches = preflight
    paths = ["z/project/manage.py", "a/project/manage.py"]
    plant(root, paths)
    main(["wrap", "--run", "--harness", harness])
    output = capsys.readouterr()
    assert not output.err
    assert "multiple — the agent will inspect" in output.out
    expected = sorted(discovered_path(path) for path in paths)
    assert output.out.index(expected[0]) < output.out.index(expected[1])
    assert "Preflight passed." in output.out
    assert launches == [harness]


@pytest.mark.parametrize("run", [False, True])
def test_missing_tools_warn_only_in_print_mode(preflight, monkeypatch, capsys, run):
    root, _, launches = preflight
    plant(root, ["nested/manage.py"])
    monkeypatch.setattr(wrap.shutil, "which", lambda name: name if name == "claude" else None)
    args = ["wrap"] + (["--run", "--harness", "claude"] if run else [])
    if run:
        with pytest.raises(SystemExit) as error:
            main(args)
        assert error.value.code == 1
    else:
        main(args)
    output = capsys.readouterr()
    for tool in ("node", "npm", "just"):
        stream = output.err if run else output.out
        assert f"{tool} not found" in stream
        expected = "required for wrapping and verification" if run else "post-wrap verification"
        assert expected in stream
    assert ("Preflight passed." in output.out) is not run
    assert not launches


def test_directory_symlinks_are_not_followed_without_platform_privileges(
    preflight, monkeypatch, capsys
):
    root, _, launches = preflight
    plant(root, ["linked/project/manage.py"])
    islink = os.path.islink
    # Model a directory symlink at the standard-library filesystem boundary;
    # Windows runners need no developer-mode symlink permission.
    monkeypatch.setattr(
        os.path,
        "islink",
        lambda path: os.path.abspath(path) == str(root / "linked") or islink(path),
    )
    assert wrap._find_manage_py() == []
    with pytest.raises(SystemExit) as error:
        main(["wrap", "--run", "--harness", "claude"])
    assert error.value.code == 1
    assert "No manage.py found" in capsys.readouterr().err
    assert not launches
