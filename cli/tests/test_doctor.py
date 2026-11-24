"""Run doctor through the CLI with synthetic resources, tools and preferences."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from asset_inventory import CANONICAL_ASSETS, MANIFEST
from dds import config, doctor, wrap
from dds.cli import main

ASSETS = (
    "skills/wrap-existing-django-in-electron/SKILL.md",
    "skills/wrap-existing-django-in-electron/prompt.md",
    "shells/electron/main.js",
)
TOOLS = ("node", "npm", "just", "git", "uv")


def snapshot(root: Path) -> dict[str, bytes | None]:
    return {
        str(p.relative_to(root)): p.read_bytes() if p.is_file() else None for p in root.rglob("*")
    }


@pytest.fixture
def tool_installation(tmp_path, monkeypatch, isolated_user_dirs):
    package = tmp_path / "relocated package with spaces"
    for rel in CANONICAL_ASSETS:
        path = package / "_assets" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic asset", encoding="utf-8")
    (package / MANIFEST.name).write_bytes(MANIFEST.read_bytes())
    bin_dir = tmp_path / "fake tools"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("PATHEXT", ".EXE")
    tools = {}
    for tool in TOOLS:
        path = bin_dir / (tool + ".EXE" if os.name == "nt" else tool)
        path.write_bytes(b"synthetic tool; never execute")
        path.chmod(0o755)
        tools[tool] = path
    monkeypatch.setattr(
        doctor, "files", lambda name: package if name == "dds" else pytest.fail(name)
    )

    return package, tools, isolated_user_dirs


@pytest.fixture
def installation(tool_installation, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("doctor must not launch, prompt, save config or stage assets")

    node = tool_installation[1]["node"]

    def probe(args, **kwargs):
        if args != [str(node), "--version"]:
            forbidden()
        return subprocess.CompletedProcess(args, 0, b"v22.12.0\n", b"")

    monkeypatch.setattr(subprocess, "run", probe)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(os, "execvp", forbidden)
    monkeypatch.setattr(config, "save_wrapper_config", forbidden)
    monkeypatch.setattr(wrap, "run_init", forbidden)
    monkeypatch.setattr("builtins.input", forbidden)
    return tool_installation


def invoke_readonly(installation, capsys):
    package, tools, user_dirs = installation
    roots = (package, next(iter(tools.values())).parent, user_dirs)
    before = [snapshot(root) for root in roots]
    code = 0
    try:
        main(["doctor"])
    except SystemExit as exc:
        code = exc.code
    assert [snapshot(root) for root in roots] == before
    output = capsys.readouterr()
    return code, output.out, output.err


@pytest.mark.parametrize("missing", [None, *ASSETS, *TOOLS])
def test_core_health_matrix(installation, capsys, missing):
    package, tools, _ = installation
    if missing in ASSETS:
        (package / "_assets" / missing).unlink()
    elif missing:
        tools[missing].unlink()
    code, out, err = invoke_readonly(installation, capsys)
    required_failure = missing is not None and missing != "uv"
    assert code == int(required_failure)
    assert str(package / "_assets") in out
    if missing in ASSETS:
        assert "bundled assets incomplete" in err
        assert missing in err
    elif required_failure:
        assert f"{missing}: not found" in err
        assert doctor.REQUIRED_TOOLS[missing] in err
    else:
        assert not err
        assert "Core checks passed" in out
        if missing == "uv":
            assert "-  uv: not found (Python package manager)" in out
    if required_failure:
        assert "Issues found: 1" in out
    else:
        for tool in TOOLS:
            if tool != missing:
                assert f"ok {tool}: {tools[tool]}" in out


def test_missing_non_sentinel_asset_fails(installation, capsys):
    package, _, _ = installation
    missing = "scripts/stage-backend.cjs"
    (package / "_assets" / missing).unlink()

    code, _, err = invoke_readonly(installation, capsys)
    assert code == 1
    assert missing in err


def test_missing_asset_diagnostic_is_bounded(installation, capsys):
    package, _, _ = installation
    for rel in CANONICAL_ASSETS:
        (package / "_assets" / rel).unlink()

    code, _, err = invoke_readonly(installation, capsys)
    assert code == 1
    assert f"{len(CANONICAL_ASSETS)} required file(s) missing" in err
    assert f"(+{len(CANONICAL_ASSETS) - 8} more)" in err
    listed = err.split("required file(s) missing: ", 1)[1].split(" (+", 1)[0]
    assert listed.split(", ") == CANONICAL_ASSETS[:8]


@pytest.mark.parametrize("manifest", [None, b"", b"\xff"])
def test_missing_or_unreadable_inventory_fails(installation, capsys, manifest):
    package, _, _ = installation
    path = package / MANIFEST.name
    if manifest is None:
        path.unlink()
    else:
        path.write_bytes(manifest)

    code, _, err = invoke_readonly(installation, capsys)
    assert code == 1
    assert "bundled asset inventory" in err


@pytest.mark.parametrize(
    ("saved", "installed", "advice", "attention"),
    [
        ('[wrap\nharness = "pi"', (), "invalid; run `dds init` to rewrite it", True),
        ('[wrap]\nharness = "unknown"', ("pi",), "invalid; run `dds init` to rewrite it", True),
        ('[wrap]\nharness = "pi"', ("pi", "codex"), "saved default harness `pi`", False),
        (
            '[wrap]\nharness = "pi"\nmodel = "synthetic-model"',
            ("pi",),
            "saved default harness `pi`",
            False,
        ),
        (
            '[wrap]\nharness = "claude"',
            ("codex",),
            "`claude` is not on PATH; run `dds init` or pass `--harness` explicitly",
            True,
        ),
        (None, (), "install `claude`, `pi`, or `codex`, then run `dds init`", True),
        (None, ("codex",), "auto-select `codex`", False),
        (
            None,
            ("claude", "pi", "codex"),
            "non-interactive runs need `dds init` or `--harness`",
            True,
        ),
    ],
)
def test_wrapper_resolution_matrix(
    installation, monkeypatch, capsys, saved, installed, advice, attention
):
    config_path = config.default_config_path()
    if saved is not None:
        config_path.parent.mkdir(parents=True)
        config_path.write_text(saved, encoding="utf-8")
    monkeypatch.setattr(
        doctor, "detect_installed_harnesses", lambda: {name: f"/fake/{name}" for name in installed}
    )
    code, out, err = invoke_readonly(installation, capsys)
    assert code == 0
    assert not err
    assert str(config_path) in out
    assert advice in out
    assert ("needs setup attention" in out) is attention
    assert ("All checks passed." in out) is not attention
    if saved and 'harness = "pi"' in saved and "[wrap]" in saved:
        assert "default harness: pi" in out
        expected = "default model: synthetic-model" if "model =" in saved else "harness default"
        assert expected in out
    for name in config.SUPPORTED_HARNESSES:
        expected = (
            f"harness {name}: /fake/{name}" if name in installed else f"harness {name}: not found"
        )
        assert expected in out


@pytest.mark.parametrize(
    ("harness", "model", "replacement"),
    [
        ("codex", "gpt-5.4", "gpt-6.2-sol"),
        ("pi", "openai/gpt-6.1-sol:high", "openai-codex/gpt-6.2-sol"),
        ("codex", "gpt-6.2-astra", None),
        ("pi", "openai-codex/gpt-6.2-sol:high", None),
        ("pi", "ollama/gpt-5.4", None),
    ],
)
def test_saved_model_matches_wrap_preflight(
    installation, monkeypatch, capsys, harness, model, replacement
):
    package, tools, _ = installation
    executable = tools["git"].with_name(harness + tools["git"].suffix)
    executable.write_bytes(b"synthetic harness; never execute")
    executable.chmod(0o755)
    saved = config.default_config_path()
    saved.parent.mkdir(parents=True)
    saved.write_text(f'[wrap]\nharness = "{harness}"\nmodel = "{model}"\n', encoding="utf-8")

    code, out, err = invoke_readonly(installation, capsys)
    assert code == 0
    assert not err
    assert ("needs setup attention" in out) is (replacement is not None)
    assert ("All checks passed." in out) is (replacement is None)
    assert ("will use saved default harness" in out) is (replacement is None)

    if replacement:
        with pytest.raises(SystemExit) as exit_info:
            main(["wrap", "--run"])
        assert exit_info.value.code == 1
        wrap_err = capsys.readouterr().err
        for message in (
            repr(model),
            "approved GPT-6.2 model list",
            "dds init",
            f"--model {replacement}",
        ):
            assert message in out
            assert message in wrap_err
        return

    monkeypatch.chdir(package)
    (package / "manage.py").touch()
    monkeypatch.setattr(wrap, "SKILL_PATH", package / "_assets" / ASSETS[0])
    monkeypatch.setattr(wrap, "PROMPT_TEMPLATE", package / "_assets" / ASSETS[1])
    probe = subprocess.run

    def preflight(args, **kwargs):
        if args in (["git", "rev-parse", "--git-dir"], ["git", "status", "--porcelain"]):
            return subprocess.CompletedProcess(args, 0, "", "")
        return probe(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", preflight)
    launches = []
    monkeypatch.setattr(os, "execvp", lambda name, argv: launches.append((name, argv)))

    main(["wrap", "--run"])

    [(name, argv)] = launches
    assert name == harness
    assert argv[argv.index("--model") + 1] == model


@pytest.mark.skipif(os.name == "nt", reason="synthetic Node executable uses a POSIX shell")
@pytest.mark.parametrize("mode", ["doctor", "print", "run"])
@pytest.mark.parametrize(
    ("script", "diagnostic", "supported"),
    [
        ("printf 'v22.12.0\\n'", "v22.12.0", True),
        ("printf 'v23.0.0\\n'", "v23.0.0", True),
        ("printf 'v22.11.99\\n'", "v22.11.99", False),
        ("printf 'unknown version\\n'", "unrecognized version", False),
        ("printf 'v23.0.0\\n'; exit 7", "exit 7", False),
        ("exec /bin/sleep 30", "timed out", False),
    ],
)
def test_node_version_prerequisite(
    tool_installation, monkeypatch, capsys, mode, script, diagnostic, supported
):
    package, tools, _ = tool_installation
    node = tools["node"]
    node.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
    codex = node.with_name("codex")
    codex.touch()
    codex.chmod(0o755)
    monkeypatch.chdir(package)
    (package / "manage.py").touch()
    monkeypatch.setattr(wrap, "SKILL_PATH", package / "_assets" / ASSETS[0])
    monkeypatch.setattr(wrap, "PROMPT_TEMPLATE", package / "_assets" / ASSETS[1])
    real_run = subprocess.run

    def run_local_check(args, **kwargs):
        if args == [str(node), "--version"]:
            assert 0 < kwargs["timeout"] <= 5
            return real_run(args, **kwargs)
        assert mode != "doctor"
        assert args in (["git", "rev-parse", "--git-dir"], ["git", "status", "--porcelain"])
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run_local_check)
    launches = []
    monkeypatch.setattr(os, "execvp", lambda name, argv: launches.append(name))

    if mode == "doctor":
        code, out, err = invoke_readonly(tool_installation, capsys)
        assert code == int(not supported)
    else:
        args = ["wrap", "--force"] + (["--run", "--harness", "codex"] if mode == "run" else [])
        if mode == "run" and not supported:
            with pytest.raises(SystemExit) as exit_info:
                main(args)
            assert exit_info.value.code == 1
        else:
            main(args)
        out, err = capsys.readouterr()
        assert ("Preflight passed." in out) is (supported or mode == "print")
        if mode == "print":
            assert "To wrap this project:" in out

    if supported:
        assert diagnostic in out
        assert not err
    else:
        message = out if mode == "print" else err
        assert diagnostic in message
        assert "Node.js 22.12 or newer" in message
    assert launches == (["codex"] if supported and mode == "run" else [])
