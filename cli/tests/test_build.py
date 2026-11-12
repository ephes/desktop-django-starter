"""Exercise Hatch admission and a relocated offline wheel installation."""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from asset_inventory import CANONICAL_ASSETS
from hatchling.build import build_sdist, build_wheel

CLI_ROOT = Path(__file__).resolve().parents[1]
BUILDERS = {"wheel": build_wheel, "sdist": build_sdist}


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "synthetic build"
    root.mkdir()
    for name in ("pyproject.toml", "hatch_build.py", "asset_inventory.py", "README.md"):
        shutil.copy2(CLI_ROOT / name, root / name)
    shutil.copytree(
        CLI_ROOT / "src",
        root / "src",
        ignore=shutil.ignore_patterns("_assets", ".assets-sync-*", "__pycache__"),
    )
    assets = root / "src" / "dds" / "_assets"
    for rel in CANONICAL_ASSETS:
        path = assets / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"synthetic content for {rel}\n", encoding="utf-8")
    # Synthetic reference documents exercise all inventory paths, including
    # dot directories, rather than relying on a tiny sentinel-only wheel.
    skill = assets / "skills/wrap-existing-django-in-electron/SKILL.md"
    skill.write_text("\n".join(f"Read `{rel}`" for rel in CANONICAL_ASSETS), encoding="utf-8")
    prompt = assets / "skills/wrap-existing-django-in-electron/prompt.md"
    prompt.write_text(
        "\n".join(f"Read `../desktop-django-starter/{rel}`" for rel in CANONICAL_ASSETS),
        encoding="utf-8",
    )
    monkeypatch.chdir(root)

    def no_network(*args, **kwargs):
        pytest.fail("build tests must be offline")

    monkeypatch.setattr(socket, "socket", no_network)
    monkeypatch.setenv("UV_OFFLINE", "true")
    return root, assets


@pytest.mark.parametrize("target", BUILDERS)
@pytest.mark.parametrize("missing", CANONICAL_ASSETS)
@pytest.mark.parametrize("kind", ["absent", "directory"])
def test_incomplete_builds_fail_before_artifact(project, target, missing, kind):
    root, assets = project
    path = assets / missing
    path.unlink()
    if kind == "directory":
        path.mkdir()
    with pytest.raises(RuntimeError, match=re.escape(missing)) as error:
        BUILDERS[target](str(root / "dist"))
    assert "just cli-sync-assets" in str(error.value)
    assert not list((root / "dist").glob("*.whl"))
    assert not list((root / "dist").glob("*.tar.gz"))


@pytest.mark.parametrize("target", BUILDERS)
def test_skill_alone_is_not_a_complete_distribution(project, target):
    root, assets = project
    for rel in CANONICAL_ASSETS:
        if not rel.endswith("SKILL.md"):
            (assets / rel).unlink()
    with pytest.raises(RuntimeError, match="required file") as error:
        BUILDERS[target](str(root / "dist"))
    assert "+" in str(error.value)
    assert len(str(error.value)) < 700
    assert not list((root / "dist").glob("*.whl"))
    assert not list((root / "dist").glob("*.tar.gz"))


@pytest.mark.parametrize("target", BUILDERS)
def test_complete_build_is_admitted(project, target):
    root, _ = project
    artifact = BUILDERS[target](str(root / "dist"))
    assert (root / "dist" / artifact).is_file()


def tree(root):
    return {
        str(p.relative_to(root)): p.read_bytes() if p.is_file() else None for p in root.rglob("*")
    }


def test_wheel_installs_and_runs_after_relocation(project, tmp_path, monkeypatch):
    root, assets = project
    expected = {rel: (assets / rel).read_bytes() for rel in CANONICAL_ASSETS}
    wheel = root / "dist" / build_wheel(str(root / "dist"))
    with zipfile.ZipFile(wheel) as archive:
        for rel, content in expected.items():
            assert archive.read(f"dds/_assets/{rel}") == content
    uv = shutil.which("uv")
    assert uv, "uv is required for the offline install probe"
    environment = tmp_path / "installed environment with spaces"
    subprocess.run(
        [uv, "venv", "--no-python-downloads", "--python", sys.executable, str(environment)],
        check=True,
        capture_output=True,
    )
    scripts = environment / ("Scripts" if os.name == "nt" else "bin")
    python = scripts / ("python.exe" if os.name == "nt" else "python")
    subprocess.run(
        [uv, "pip", "install", "--offline", "--no-deps", "--python", str(python), str(wheel)],
        check=True,
        capture_output=True,
    )
    # Move the installed package after install, then remove all build sources.
    site = subprocess.run(
        [str(python), "-c", "import dds; print(dds.__path__[0])"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    relocated = tmp_path / "relocated package with spaces"
    relocated.mkdir()
    shutil.move(site, relocated / "dds")
    # The fixture runs the build from inside the source tree; leave it first,
    # because Windows refuses to delete a process's current directory.
    monkeypatch.chdir(tmp_path)
    shutil.rmtree(root)
    assert not root.exists()
    cwd = tmp_path / "unrelated cwd with spaces"
    cwd.mkdir()
    home = tmp_path / "probe home"
    home.mkdir()
    tools = tmp_path / "fake tools"
    tools.mkdir()
    for name in ("node", "npm", "just", "git"):
        path = tools / (name + ".EXE" if os.name == "nt" else name)
        path.write_bytes(b"never execute")
        path.chmod(0o755)
    # The installed entry point must not start any subprocess, exec a harness,
    # prompt for preferences or use the network. sitecustomize guards children.
    (relocated / "sitecustomize.py").write_text(
        "import os, socket, subprocess\n"
        "def forbidden(*args, **kwargs):\n"
        "    raise AssertionError('installed probe must be read-only and offline')\n"
        "subprocess.Popen = forbidden\nos.execvp = forbidden\n"
        "socket.socket = forbidden\n",
        encoding="utf-8",
    )
    env = dict(
        os.environ,
        PYTHONPATH=str(relocated),
        PYTHONDONTWRITEBYTECODE="1",
        PATH=str(tools),
        PATHEXT=".EXE",
    )
    for key in (
        "HOME",
        "USERPROFILE",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
        "APPDATA",
        "LOCALAPPDATA",
    ):
        env[key] = str(home)
    before = {str(p): tree(p) for p in (home, cwd, relocated, tools)}
    dds = scripts / ("dds.exe" if os.name == "nt" else "dds")
    for args in (["--help"], ["wrap", "--emit-prompt"], ["doctor"]):
        result = subprocess.run(
            [str(dds), *args], cwd=cwd, env=env, capture_output=True, text=True, check=True
        )
        assert not result.stderr
        if args == ["--help"]:
            assert "Wrap any Django project" in result.stdout
        elif args[0] == "wrap":
            installed_assets = relocated / "dds" / "_assets"
            assert "../desktop-django-starter" not in result.stdout
            references = re.findall(r"Read `([^`]+)`", result.stdout)
            assert len(references) == len(expected)
            for reference in references:
                rel = Path(reference).relative_to(installed_assets).as_posix()
                assert Path(reference).read_bytes() == expected[rel]
            skill = installed_assets / "skills/wrap-existing-django-in-electron/SKILL.md"
            for rel in re.findall(r"Read `([^`]+)`", skill.read_text(encoding="utf-8")):
                assert (installed_assets / rel).is_file()
        else:
            assert "Core checks passed" in result.stdout
            assert str(relocated / "dds" / "_assets") in result.stdout
    assert {str(p): tree(p) for p in (home, cwd, relocated, tools)} == before
