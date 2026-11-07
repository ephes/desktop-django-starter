"""Run doctor through the CLI with synthetic resources, tools and preferences."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
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
def installation(tmp_path, monkeypatch, isolated_user_dirs):
    package = tmp_path / "relocated package with spaces"
    for rel in ASSETS:
        path = package / "_assets" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic asset", encoding="utf-8")
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

    def forbidden(*args, **kwargs):
        pytest.fail("doctor must not launch, prompt, save config or stage assets")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(os, "execvp", forbidden)
    monkeypatch.setattr(config, "save_wrapper_config", forbidden)
    monkeypatch.setattr(wrap, "run_init", forbidden)
    monkeypatch.setattr("builtins.input", forbidden)
    return package, tools, isolated_user_dirs


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
        label = "electron/main.js" if missing.endswith("main.js") else Path(missing).name
        assert f"asset missing: {label}" in err
        assert str(package / "_assets" / missing) in err
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
