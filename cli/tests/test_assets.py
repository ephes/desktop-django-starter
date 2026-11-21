"""Verify that all bundled assets exist in the canonical repo locations.

This catches drift: if a canonical file is renamed or removed, this test fails
before a broken wheel is published.
"""

from __future__ import annotations

import os
import re
import shutil
import tarfile
import traceback
import zipfile
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
from threading import Event

import pytest
import sync_assets
from asset_lock import ASSET_MARKER
from hatchling.build import build_sdist, build_wheel
from sync_assets import CANONICAL_ASSETS

CLI_DIR = Path(__file__).resolve().parent.parent

REPO_ROOT = CLI_DIR.parent


@pytest.mark.parametrize("rel_path", CANONICAL_ASSETS)
def test_canonical_asset_exists(rel_path: str) -> None:
    full = REPO_ROOT / rel_path
    assert full.is_file(), f"canonical asset missing: {full}"


_RELATIVE_REQUIRE = re.compile(r"""require\(\s*["'](\.{1,2}/[^"']+)["']\s*\)""")


@pytest.mark.parametrize(
    "rel_path", [rel for rel in CANONICAL_ASSETS if rel.endswith((".js", ".cjs"))]
)
def test_bundled_relative_requires_resolve_inside_assets(rel_path: str) -> None:
    """Every relative require() in a bundled script must point at a bundled file.

    The wrap prompt copies these files into another repo, so a module that is
    required but not bundled makes the wrapped app fail at startup.
    """
    bundled = set(CANONICAL_ASSETS)
    source = (REPO_ROOT / rel_path).read_text()
    base = Path(rel_path).parent
    for target in _RELATIVE_REQUIRE.findall(source):
        resolved = os.path.normpath(base / target).replace(os.sep, "/")
        candidates = {resolved, f"{resolved}.js", f"{resolved}.cjs"}
        assert candidates & bundled, f"{rel_path} requires {target}, which is not bundled"


@pytest.fixture
def asset_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    assets = tmp_path / "package" / "_assets"
    for rel in ("first.txt", "nested/last.txt"):
        src = repo / rel
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_bytes(rel.encode())
    assets.mkdir(parents=True)
    (assets / "stale.txt").write_bytes(b"previous assets")
    (assets / ".gitkeep").write_bytes(b"placeholder")
    monkeypatch.setattr(sync_assets, "REPO_ROOT", repo)
    monkeypatch.setattr(sync_assets, "ASSETS_DIR", assets)
    monkeypatch.setattr(sync_assets, "CANONICAL_ASSETS", ["first.txt", "nested/last.txt"])
    return repo, assets


