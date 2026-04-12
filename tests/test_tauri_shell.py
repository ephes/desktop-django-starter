import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_tauri_bundle_uses_shared_stage_and_icons() -> None:
    config = json.loads((ROOT / "shells" / "tauri" / "src-tauri" / "tauri.conf.json").read_text())
    csp = config["app"]["security"]["csp"]

    assert config["bundle"]["active"] is True
    assert config["bundle"]["resources"] == {"../../../.stage/backend": "backend"}
    assert config["bundle"]["windows"]["webviewInstallMode"]["type"] == "downloadBootstrapper"
    assert "icons/icon.icns" in config["bundle"]["icon"]
    assert "icons/icon.ico" in config["bundle"]["icon"]
    assert "default-src 'self'" in csp
    assert "connect-src ipc: http://ipc.localhost http://127.0.0.1:* http://localhost:*" in csp
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp


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
    assert '.stage", "backend' in launcher
    assert "stage-backend" in builder
    assert '"build"' in builder
    assert '--bundles", "nsis' in builder
    assert '--bundles", "appimage' in builder
    assert '--bundles", shouldSmokeTest ? "app" : "dmg"' in builder
    assert "bundle/nsis/" in builder
    assert "Windows bundle smoke testing is not automated" in builder
    assert "Windows NSIS validation checklist" in builder
    expected = "Confirm closing the app stops the bundled Django and db_worker processes cleanly."
    assert expected in builder
    assert 'tauri-build TARGET=""' in justfile
    assert "Flying Stable" in splash
    assert "Saddling up" in splash


def test_tauri_runtime_keeps_tasks_demo_subprocess_model() -> None:
    runtime = (ROOT / "shells" / "tauri" / "src-tauri" / "src" / "lib.rs").read_text()
    docs = (ROOT / "docs" / "shells" / "tauri.md").read_text()
    cargo_toml = (ROOT / "shells" / "tauri" / "src-tauri" / "Cargo.toml").read_text()

    assert "db_worker" in runtime
    assert "wait_for_django" in runtime
    assert 'getrandom = "0.3.4"' in cargo_toml
    assert "generate_desktop_auth_token" in runtime
    assert "getrandom::fill" in runtime
    assert "DESKTOP_DJANGO_AUTH_TOKEN" in runtime
    assert "X-Desktop-Django-Token" in runtime
    assert "build_bootstrap_url" in runtime
    assert "/desktop-auth/bootstrap/" in runtime
    assert "create_main_window(&app_handle, &bootstrap_url)" in runtime
    assert "SHUTDOWN_GRACE_PERIOD_MS" in runtime
    assert '["-TERM", &process.id().to_string()]' in runtime
    assert "supported" in docs
    assert ".github/workflows/tauri-packages.yml" in docs
    assert "artifact-only GitHub Actions workflow" in docs
    assert "build-only `tauri-action`" in docs
    assert "downloadBootstrapper" in docs
    assert "minimal `app.security.csp`" in docs
    assert "Current minimal CSP posture" in docs
    assert "canonical written checklist" in docs
    assert "not a release-parity path in this slice" in docs
    assert "installer install/run validation still needs a real live Windows machine" in docs
    assert "create_splash_window" in runtime
    assert "MINIMUM_SPLASH_DURATION_MS" in runtime
    assert "splash window immediately" in docs
    assert "SIGTERM" in docs
    assert "2-second grace period" in docs
