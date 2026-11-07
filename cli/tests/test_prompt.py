"""Prompt-only CLI calls use relocated UTF-8 resources without setup or launches."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from dds import wrap
from dds.cli import main
from dds.config import default_config_path

REFERENCES = (
    "skills/wrap-existing-django-in-electron/SKILL.md",
    "docs/architecture.md",
    "docs/specification.md",
    "shells/electron/main.js",
    "scripts/stage-backend.cjs",
)
ORDINARY = (
    "desktop-django-starter; ../desktop-django; ../desktop-django-starter-extra/doc.md; "
    "bare root `../desktop-django-starter`"
)


def snapshot(root):
    return {
        str(p.relative_to(root)): p.read_bytes() if p.is_file() else None for p in root.rglob("*")
    }


@pytest.fixture
def resources(tmp_path, monkeypatch):
    def create(name):
        assets = tmp_path / name / "_assets"
        for rel in REFERENCES:
            path = assets / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"synthetic {rel}", encoding="utf-8")
        template = assets / "skills/wrap-existing-django-in-electron/prompt.md"
        content = "\n".join(f"Read `../desktop-django-starter/{rel}`" for rel in REFERENCES)
        content += f"\nGrüße 🐎\n{ORDINARY}\n"
        template.write_text(content, encoding="utf-8")
        monkeypatch.setattr(wrap, "ASSETS_PATH", assets)
        monkeypatch.setattr(wrap, "PROMPT_TEMPLATE", template)
        monkeypatch.setattr(wrap, "SKILL_PATH", assets / REFERENCES[0])
        return assets, template, content

    return create


@pytest.fixture
def forbid_setup(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("prompt emission must bypass tools, project discovery and wrapper setup")

    for name in (
        "_find_manage_py",
        "_resolve_run_config",
        "_run_claude",
        "run_init",
        "load_wrapper_config",
        "save_wrapper_config",
        "detect_installed_harnesses",
    ):
        monkeypatch.setattr(wrap, name, forbidden)
    monkeypatch.setattr(wrap.shutil, "which", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(os, "execvp", forbidden)
    monkeypatch.setattr("builtins.input", forbidden)
    monkeypatch.setenv("PATH", "")


@pytest.mark.parametrize("name", ["package with spaces", "Grüße 🐎", "literal ' $ & ; (shell)`"])
@pytest.mark.parametrize("run", [False, True])
@pytest.mark.parametrize("saved", [False, True])
def test_emit_prompt_is_literal_relocated_and_readonly(
    resources, forbid_setup, isolated_user_dirs, tmp_path, monkeypatch, capsys, name, run, saved
):
    assets, template, _ = resources(name)
    config = default_config_path()
    assert not config.exists()
    # A broken saved config must also be ignored by the prompt-only path.
    if saved:
        config.parent.mkdir(parents=True)
        config.write_text("[invalid config", encoding="utf-8")
    cwd = tmp_path / "unrelated target with no project"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    before = (snapshot(tmp_path), snapshot(isolated_user_dirs))
    args = ["wrap", "--emit-prompt"] + (["--run"] if run else [])
    main(args)
    output = capsys.readouterr()
    expected = "\n".join(f"Read `{assets}/{rel}`" for rel in REFERENCES)
    assert output.out == expected + f"\nGrüße 🐎\n{ORDINARY}\n\n"
    assert not output.err
    for rel in REFERENCES:
        assert (assets / rel).is_file()
        assert f"`{assets}/{rel}`" in output.out
    assert (snapshot(tmp_path), snapshot(isolated_user_dirs)) == before


@pytest.mark.parametrize("fault", ["missing", "directory", "unreadable", "invalid-utf8"])
def test_bad_prompt_is_an_actionable_cli_error(
    resources, forbid_setup, isolated_user_dirs, tmp_path, monkeypatch, capsys, fault
):
    _, template, _ = resources("broken package")
    if fault == "missing":
        template.unlink()
    elif fault == "directory":
        template.unlink()
        template.mkdir()
    elif fault == "invalid-utf8":
        template.write_bytes(b"\xff\xfe")
    else:
        read = Path.read_text

        def unreadable(path, *args, **kwargs):
            if path == template:
                raise PermissionError("synthetic read denied")
            return read(path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", unreadable)
    before = (snapshot(tmp_path), snapshot(isolated_user_dirs))
    with pytest.raises(SystemExit) as error:
        main(["wrap", "--emit-prompt"])
    assert error.value.code == 1
    output = capsys.readouterr()
    assert not output.out
    assert "error: could not read wrapping prompt" in output.err
    assert str(template) in output.err
    assert "Traceback" not in output.err
    assert (snapshot(tmp_path), snapshot(isolated_user_dirs)) == before