def tree_bytes(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_missing_late_input_preserves_assets(asset_tree: tuple[Path, Path]) -> None:
    repo, assets = asset_tree
    before = tree_bytes(assets)
    (repo / "nested/last.txt").unlink()
    with pytest.raises(SystemExit, match="1"):
        sync_assets.sync()
    assert tree_bytes(assets) == before
    assert list(assets.parent.iterdir()) == [assets]


def test_late_copy_failure_preserves_assets(
    asset_tree: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, assets = asset_tree
    before = tree_bytes(assets)
    copy = sync_assets.shutil.copy2
    calls = []

    def fail_late(src: Path, dst: Path) -> None:
        calls.append(src)
        if src == repo / "nested/last.txt":
            dst.write_bytes(b"partial")
            raise OSError("copy failed")
        copy(src, dst)

    monkeypatch.setattr(sync_assets.shutil, "copy2", fail_late)
    with pytest.raises(OSError, match="copy failed"):
        sync_assets.sync()
    assert calls == [repo / "first.txt", repo / "nested/last.txt"]
    assert tree_bytes(assets) == before
    assert list(assets.parent.iterdir()) == [assets]


@pytest.mark.parametrize("change_at", ["before copy", "during copy", "after copy"])
def test_changed_canonical_input_refuses_publication(
    asset_tree: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, change_at: str
) -> None:
    repo, assets = asset_tree
    before = tree_bytes(assets)
    first = repo / "first.txt"
    last = repo / "nested/last.txt"
    changed = last if change_at == "before copy" else first
    copy = sync_assets.shutil.copy2
    copied = []

    def replace_changed() -> None:
        # A new inode changes the recorded identity on every platform.
        replacement = changed.with_suffix(".new")
        replacement.write_bytes(b"x" * changed.stat().st_size)
        replacement.replace(changed)

    def copy_with_change(src: Path, dst: Path) -> None:
        if change_at == "before copy" and src == first:
            replace_changed()
        copy(src, dst)
        copied.append(src)
        if (change_at == "during copy" and src == first) or (
            change_at == "after copy" and src == last
        ):
            replace_changed()

    monkeypatch.setattr(sync_assets.shutil, "copy2", copy_with_change)
    relative_path = re.escape(changed.relative_to(repo).as_posix())
    with pytest.raises(RuntimeError, match=f"Canonical asset changed: {relative_path}"):
        sync_assets.sync()
    assert copied == ([first, last] if change_at == "after copy" else [first])
    assert tree_bytes(assets) == before
    assert list(assets.parent.iterdir()) == [assets]


@pytest.mark.parametrize("edited", ["first.txt", "nested/last.txt"])
def test_same_metadata_edit_refuses_publication(
    asset_tree: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, edited: str
) -> None:
    """A same-size edit within one timestamp tick keeps the metadata identity."""
    repo, assets = asset_tree
    before = tree_bytes(assets)
    target = repo / edited
    copy = sync_assets.shutil.copy2
    copied = []

    def copy_then_edit(src: Path, dst: Path) -> None:
        copy(src, dst)
        copied.append(src)
        if src == target:
            target.write_bytes(b"x" * target.stat().st_size)

    monkeypatch.setattr(sync_assets, "source_identity", lambda rel: (0,))
    monkeypatch.setattr(sync_assets.shutil, "copy2", copy_then_edit)
    with pytest.raises(RuntimeError, match=f"Canonical asset changed: {re.escape(edited)}"):
        sync_assets.sync()
    assert copied == [repo / "first.txt", repo / "nested/last.txt"]
    assert tree_bytes(assets) == before
    assert list(assets.parent.iterdir()) == [assets]


@pytest.mark.parametrize("failure", [OSError, KeyboardInterrupt])
def test_publication_failure_restores_assets(
    asset_tree: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, failure: type[BaseException]
) -> None:
    _, assets = asset_tree
    before = tree_bytes(assets)
    rename = Path.rename
    failed = []

    def fail_publish(src: Path, dst: Path) -> Path:
        if src.name == "staged":
            failed.append(src)
            raise failure("publish failed")
        return rename(src, dst)

    monkeypatch.setattr(Path, "rename", fail_publish)
    with pytest.raises(failure, match="publish failed"):
        sync_assets.sync()
    assert len(failed) == 1
    assert tree_bytes(assets) == before
    assert set(assets.parent.iterdir()) == {assets, assets.parent / ".assets-sync-lock"}


@pytest.mark.parametrize(
    "barrier",
    [
        "record",
        pytest.param(
            "package directory", marks=pytest.mark.skipif(os.name == "nt", reason="POSIX barrier")
        ),
    ],
)
def test_journal_barrier_failure_prevents_tree_renames(
    asset_tree: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, barrier: str
) -> None:
    _, assets = asset_tree
    before = tree_bytes(assets)
    marker = assets.parent / ASSET_MARKER
    fsync = os.fsync
    rename = Path.rename
    flushed = set()
    renamed = []

    def fail_journal_sync(fd: int) -> None:
        info = os.fstat(fd)
        flushed.add((info.st_dev, info.st_ino))
        record = next(assets.parent.glob(".assets-sync-*/pending"), marker)
        target = record if barrier == "record" else assets.parent
        if target.exists() and os.path.samestat(info, target.stat()):
            (staged,) = assets.parent.glob(".assets-sync-*/staged")
            for name in ("first.txt", "nested/last.txt", ".gitkeep"):
                payload = (staged / name).stat()
                assert (payload.st_dev, payload.st_ino) in flushed
            if barrier == "package directory":
                assert marker.is_file()
                for path in (marker, staged / "nested", staged, staged.parent):
                    entry = path.stat()
                    assert (entry.st_dev, entry.st_ino) in flushed
            raise OSError("journal flush failed")
        fsync(fd)

    def record_rename(src: Path, dst: Path) -> Path:
        renamed.append(src)
        return rename(src, dst)

    monkeypatch.setattr(os, "fsync", fail_journal_sync)
    monkeypatch.setattr(Path, "rename", record_rename)
    with pytest.raises(OSError, match="journal flush failed"):
        sync_assets.sync()
    assert renamed == []
    assert tree_bytes(assets) == before
    assert marker.exists() == (barrier == "package directory")


def test_success_replaces_stale_assets(asset_tree: tuple[Path, Path]) -> None:
    repo, assets = asset_tree
    sync_assets.sync()
    assert tree_bytes(assets) == {**tree_bytes(repo), ".gitkeep": b"placeholder"}
    assert set(assets.parent.iterdir()) == {assets, assets.parent / ".assets-sync-lock"}


def test_parallel_publications_preserve_placeholder(
    asset_tree: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, assets = asset_tree
    rename = Path.rename
    first_at_promotion = Event()
    second_started = Event()
    release_first = Event()
    publications = []

    def sync_second() -> None:
        second_started.set()
        sync_assets.sync()

    def pause_first(src: Path, dst: Path) -> Path:
        if src.name != "staged":
            return rename(src, dst)
        generation = (src / "first.txt").read_bytes()
        if generation == b"first.txt":
            first_at_promotion.set()
            assert release_first.wait(10)
        result = rename(src, dst)
        publications.append(generation)
        return result

    monkeypatch.setattr(Path, "rename", pause_first)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(sync_assets.sync)
        try:
            assert first_at_promotion.wait(10)
            assert not assets.exists()
            (repo / "first.txt").write_bytes(b"second first")
            (repo / "nested/last.txt").write_bytes(b"second last")
            second = pool.submit(sync_second)
            assert second_started.wait(10)
            with pytest.raises(TimeoutError):
                second.result(timeout=1)
        finally:
            release_first.set()
        first.result(timeout=10)
        second.result(timeout=10)

    assert publications == [b"first.txt", b"second first"]
    assert tree_bytes(assets) == {
        "first.txt": b"second first",
        "nested/last.txt": b"second last",
        ".gitkeep": b"placeholder",
    }


def test_first_sync_creates_assets(asset_tree: tuple[Path, Path]) -> None:
    repo, assets = asset_tree
    sync_assets.shutil.rmtree(assets)
    sync_assets.sync()
    assert tree_bytes(assets) == tree_bytes(repo)
    assert set(assets.parent.iterdir()) == {assets, assets.parent / ".assets-sync-lock"}


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_rollback_failure_retains_previous_tree(
    asset_tree: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
    cleanup_fails: bool,
) -> None:
    _, assets = asset_tree
    before = tree_bytes(assets)
    rename = Path.rename
    remove = sync_assets.shutil.rmtree
    calls = []
    publish_error = OSError("promotion failed")

    def fail_restore(src: Path, dst: Path) -> Path:
        calls.append(src.name)
        if src.name == "staged":
            raise publish_error
        if src.name == "previous":
            raise OSError("restore failed")
        return rename(src, dst)

    def fail_cleanup(path: Path, **kwargs) -> None:
        if path.name == "staged" and cleanup_fails:
            raise OSError("staging cleanup failed")
        remove(path, **kwargs)

    monkeypatch.setattr(Path, "rename", fail_restore)
    monkeypatch.setattr(sync_assets.shutil, "rmtree", fail_cleanup)
    with pytest.raises(OSError, match="promotion failed") as caught:
        sync_assets.sync()
    assert caught.value is publish_error
    assert calls == ["_assets", "staged", "previous"]
    (work,) = [path for path in assets.parent.iterdir() if path.is_dir()]
    assert tree_bytes(work / "previous") == before
    assert (work / "staged").exists() == cleanup_fails

    diagnostics = "".join(traceback.format_exception(caught.value))
    assert "restore failed" in diagnostics
    assert str(work / "previous") in diagnostics
    assert ("staging cleanup failed" in diagnostics) == cleanup_fails
    assert str(work / "previous") in capsys.readouterr().out


def test_cleanup_failure_does_not_replace_primary_error(
    asset_tree: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, assets = asset_tree
    before = tree_bytes(assets)

    def fail_copy(src: Path, dst: Path) -> None:
        raise OSError("copy failed")

    def fail_cleanup(path: Path) -> None:
        raise OSError("cleanup failed")

    monkeypatch.setattr(sync_assets.shutil, "copy2", fail_copy)
    monkeypatch.setattr(sync_assets.shutil, "rmtree", fail_cleanup)
    with pytest.raises(OSError, match="copy failed") as caught:
        sync_assets.sync()
    assert "cleanup failed" in "".join(traceback.format_exception(caught.value))
    assert tree_bytes(assets) == before


def test_old_tree_cleanup_failure_keeps_new_assets(
    asset_tree: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    repo, assets = asset_tree
    remove = sync_assets.shutil.rmtree

    def fail_cleanup(path: Path, **kwargs) -> None:
        if (path / "previous").is_dir():
            raise OSError("cleanup failed")
        remove(path, **kwargs)

    monkeypatch.setattr(sync_assets.shutil, "rmtree", fail_cleanup)
    with pytest.raises(OSError, match="cleanup failed"):
        sync_assets.sync()
    assert tree_bytes(assets) == {**tree_bytes(repo), ".gitkeep": b"placeholder"}
    assert "Old asset cleanup incomplete" in capsys.readouterr().out


def test_recovery_directories_are_excluded_from_built_packages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli_root = CLI_DIR
    project = tmp_path / "cli"
    project.mkdir()
    for name in (
        "pyproject.toml",
        "hatch_build.py",
        "asset_inventory.py",
        "asset_lock.py",
        "README.md",
    ):
        shutil.copy2(cli_root / name, project / name)
    shutil.copytree(
        cli_root / "src",
        project / "src",
        ignore=shutil.ignore_patterns("_assets", ".assets-sync-*", "__pycache__"),
    )
    package = project / "src" / "dds"
    for rel in CANONICAL_ASSETS:
        asset = package / "_assets" / rel
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_text("synthetic asset")
    stale = package / ".assets-sync-recovery" / "previous" / "stale.txt"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale")
    (package / ".assets-sync-lock").touch()

    dist = tmp_path / "dist"
    monkeypatch.chdir(project)
    sdist_name = build_sdist(str(dist))
    unpack = tmp_path / "unpacked"
    with tarfile.open(dist / sdist_name) as archive:
        assert any(name.endswith("/asset_inventory.py") for name in archive.getnames())
        if hasattr(tarfile, "data_filter"):
            archive.extractall(unpack, filter="data")
        else:
            # This synthetic archive was just built in this test.
            archive.extractall(unpack)
    (source,) = unpack.iterdir()
    monkeypatch.chdir(source)
    build_wheel(str(dist))

    (wheel,) = dist.glob("*.whl")
    (sdist,) = dist.glob("*.tar.gz")
    with zipfile.ZipFile(wheel) as archive:
        wheel_names = archive.namelist()
    with tarfile.open(sdist) as archive:
        sdist_names = archive.getnames()
    for names in (wheel_names, sdist_names):
        assert any(
            name.endswith("_assets/skills/wrap-existing-django-in-electron/SKILL.md")
            for name in names
        )
        assert not any(".assets-sync-" in name for name in names)
