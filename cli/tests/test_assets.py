"""Verify that all bundled assets exist in the canonical repo locations.

This catches drift: if a canonical file is renamed or removed, this test fails
before a broken wheel is published.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add cli/ to path so we can import the sync script's asset list
CLI_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CLI_DIR))

import sync_assets  # noqa: E402
from sync_assets import CANONICAL_ASSETS  # noqa: E402

REPO_ROOT = CLI_DIR.parent


@pytest.mark.parametrize("rel_path", CANONICAL_ASSETS)
def test_canonical_asset_exists(rel_path: str) -> None:
    full = REPO_ROOT / rel_path
    assert full.is_file(), f"canonical asset missing: {full}"


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
    assert list(assets.parent.iterdir()) == [assets]


def test_success_replaces_stale_assets(asset_tree: tuple[Path, Path]) -> None:
    repo, assets = asset_tree
    sync_assets.sync()
    assert tree_bytes(assets) == {**tree_bytes(repo), ".gitkeep": b"placeholder"}
    assert list(assets.parent.iterdir()) == [assets]


def test_first_sync_creates_assets(asset_tree: tuple[Path, Path]) -> None:
    repo, assets = asset_tree
    sync_assets.shutil.rmtree(assets)
    sync_assets.sync()
    assert tree_bytes(assets) == tree_bytes(repo)
    assert list(assets.parent.iterdir()) == [assets]


def test_rollback_failure_retains_previous_tree(
    asset_tree: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _, assets = asset_tree
    before = tree_bytes(assets)
    rename = Path.rename
    calls = []

    def fail_restore(src: Path, dst: Path) -> Path:
        calls.append(src.name)
        if src.name in {"staged", "previous"}:
            raise OSError("rename failed")
        return rename(src, dst)

    monkeypatch.setattr(Path, "rename", fail_restore)
    with pytest.raises(OSError, match="rename failed"):
        sync_assets.sync()
    assert calls == ["_assets", "staged", "previous"]
    (work,) = assets.parent.iterdir()
    assert tree_bytes(work / "previous") == before
    assert not (work / "staged").exists()
    assert str(work / "previous") in capsys.readouterr().out


def test_old_tree_cleanup_failure_keeps_new_assets(
    asset_tree: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    repo, assets = asset_tree
    remove = sync_assets.shutil.rmtree

    def fail_cleanup(path: Path, **kwargs) -> None:
        if path.name == "previous":
            raise OSError("cleanup failed")
        remove(path, **kwargs)

    monkeypatch.setattr(sync_assets.shutil, "rmtree", fail_cleanup)
    with pytest.raises(OSError, match="cleanup failed"):
        sync_assets.sync()
    assert tree_bytes(assets) == {**tree_bytes(repo), ".gitkeep": b"placeholder"}
    assert "Old asset cleanup incomplete" in capsys.readouterr().out
