from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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


def test_electron_asks_before_quitting_with_running_tasks() -> None:
    runtime = (ROOT / "shells" / "electron" / "main.js").read_text()

    assert 'new URL("/desktop/activity/", url)' in runtime
    assert "quitGuard.needsCheck()" in runtime
    assert 'message: "A background task is still running"' in runtime
