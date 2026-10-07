from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_electron_runtime_seeds_demo_content_only_for_new_packaged_database() -> None:
    runtime = (ROOT / "shells" / "electron" / "main.js").read_text()

    assert "getPackagedDatabasePath" in runtime
    assert 'path.join(app.getPath("userData"), "app.sqlite3")' in runtime
    assert 'runManageCommand(["seed_demo_content"]' in runtime
    assert "shouldSeedDemoContent" in runtime


def test_shells_do_not_inject_a_shared_packaged_secret_key() -> None:
    shell_sources = [
        ROOT / "shells" / "electron" / "main.js",
        ROOT / "shells" / "tauri" / "src-tauri" / "src" / "lib.rs",
        ROOT / "shells" / "positron" / "src" / "desktop_django_starter_positron" / "runtime.py",
    ]

    for source_path in shell_sources:
        source = source_path.read_text()
        assert "PACKAGED_RUNTIME_SECRET_KEY" not in source, source_path
        assert "packaged-runtime-secret" not in source, source_path
        assert "DJANGO_SECRET_KEY" not in source, source_path


def test_electron_guards_redirects_and_bridge_sender_origin() -> None:
    runtime = (ROOT / "shells" / "electron" / "main.js").read_text()

    assert 'win.webContents.on("will-redirect"' in runtime
    assert "getRedirectGuardAction(event, url)" in runtime
    assert "isTrustedIpcSender(event, currentAppUrl)" in runtime
