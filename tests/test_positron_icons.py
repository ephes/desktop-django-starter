"""Run real icon orchestration with fake platform tools and synthetic artwork."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "shells/positron/scripts/generate-icons.py"
OLD = {"app-icon.png": b"old-png", "app-icon.icns": b"old-icns"}


def tree(root):
    return {
        p.relative_to(root).as_posix(): p.read_bytes() if p.is_file() else None
        for p in root.rglob("*")
    }


@pytest.fixture
def icons(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("positron_icons", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    script = tmp_path / "repo with spaces/shells/positron/scripts/generate-icons.py"
    script.parent.mkdir(parents=True)
    brand = script.parents[3] / "assets/brand/flying-stable-app-icon.svg"
    brand.parent.mkdir(parents=True)
    brand.write_text("<svg/>", encoding="utf-8")
    monkeypatch.setattr(module, "__file__", str(script))
    monkeypatch.setattr(module, "sys", SimpleNamespace(platform="darwin", stderr=sys.stderr))
    monkeypatch.setattr(module.shutil, "which", lambda name: f"/fake/{name}")
    resources = script.parents[1] / "resources"
    resources.mkdir()
    for name, content in OLD.items():
        (resources / name).write_bytes(content)
    # This pre-existing scratch name belongs to a caller and must survive.
    (resources / "app-icon.iconset").mkdir()
    (resources / "app-icon.iconset/caller.txt").write_bytes(b"caller owned")
    (resources / ".gitkeep").write_bytes(b"keep")
    return module, resources


class Renderer:
    def __init__(self, fail=None, empty=None):
        self.fail = fail
        self.empty = empty
        self.calls = []
        self.iconsets = []

    def __call__(self, command, *, check):
        assert check is True
        self.calls.append(command)
        output = Path(command[-1])
        if command[0] == "rsvg-convert":
            assert command[1] == "--width" and command[3] == "--height"
            assert command[2] == command[4]
            assert Path(command[5]).read_text(encoding="utf-8") == "<svg/>"
            assert command[-2] == "--output"
            content = f"png-{command[2]}".encode()
        else:
            assert command[:3] == ["iconutil", "-c", "icns"]
            assert command[-2] == "-o"
            iconset = Path(command[3])
            assert iconset.suffix == ".iconset"
            expected = {}
            for size in (16, 32, 128, 256, 512):
                for scale, suffix in ((1, ""), (2, "@2x")):
                    expected[f"icon_{size}x{size}{suffix}.png"] = f"png-{size * scale}".encode()
            assert tree(iconset) == expected
            self.iconsets.append(iconset)
            content = b"new-icns"
        output.write_bytes(b"" if len(self.calls) == self.empty else content)
        if len(self.calls) == self.fail:
            raise subprocess.CalledProcessError(1, command)


@pytest.mark.parametrize("platform", ["darwin", "linux", "win32"])
def test_success_publishes_platform_set_and_cleans_owned_work(icons, monkeypatch, platform):
    module, resources = icons
    before = tree(resources)
    renderer = Renderer()
    monkeypatch.setattr(module, "sys", SimpleNamespace(platform=platform, stderr=sys.stderr))
    monkeypatch.setattr(module.subprocess, "run", renderer)
    assert module.main() == 0
    before["app-icon.png"] = b"png-512"
    if platform == "darwin":
        before["app-icon.icns"] = b"new-icns"
    assert tree(resources) == before
    assert len(renderer.calls) == (12 if platform == "darwin" else 1)
    assert all(not path.exists() for path in renderer.iconsets)


@pytest.mark.parametrize("missing", ["rsvg-convert", "iconutil"])
def test_preflight_fails_before_render_or_writes(icons, monkeypatch, missing):
    module, resources = icons
    before = tree(resources)
    monkeypatch.setattr(module.shutil, "which", lambda name: None if name == missing else name)
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: pytest.fail("render started"))
    with pytest.raises(SystemExit, match=missing):
        module.main()
    assert tree(resources) == before


@pytest.mark.parametrize("step", range(1, 13))
@pytest.mark.parametrize("fault", ["failure", "empty", "missing"])
def test_every_renderer_boundary_preserves_previous_set_and_retry(icons, monkeypatch, step, fault):
    module, resources = icons
    before = tree(resources)
    renderer = Renderer(
        fail=step if fault == "failure" else None, empty=step if fault == "empty" else None
    )

    def run(command, **kwargs):
        renderer(command, **kwargs)
        if fault == "missing" and len(renderer.calls) == step:
            Path(command[-1]).unlink()

    monkeypatch.setattr(module.subprocess, "run", run)
    with pytest.raises((subprocess.CalledProcessError, RuntimeError)):
        module.main()
    assert len(renderer.calls) == step
    assert tree(resources) == before
    monkeypatch.setattr(module.subprocess, "run", Renderer())
    assert module.main() == 0
    before.update({"app-icon.png": b"png-512", "app-icon.icns": b"new-icns"})
    assert tree(resources) == before


@pytest.mark.parametrize("name", OLD)
@pytest.mark.parametrize("existing", [True, False])
@pytest.mark.parametrize("failure", [OSError, KeyboardInterrupt])
def test_publication_failure_restores_complete_previous_set(
    icons, monkeypatch, name, existing, failure
):
    module, resources = icons
    if not existing:
        for old in OLD:
            (resources / old).unlink()
    before = tree(resources)
    monkeypatch.setattr(module.subprocess, "run", Renderer())
    replace = Path.replace
    failed = []

    def fail(source, target):
        if source.parent.name == "staged" and source.name == name:
            failed.append(source)
            raise failure("publication failed")
        return replace(source, target)

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(failure, match="publication failed"):
        module.main()
    assert len(failed) == 1
    assert tree(resources) == before
    monkeypatch.setattr(Path, "replace", replace)
    assert module.main() == 0


@pytest.mark.parametrize("name", OLD)
def test_backup_failure_leaves_originals_and_cleans_work(icons, monkeypatch, name):
    module, resources = icons
    before = tree(resources)
    monkeypatch.setattr(module.subprocess, "run", Renderer())
    copy = module.shutil.copy2
    failed = []

    def fail(source, target):
        if source.name == name:
            failed.append(source)
            raise OSError("backup failed")
        return copy(source, target)

    monkeypatch.setattr(module.shutil, "copy2", fail)
    with pytest.raises(OSError, match="backup failed"):
        module.main()
    assert len(failed) == 1
    assert tree(resources) == before


@pytest.mark.parametrize("failure", [OSError, KeyboardInterrupt, RuntimeError])
def test_rollback_failure_retains_named_recovery_data(icons, monkeypatch, failure):
    module, resources = icons
    monkeypatch.setattr(module.subprocess, "run", Renderer())
    replace = Path.replace
    failed = []

    def fail(source, target):
        if (source.parent.name == "staged" and source.name == "app-icon.icns") or (
            source.parent.name == "previous" and source.name == "app-icon.png"
        ):
            failed.append(source)
            raise failure("replacement failed")
        return replace(source, target)

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(RuntimeError, match="recovery directory retained") as error:
        module.main()
    assert len(failed) == 2
    assert isinstance(error.value.__cause__, failure)
    (work,) = resources.glob(".app-icons-*")
    assert tree(work / "previous") == OLD
    assert str(work / "previous") in str(error.value)
    assert not (work / "staged").exists()
    assert not list(work.rglob("*.iconset"))


def test_interleaved_renderers_keep_owned_iconsets(icons, monkeypatch):
    module, resources = icons
    ready = threading.Event()
    failed_done = threading.Event()
    healthy_iconsets = []
    failing_calls = []
    renderer = Renderer()

    def run(command, **kwargs):
        if threading.current_thread().name.startswith("healthy"):
            if command[0] == "iconutil":
                iconset = Path(command[3])
                healthy_iconsets.append(iconset)
                assert ready.wait(5)
                assert failed_done.wait(5)
                assert len(list(iconset.iterdir())) == 10
            renderer(command, **kwargs)
        else:
            failing_calls.append(command)
            if len(failing_calls) == 3:
                raise subprocess.CalledProcessError(1, command)
            renderer(command, **kwargs)

    monkeypatch.setattr(module.subprocess, "run", run)

    # Start the healthy run and pause it at iconutil. Then the failing run
    # renders into another iconset and cleans it while the first is active.
    def signal(command, **kwargs):
        if threading.current_thread().name.startswith("healthy") and command[0] == "iconutil":
            ready.set()
        return run(command, **kwargs)

    monkeypatch.setattr(module.subprocess, "run", signal)
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="healthy") as pool:
        future = pool.submit(module.main)
        assert ready.wait(5)
        try:
            with pytest.raises(subprocess.CalledProcessError):
                module.main()
        finally:
            failed_done.set()
        assert future.result(timeout=5) == 0
    assert len(failing_calls) == 3
    assert len(healthy_iconsets) == 1
    assert not healthy_iconsets[0].exists()
    assert (resources / "app-icon.png").read_bytes() == b"png-512"
    assert (resources / "app-icon.icns").read_bytes() == b"new-icns"
    assert (resources / "app-icon.iconset/caller.txt").read_bytes() == b"caller owned"
    assert not list(resources.glob(".app-icons-*"))


def test_staging_directory_failure_cleans_owned_work(icons, monkeypatch):
    module, resources = icons
    before = tree(resources)
    mkdir = Path.mkdir
    failed = []

    def fail(path, *args, **kwargs):
        if path.name == "staged":
            failed.append(path)
            raise OSError("staging failed")
        return mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail)
    with pytest.raises(OSError, match="staging failed"):
        module.main()
    assert len(failed) == 1
    assert tree(resources) == before


@pytest.mark.parametrize("render_fails", [False, True])
def test_cleanup_failure_keeps_primary_error_and_published_set(
    icons, monkeypatch, capsys, render_fails
):
    module, resources = icons
    before = tree(resources)
    module.sys.stderr = sys.stderr
    renderer = Renderer(fail=2 if render_fails else None)
    monkeypatch.setattr(module.subprocess, "run", renderer)
    remove = module.shutil.rmtree
    failed = []

    def fail(path, *args, **kwargs):
        if Path(path).name.startswith(".app-icons-"):
            failed.append(path)
            raise OSError("cleanup failed")
        return remove(path, *args, **kwargs)

    monkeypatch.setattr(module.shutil, "rmtree", fail)
    expected = subprocess.CalledProcessError if render_fails else OSError
    with pytest.raises(expected):
        module.main()
    assert len(failed) == 1
    if render_fails:
        assert "Icon cleanup incomplete" in capsys.readouterr().err
    else:
        before.update({"app-icon.png": b"png-512", "app-icon.icns": b"new-icns"})
    (work,) = resources.glob(".app-icons-*")
    remove(work)
    assert tree(resources) == before


def test_first_publication_failed_removal_retains_recovery_directory(icons, monkeypatch):
    module, resources = icons
    for name in OLD:
        (resources / name).unlink()
    monkeypatch.setattr(module.subprocess, "run", Renderer())
    replace, unlink = Path.replace, Path.unlink
    faults = []

    def fail_replace(source, target):
        if source.parent.name == "staged" and source.name == "app-icon.icns":
            faults.append("publish")
            raise OSError("publish failed")
        return replace(source, target)

    def fail_unlink(path, *args, **kwargs):
        if path == resources / "app-icon.png":
            faults.append("unlink")
            raise OSError("removal failed")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "replace", fail_replace)
    monkeypatch.setattr(Path, "unlink", fail_unlink)
    with pytest.raises(RuntimeError, match="recovery directory retained") as error:
        module.main()
    assert faults == ["publish", "unlink"]
    assert "previous icons retained" not in str(error.value)
    (work,) = resources.glob(".app-icons-*")
    assert tree(work / "previous") == {}
    assert (resources / "app-icon.png").read_bytes() == b"png-512"
