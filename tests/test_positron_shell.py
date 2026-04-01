import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POSITRON_SRC = ROOT / "shells" / "positron" / "src"


def test_positron_shell_files_exist() -> None:
    expected = [
        ROOT / "shells" / "positron" / "pyproject.toml",
        ROOT / "shells" / "positron" / "resources" / ".gitkeep",
        ROOT / "shells" / "positron" / "scripts" / "generate-icons.py",
        ROOT / "shells" / "positron" / "src" / "desktop_django_starter_positron" / "app.py",
        ROOT / "shells" / "positron" / "src" / "desktop_django_starter_positron" / "__main__.py",
        ROOT / "shells" / "positron" / "src" / "desktop_django_starter_positron" / "runtime.py",
        ROOT / "shells" / "positron" / "src" / "desktop_django_starter_positron" / "management.py",
    ]

    for path in expected:
        assert path.exists(), f"Missing expected Positron shell file: {path}"


def test_positron_docs_and_commands_state_scope_honestly() -> None:
    readme = (ROOT / "README.md").read_text()
    release = (ROOT / "docs" / "release.md").read_text()
    shell_doc = (ROOT / "docs" / "shells" / "positron.md").read_text()
    justfile = (ROOT / "justfile").read_text()

    assert "just positron-install" in readme
    assert "just positron-start" in readme
    assert "just positron-smoke" in readme
    assert "just positron-package-dmg" in readme
    assert "GitHub Actions artifact generation remains out of scope" in shell_doc
    assert "Windows packaged-build parity is not claimed" in shell_doc
    assert "ad-hoc signing" in shell_doc
    assert "no dedicated Positron GitHub packaging workflow" in release
    assert "just positron-package-dmg" in release
    assert "positron-start" in justfile
    assert "positron-smoke" in justfile
    assert "positron-build" in justfile
    assert "positron-package-dmg" in justfile


def test_positron_runtime_reuses_shared_django_and_brand_assets() -> None:
    package_dir = ROOT / "shells" / "positron" / "src" / "desktop_django_starter_positron"
    app = (package_dir / "app.py").read_text()
    runtime = (package_dir / "runtime.py").read_text()
    pyproject = (ROOT / "shells" / "positron" / "pyproject.toml").read_text()
    icon_script = (ROOT / "shells" / "positron" / "scripts" / "generate-icons.py").read_text()

    assert "collectstatic" in app
    assert "Worker(" in app
    assert "desktop_django_starter.settings.packaged" in runtime
    assert "shared_brand_icon" in runtime
    assert "../../src" in pyproject
    assert "resources/app-icon" in pyproject
    assert "flying-stable-app-icon.svg" in icon_script
    assert "rsvg-convert" in icon_script


def test_positron_runtime_helpers_resolve_repo_paths(tmp_path) -> None:
    sys.path.insert(0, str(POSITRON_SRC))
    try:
        from desktop_django_starter_positron import runtime
    finally:
        sys.path.remove(str(POSITRON_SRC))

    module_file = POSITRON_SRC / "desktop_django_starter_positron" / "runtime.py"
    app_root = runtime.bundled_app_root(module_file)
    bundled_src = runtime.bundled_django_src(module_file)
    repo_root = runtime.development_repo_root(module_file)
    repo_src = runtime.development_repo_src(module_file)
    brand_icon = runtime.shared_brand_icon(module_file)
    env = runtime.django_environment(
        app_data_dir=tmp_path / "data",
        bundle_dir=tmp_path / "bundle",
        port=9042,
    )

    assert app_root == POSITRON_SRC
    assert bundled_src == POSITRON_SRC / "src"
    assert repo_root == ROOT
    assert repo_src == ROOT / "src"
    assert brand_icon == ROOT / "assets" / "brand" / "flying-stable-app-icon.svg"
    assert env["DJANGO_SETTINGS_MODULE"] == "desktop_django_starter.settings.packaged"
    assert env["DESKTOP_DJANGO_APP_DATA_DIR"] == str(tmp_path / "data")
    assert env["DESKTOP_DJANGO_BUNDLE_DIR"] == str(tmp_path / "bundle")
    assert env["DESKTOP_DJANGO_PORT"] == "9042"
