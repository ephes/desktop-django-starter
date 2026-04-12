import subprocess
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
    assert "manual-only for now" in shell_doc
    expected = (
        "there is no connected updater, hosted artifact lane, checksum lane, "
        "or GitHub release-publication flow"
    )
    assert expected in shell_doc
    assert "Briefcase development refresh flows" in shell_doc
    assert "fallback `DJANGO_SECRET_KEY` value as Electron and Tauri" in shell_doc
    assert "not a release-parity path in this slice" in shell_doc
    assert "no dedicated Positron GitHub packaging workflow" in release
    assert "just positron-package-dmg" in release
    assert "Positron updates are manual-only for now" in release
    assert "local manual replacement only" in release
    assert "not a release-parity path in this slice" in release
    assert "manual-only for now" in readme
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
    assert "clear=False" in app
    assert "acquire_instance_lock" in app
    assert "Worker(" in app
    assert "secrets.token_hex(32)" in app
    assert "bootstrap_url" in app
    assert "/desktop-auth/bootstrap/" in app
    assert "DESKTOP_DJANGO_RUNTIME_MODE" in runtime
    assert "DESKTOP_DJANGO_AUTH_TOKEN" in runtime
    assert "POSITRON_RUNTIME_MODE" in runtime
    assert "POSITRON_DJANGO_SETTINGS_MODULE" in runtime
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
    lock_file = runtime.acquire_instance_lock(tmp_path / "data")
    env = runtime.django_environment(
        app_data_dir=tmp_path / "data",
        bundle_dir=tmp_path / "bundle",
        port=9042,
        auth_token="positron-test-token",
    )

    assert lock_file is not None
    runtime.release_instance_lock(lock_file)
    assert app_root == POSITRON_SRC
    assert bundled_src == POSITRON_SRC / "src"
    assert repo_root == ROOT
    assert repo_src == ROOT / "src"
    assert brand_icon == ROOT / "assets" / "brand" / "flying-stable-app-icon.svg"
    assert runtime.positron_runtime_mode() == "packaged"
    assert runtime.positron_settings_module() == "desktop_django_starter.settings.packaged"
    assert runtime.instance_lock_path(tmp_path / "data") == (
        tmp_path / "data" / "desktop-django-starter-positron.lock"
    )
    assert env["DESKTOP_DJANGO_RUNTIME_MODE"] == "packaged"
    assert env["DJANGO_SETTINGS_MODULE"] == "desktop_django_starter.settings.packaged"
    assert env["DESKTOP_DJANGO_APP_DATA_DIR"] == str(tmp_path / "data")
    assert env["DESKTOP_DJANGO_BUNDLE_DIR"] == str(tmp_path / "bundle")
    assert env["DESKTOP_DJANGO_PORT"] == "9042"
    assert env["DESKTOP_DJANGO_AUTH_TOKEN"] == "positron-test-token"
    assert env["DJANGO_SECRET_KEY"] == "desktop-django-starter-packaged-runtime-secret"


def test_positron_instance_lock_blocks_a_second_process(tmp_path) -> None:
    lock_dir = tmp_path / "data"
    lock_code = """
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from desktop_django_starter_positron import runtime

lock_file = runtime.acquire_instance_lock(Path(sys.argv[2]))
print("locked" if lock_file is not None else "busy")
if lock_file is not None:
    input()
    runtime.release_instance_lock(lock_file)
"""

    holder = subprocess.Popen(
        [sys.executable, "-c", lock_code, str(POSITRON_SRC), str(lock_dir)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "locked"

        contender = subprocess.run(
            [sys.executable, "-c", lock_code, str(POSITRON_SRC), str(lock_dir)],
            input="\n",
            capture_output=True,
            text=True,
            check=True,
        )
        assert contender.stdout.strip() == "busy"
    finally:
        assert holder.stdin is not None
        holder.stdin.write("\n")
        holder.stdin.flush()
        holder.wait(timeout=5)


def test_positron_runtime_validation_uses_shared_django_source(tmp_path) -> None:
    sys.path.insert(0, str(POSITRON_SRC))
    try:
        from desktop_django_starter_positron import runtime
    finally:
        sys.path.remove(str(POSITRON_SRC))

    module_file = (
        tmp_path / "shells" / "positron" / "src" / "desktop_django_starter_positron" / "runtime.py"
    )
    module_file.parent.mkdir(parents=True)
    module_file.write_text("", encoding="utf-8")

    repo_src = tmp_path / "src"
    for package in ("desktop_django_starter", "example_app", "tasks_demo"):
        (repo_src / package).mkdir(parents=True)

    assert runtime.resolve_django_source_root(module_file) == repo_src


def test_positron_runtime_validation_raises_clear_error_when_src_missing(tmp_path) -> None:
    sys.path.insert(0, str(POSITRON_SRC))
    try:
        from desktop_django_starter_positron import runtime
    finally:
        sys.path.remove(str(POSITRON_SRC))

    module_file = (
        tmp_path / "shells" / "positron" / "src" / "desktop_django_starter_positron" / "runtime.py"
    )
    module_file.parent.mkdir(parents=True)
    module_file.write_text("", encoding="utf-8")

    try:
        runtime.resolve_django_source_root(module_file)
    except RuntimeError as error:
        message = str(error)
    else:  # pragma: no cover - defensive failure path
        raise AssertionError("Expected a clear runtime validation error.")

    assert "Could not locate the shared Django source tree" in message
    assert "desktop_django_starter" in message
