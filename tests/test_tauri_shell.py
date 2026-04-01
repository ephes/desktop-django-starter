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
    justfile = (ROOT / "justfile").read_text()
    splash = (ROOT / "shells" / "tauri" / "src" / "splash.html").read_text()

    assert "stage-backend" in package["scripts"]
    assert "start" in package["scripts"]
    assert "start:packaged" in package["scripts"]
    assert "build:dmg" in package["scripts"]
    assert "../../assets/brand/flying-stable-app-icon.svg" in package["scripts"]["icons"]
    assert ".stage\", \"backend" in launcher
    assert "stage-backend" in builder
    assert "\"build\"" in builder
    assert "--bundles\", \"nsis" in builder
    assert "--bundles\", \"appimage" in builder
    assert "--bundles\", shouldSmokeTest ? \"app\" : \"dmg\"" in builder
    assert "bundle/nsis/" in builder
    assert "Windows bundle smoke testing is not automated" in builder
    assert 'tauri-build TARGET=""' in justfile
    assert "Flying Stable" in splash
    assert "Saddling up" in splash


def test_tauri_runtime_keeps_tasks_demo_subprocess_model() -> None:
    runtime = (ROOT / "shells" / "tauri" / "src-tauri" / "src" / "lib.rs").read_text()
    docs = (ROOT / "docs" / "shells" / "tauri.md").read_text()

    assert "db_worker" in runtime
    assert "wait_for_django" in runtime
    assert "supported" in docs
    assert "GitHub Actions artifact generation remains Electron-only" in docs
    assert "preparing a local NSIS installer path" in docs
    assert "installer install/run validation still needs a real live Windows machine" in docs
    assert "create_splash_window" in runtime
    assert "MINIMUM_SPLASH_DURATION_MS" in runtime
    assert "splash window immediately" in docs
