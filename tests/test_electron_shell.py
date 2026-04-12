from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_electron_runtime_seeds_demo_content_only_for_new_packaged_database() -> None:
    runtime = (ROOT / "shells" / "electron" / "main.js").read_text()

    assert "getPackagedDatabasePath" in runtime
    assert 'path.join(app.getPath("userData"), "app.sqlite3")' in runtime
    assert 'runManageCommand(["seed_demo_content"]' in runtime
    assert "shouldSeedDemoContent" in runtime
