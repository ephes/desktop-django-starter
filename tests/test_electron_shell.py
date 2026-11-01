from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_electron_runtime_seeds_demo_content_only_for_new_packaged_database() -> None:
    runtime = (ROOT / "shells" / "electron" / "main.js").read_text()

    assert "getPackagedDatabasePath" in runtime
    assert '"state", getStateDirName(app.getVersion()), "app.sqlite3"' in runtime
    assert "DESKTOP_DJANGO_APP_VERSION: app.getVersion()" in runtime
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


def test_electron_starts_backend_processes_through_the_process_guard() -> None:
    runtime = (ROOT / "shells" / "electron" / "main.js").read_text()

    assert '"desktop_process_guard.py"' in runtime
    assert '"--watch-stdin"' in runtime
    assert 'stdio: ["pipe", "pipe", "pipe"]' in runtime
    assert "stopOrphanedBackendProcesses(session.app_key)" in runtime
    assert "endSession(app.getPath(\"userData\"), shellSession)" in runtime
    # A second instance must never reach bootstrap (and the orphan cleanup).
    assert "if (!gotSingleInstanceLock) {\n      return;\n    }" in runtime


def test_electron_asks_before_quitting_with_running_tasks() -> None:
    runtime = (ROOT / "shells" / "electron" / "main.js").read_text()

    assert 'new URL("/desktop/activity/", url)' in runtime
    assert "quitGuard.needsCheck()" in runtime
    assert 'message: "A background task is still running"' in runtime
