"""Exercise temporary project discovery through actual CLI preflight."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from dds import wrap
from dds.cli import main
from dds.config import WrapperConfig, default_config_path, save_wrapper_config

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
    monkeypatch.setattr(wrap, "probe_node_version", lambda path: "v22.12.0")
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


@pytest.mark.parametrize("mode", ["launch", "help", "manual", "setup"])
def test_pi_default_model_is_used_and_advertised(preflight, capsys, monkeypatch, mode):
    root, _, _ = preflight
    plant(root, ["manage.py"])
    approved_model = "openai-codex/gpt-6.2-sol"

    if mode == "launch":
        commands = []
        monkeypatch.setattr(wrap.os, "execvp", lambda name, argv: commands.append(argv))
        main(["wrap", "--run", "--harness", "pi"])
        assert commands[0][:3] == ["pi", "--model", approved_model]
    elif mode == "help":
        monkeypatch.setenv("COLUMNS", "200")
        with pytest.raises(SystemExit) as error:
            main(["wrap", "--help"])
        assert error.value.code == 0
        assert f"pi defaults to {approved_model}" in " ".join(capsys.readouterr().out.split())
    elif mode == "manual":
        main(["wrap"])
        assert f"dds wrap --run --harness pi --model {approved_model}" in capsys.readouterr().out
    else:
        prompts = []

        def answer(prompt):
            prompts.append(prompt)
            return ""

        monkeypatch.setattr(wrap, "detect_installed_harnesses", lambda: {"pi": "/fake/pi"})
        monkeypatch.setattr("builtins.input", answer)
        wrap._run_setup_flow(existing_config=None, config_path=wrap.default_config_path())
        assert approved_model in prompts[-1]
        assert f"Default model: {approved_model}" in capsys.readouterr().out


@pytest.mark.parametrize("source", ["saved", "explicit"])
@pytest.mark.parametrize(
    ("harness", "model", "replacement"),
    [
        ("codex", "gpt-5.4", "gpt-6.2-sol"),
        ("codex", "o3", "gpt-6.2-sol"),
        ("pi", "openai-codex/gpt-5.4", "openai-codex/gpt-6.2-sol"),
        ("pi", " OpenAI / gpt-6.1-sol:high ", "openai-codex/gpt-6.2-sol"),
        ("pi", "gpt-5.4-mini", "openai-codex/gpt-6.2-sol"),
    ],
)
def test_disallowed_openai_model_stops_before_launch(
    preflight, capsys, source, harness, model, replacement
):
    root, git_calls, launches = preflight
    plant(root, ["manage.py"])
    config_path = default_config_path()
    saved = WrapperConfig(harness, model if source == "saved" else replacement)
    save_wrapper_config(saved, config_path)
    args = ["wrap", "--run", "--force"]
    if source == "explicit":
        args += ["--model", model]

    with pytest.raises(SystemExit) as error:
        main(args)

    assert error.value.code == 1
    diagnostic = capsys.readouterr().err
    assert repr(model) in diagnostic
    assert f"--model {replacement}" in diagnostic
    assert ("dds init" in diagnostic) is (source == "saved")
    assert not git_calls
    assert not launches
    assert wrap.load_wrapper_config(config_path) == saved


@pytest.mark.parametrize(
    ("harness", "approved", "saved"),
    [
        ("codex", "gpt-6.2-sol", "gpt-5.4"),
        ("codex", "gpt-6.2-astra", "gpt-5.4"),
        ("codex", "qwen3-coder", None),
        ("pi", "openai/gpt-6.2-sol:high", "openai/gpt-5.4"),
        ("pi", "ollama/gpt-5.4", "openai-codex/gpt-5.4"),
        ("pi", "gpt-oss-120b", "openai-codex/gpt-5.4"),
        ("claude", "claude-opus-4-6", None),
    ],
)
def test_selected_model_is_passed_through(preflight, monkeypatch, harness, approved, saved):
    root, _, _ = preflight
    plant(root, ["manage.py"])
    save_wrapper_config(WrapperConfig(harness, saved), default_config_path())
    selected_models = []

    def record_exec(name, argv):
        assert name == harness
        selected_models.append(argv[argv.index("--model") + 1])

    monkeypatch.setattr(wrap.os, "execvp", record_exec)
    monkeypatch.setattr(
        wrap, "_run_claude", lambda prompt, assets, model: selected_models.append(model)
    )
    main(["wrap", "--run", "--model", approved])

    assert selected_models == [approved]


@pytest.mark.parametrize(
    ("harness", "saved", "answers", "expected"),
    [
        ("codex", None, ["gpt-5.4", "gpt-6.2-sol"], "gpt-6.2-sol"),
        ("pi", None, ["openai-codex/gpt-5.4:high", ""], None),
        ("codex", "gpt-5.4", ["gpt-6.2-astra"], "gpt-6.2-astra"),
        ("pi", "openai-codex/gpt-5.4", [""], None),
        ("pi", "openai-codex/gpt-5.4", ["-"], None),
        ("codex", "qwen3-coder", [""], "qwen3-coder"),
    ],
)
def test_setup_rejects_unapproved_openai_models(
    preflight, monkeypatch, capsys, harness, saved, answers, expected
):
    config_path = default_config_path()
    existing = WrapperConfig(harness, saved) if saved else None
    pending = iter([""] + answers)
    prompts = []

    def answer(prompt):
        prompts.append(prompt)
        return next(pending)

    monkeypatch.setattr(wrap, "detect_installed_harnesses", lambda: {harness: f"/fake/{harness}"})
    monkeypatch.setattr("builtins.input", answer)
    config = wrap._run_setup_flow(existing_config=existing, config_path=config_path)

    assert config == WrapperConfig(harness, expected)
    assert wrap.load_wrapper_config(config_path) == config
    assert len(prompts) == len(answers) + 1
    output = capsys.readouterr().out
    unapproved = [a for a in [saved, *answers] if a and a != "-" and a != expected]
    for model in unapproved:
        assert f"{model!r}" in output
        assert "outside the approved GPT-6.2 model list" in output
    if not unapproved:
        assert "outside the approved" not in output
    if saved and saved != expected:
        assert f"[{saved}]" not in "".join(prompts)


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
