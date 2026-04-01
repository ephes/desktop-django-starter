import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_tauri_bundle_uses_shared_stage_and_icons() -> None:
    config = json.loads((ROOT / "shells" / "tauri" / "src-tauri" / "tauri.conf.json").read_text())

    assert config["bundle"]["active"] is True
    assert config["bundle"]["resources"] == {"../../../.stage/backend": "backend"}
    assert "icons/icon.icns" in config["bundle"]["icon"]
    assert "icons/icon.ico" in config["bundle"]["icon"]


def test_tauri_package_scripts_cover_local_runtime_flows() -> None:
    package = json.loads((ROOT / "shells" / "tauri" / "package.json").read_text())
    launcher = (ROOT / "shells" / "tauri" / "scripts" / "launch-tauri.mjs").read_text()
    builder = (ROOT / "shells" / "tauri" / "scripts" / "build-tauri.mjs").read_text()

    assert "stage-backend" in package["scripts"]
    assert "start" in package["scripts"]
    assert "start:packaged" in package["scripts"]
    assert "build:dmg" in package["scripts"]
    assert "../../assets/brand/flying-stable-app-icon.svg" in package["scripts"]["icons"]
    assert ".stage\", \"backend" in launcher
    assert "stage-backend" in builder
    assert "\"build\"" in builder


def test_tauri_runtime_keeps_tasks_demo_subprocess_model() -> None:
    runtime = (ROOT / "shells" / "tauri" / "src-tauri" / "src" / "lib.rs").read_text()
    docs = (ROOT / "docs" / "shells" / "tauri.md").read_text()

    assert "db_worker" in runtime
    assert "wait_for_django" in runtime
    assert "supported" in docs
    assert "GitHub Actions artifact generation remains Electron-only" in docs
