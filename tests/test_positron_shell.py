import asyncio
import importlib.util
import os
import socket
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

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
    assert "per-install `DJANGO_SECRET_KEY`" in shell_doc
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
    assert "seed_demo_content" in app
    # Seeding is decided from the versioned database path Django reports,
    # not a hard-coded <app-data>/app.sqlite3.
    assert 'settings.DATABASES["default"]["NAME"]' in app
    assert '"app.sqlite3"' not in app
    assert "app_version=positron_app_version(self.version)" in app
    assert "self.on_exit = self.confirm_exit" in app
    assert "async def confirm_exit" in app
    assert "background_task_counts" in app
    assert "toga.QuestionDialog" in app
    assert "self.request_exit()" in app
    assert "DESKTOP_DJANGO_APP_VERSION" in runtime
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


def test_positron_runtime_environment_drops_omitted_launch_values(tmp_path, monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(POSITRON_SRC))
    from desktop_django_starter_positron import runtime

    optional_values = {
        "DESKTOP_DJANGO_PORT": "9042",
        "DESKTOP_DJANGO_AUTH_TOKEN": "first-launch-token",
        "DESKTOP_DJANGO_APP_VERSION": "1.2.3",
    }
    monkeypatch.setattr(os, "environ", {})
    paths = {"app_data_dir": tmp_path / "data", "bundle_dir": tmp_path / "bundle"}
    first = runtime.django_environment(
        **paths, port=9042, auth_token="first-launch-token", app_version="1.2.3"
    )
    assert {key: first[key] for key in optional_values} == optional_values
    for key in optional_values:
        monkeypatch.setenv(key, first[key])
    monkeypatch.setenv("DESKTOP_DJANGO_SMOKE_TEST", "1")

    second = runtime.django_environment(**paths)

    assert optional_values.keys().isdisjoint(second)
    assert second["DESKTOP_DJANGO_SMOKE_TEST"] == "1"
    assert {key: os.environ[key] for key in optional_values} == optional_values


def test_positron_configure_django_removes_stale_process_values(
    tmp_path, monkeypatch, positron_app_module
) -> None:
    app_module = positron_app_module
    monkeypatch.setattr(app_module, "ensure_project_imports", Mock())
    monkeypatch.setattr(app_module, "positron_app_version", Mock(return_value=None))
    monkeypatch.setattr(os, "environ", {})
    os.environ.update(
        DESKTOP_DJANGO_PORT="9042",
        DESKTOP_DJANGO_AUTH_TOKEN="first-launch-token",
        DESKTOP_DJANGO_APP_VERSION="1.2.3",
        DESKTOP_DJANGO_SMOKE_TEST="1",
    )

    setup_calls = []

    def setup(*, set_prefix):
        setup_calls.append(set_prefix)
        assert "DESKTOP_DJANGO_PORT" not in os.environ
        assert "DESKTOP_DJANGO_APP_VERSION" not in os.environ
        assert os.environ["DESKTOP_DJANGO_AUTH_TOKEN"] == "current-launch-token"
        assert os.environ["DESKTOP_DJANGO_SMOKE_TEST"] == "1"

    monkeypatch.setattr(app_module.django, "setup", setup)
    app = app_module.DesktopDjangoStarterPositron()
    app.paths = SimpleNamespace(data=tmp_path / "data", cache=tmp_path / "cache")
    app.auth_token = "current-launch-token"
    app.version = None

    app.configure_django()

    assert setup_calls == [False]
    assert "DESKTOP_DJANGO_PORT" not in os.environ
    assert "DESKTOP_DJANGO_APP_VERSION" not in os.environ
    assert os.environ["DESKTOP_DJANGO_AUTH_TOKEN"] == "current-launch-token"
    assert os.environ["DESKTOP_DJANGO_SMOKE_TEST"] == "1"


def test_positron_runtime_helpers_resolve_repo_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)
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
        app_version="0.1.0",
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
    assert env["DESKTOP_DJANGO_APP_VERSION"] == "0.1.0"
    assert runtime.positron_app_version("9.9.9") == "9.9.9"
    # Falls back to the installed distribution, which the root test env lacks.
    assert runtime.positron_app_version(None) in {None, "0.1.0"}
    # Packaged settings generate a per-install key; the shell must not inject one.
    assert "DJANGO_SECRET_KEY" not in env
    assert not hasattr(runtime, "PACKAGED_RUNTIME_SECRET_KEY")


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


@pytest.mark.parametrize(
    "invalid_marker",
    [
        None,
        "example_app/__init__.py",
        "tasks_demo/__init__.py",
        "desktop_django_starter/settings/packaged.py",
    ],
)
def test_positron_runtime_validation_uses_shared_django_source(tmp_path, invalid_marker) -> None:
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
    bundled_src = module_file.parents[1] / "src"
    for source in (repo_src, bundled_src):
        for marker in (
            "desktop_django_starter/__init__.py",
            "desktop_django_starter/settings/__init__.py",
            "desktop_django_starter/settings/packaged.py",
            "example_app/__init__.py",
            "tasks_demo/__init__.py",
        ):
            path = source / marker
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()

    if invalid_marker:
        path = bundled_src / invalid_marker
        path.unlink()
        if invalid_marker == "tasks_demo/__init__.py":
            path.mkdir()

    expected = repo_src if invalid_marker else bundled_src
    assert runtime.resolve_django_source_root(module_file) == expected


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
    assert str(tmp_path / "src") in message
    assert str(module_file.parents[1] / "src") in message
    assert "desktop_django_starter/settings/packaged.py" in message


def test_positron_exit_confirmation_message() -> None:
    sys.path.insert(0, str(POSITRON_SRC))
    try:
        from desktop_django_starter_positron import runtime
    finally:
        sys.path.remove(str(POSITRON_SRC))

    assert runtime.exit_confirmation_message({"running_tasks": 0, "queued_tasks": 0}) is None
    message = runtime.exit_confirmation_message({"running_tasks": 1, "queued_tasks": 2})
    assert message is not None
    assert message.startswith(
        "Quitting now stops 1 running background task. "
        "2 queued tasks will start the next time the app runs."
    )


@pytest.fixture
def positron_app_module(monkeypatch):
    monkeypatch.syspath_prepend(str(POSITRON_SRC))
    monkeypatch.setitem(sys.modules, "toga", SimpleNamespace(App=object, QuestionDialog=Mock()))
    spec = importlib.util.spec_from_file_location(
        "desktop_django_starter_positron.app",
        POSITRON_SRC / "desktop_django_starter_positron" / "app.py",
    )
    app_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app_module)
    return app_module


@pytest.mark.parametrize("outcome", ["approve", "decline", "cancel"])
def test_positron_quit_owns_activity_probe_and_dialog(
    monkeypatch, outcome, positron_app_module
) -> None:
    monkeypatch.delenv("DESKTOP_DJANGO_SMOKE_TEST", raising=False)
    app_module = positron_app_module

    async def exercise_exit() -> None:
        probe_started = asyncio.Event()
        release_probe = asyncio.Event()
        counts = Mock(return_value={"running_tasks": 1, "queued_tasks": 0})

        async def probe(function):
            result = function()
            if not release_probe.is_set():
                if probe_started.is_set():
                    return {"running_tasks": 0, "queued_tasks": 0}
                probe_started.set()
                await release_probe.wait()
            return result

        monkeypatch.setattr(app_module.asyncio, "to_thread", probe)
        dialog_open = asyncio.Event()

        async def answer(_dialog):
            if outcome == "cancel":
                dialog_open.set()
                await asyncio.Future()
            return outcome == "approve"

        window = SimpleNamespace(dialog=AsyncMock(side_effect=answer))
        app = SimpleNamespace(
            _exit_in_progress=False,
            _django_ready=lambda: True,
            _background_task_counts=counts,
            main_window=window,
            cleanup=Mock(return_value=True),
        )
        confirm_exit = app_module.DesktopDjangoStarterPositron.confirm_exit
        first = asyncio.create_task(confirm_exit(app, None))
        try:
            await asyncio.wait_for(probe_started.wait(), timeout=2)
            assert await asyncio.wait_for(confirm_exit(app, None), timeout=2) is False
            counts.assert_called_once()
            window.dialog.assert_not_awaited()
            app.cleanup.assert_not_called()

            release_probe.set()
            if outcome == "cancel":
                await asyncio.wait_for(dialog_open.wait(), timeout=2)
                first.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await first
            else:
                assert await first is (outcome == "approve")

            window.dialog.assert_awaited_once()
            if outcome != "approve":
                app.cleanup.assert_not_called()
                window.dialog.side_effect = None
                window.dialog.return_value = True
                assert await confirm_exit(app, None) is True
            app.cleanup.assert_called_once()
        finally:
            if not first.done():
                first.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await first

    asyncio.run(exercise_exit())


@pytest.mark.parametrize("interruption", ["migrate", "seed_demo_content", "legacy"])
def test_positron_packaged_seed_survives_interrupted_first_launch(tmp_path, interruption) -> None:
    script = """
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.modules["toga"] = SimpleNamespace(App=object)
from desktop_django_starter_positron import app

data, cache, action = sys.argv[1:]
shell = app.DesktopDjangoStarterPositron()
shell.paths = SimpleNamespace(data=Path(data), cache=Path(cache))
shell.auth_token = "synthetic-test-token"
shell.version = "1.0.0"
shell.configure_django()

from example_app.models import Item

call_command = app.django_manage.call_command

class Interrupted(Exception):
    pass

def interrupted_command(name, **kwargs):
    if name == action == "seed_demo_content":
        raise Interrupted
    result = call_command(name, **kwargs)
    if name == action == "migrate":
        raise Interrupted
    return result

if action == "legacy":
    call_command("migrate", interactive=False, verbosity=0)
elif action in {"migrate", "seed_demo_content"}:
    with patch.object(app.django_manage, "call_command", interrupted_command):
        try:
            shell.prepare_runtime()
        except Interrupted:
            pass
        else:
            raise AssertionError("the first launch did not reach the interruption")
    assert Item.objects.count() == 0
else:
    shell.prepare_runtime()
    if action == "edit":
        assert Item.objects.count() == 3
        Item.objects.filter(title="Skylark Comet").update(title="Edited pony")
    elif action == "check":
        assert set(Item.objects.values_list("title", flat=True)) == {
            "Edited pony", "Marigold Drift", "Northwind Glimmer",
        }
        Item.objects.all().delete()
    else:
        assert Item.objects.count() == 0
"""
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join((str(POSITRON_SRC), str(ROOT / "src"))),
    }
    actions = (
        (interruption, "empty")
        if interruption == "legacy"
        else (interruption, "edit", "check", "empty")
    )
    for action in actions:
        result = subprocess.run(
            [sys.executable, "-c", script, str(tmp_path / "data"), str(tmp_path / "cache"), action],
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert result.returncode == 0, f"{action}: {result.stdout}\n{result.stderr}"


def test_positron_seed_claim_is_durable_before_migrate(
    positron_app_module, monkeypatch, tmp_path
) -> None:
    app_module = positron_app_module
    database_path = tmp_path / "app.sqlite3"
    marker = tmp_path / "app.demo-seed-pending"
    synced: list[str] = []
    real_fsync = os.fsync

    def recording_fsync(fd: int) -> None:
        synced.append("dir" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file")
        real_fsync(fd)

    monkeypatch.setattr(app_module.os, "fsync", recording_fsync)

    assert app_module.claim_pending_demo_seed(database_path) == marker
    assert marker.is_file() and marker.stat().st_size == 0
    assert synced[0] == "file"
    if os.name != "nt":
        assert synced[1:] == ["dir"]

    # A retry reuses the durable claim even though migrate created the database.
    database_path.touch()
    assert app_module.claim_pending_demo_seed(database_path) == marker

    # Without a claim, an existing database is already admitted.
    marker.unlink()
    assert app_module.claim_pending_demo_seed(database_path) is None
    assert not marker.exists()


@pytest.mark.parametrize("kind", ["nonempty", "directory", "symlink"])
def test_positron_seed_claim_rejects_invalid_marker(positron_app_module, tmp_path, kind) -> None:
    database_path = tmp_path / "app.sqlite3"
    marker = tmp_path / "app.demo-seed-pending"
    if kind == "nonempty":
        marker.write_text("x")
    elif kind == "directory":
        marker.mkdir()
    else:
        target = tmp_path / "target"
        target.touch()
        marker.symlink_to(target)

    with pytest.raises(RuntimeError, match="Invalid pending demo seed marker"):
        positron_app_module.claim_pending_demo_seed(database_path)


@pytest.fixture
def running_positron_shell(positron_app_module, monkeypatch, tmp_path):
    app_module = positron_app_module
    monkeypatch.setattr(app_module.toga, "WebView", Mock(), raising=False)
    window = Mock(dialog=AsyncMock())
    monkeypatch.setattr(app_module.toga, "MainWindow", Mock(return_value=window), raising=False)
    monkeypatch.setattr(app_module.toga, "ErrorDialog", Mock(), raising=False)
    app = app_module.DesktopDjangoStarterPositron()
    app.paths = SimpleNamespace(data=tmp_path)
    app.formal_name = "Synthetic Positron"
    app.configure_django = Mock()
    app.prepare_runtime = Mock()
    return app


def test_positron_closes_listener_when_handler_setup_fails(
    monkeypatch, positron_app_module, running_positron_shell
) -> None:
    app_module = positron_app_module
    app = running_positron_shell
    servers = []

    class BoundServer(app_module.ThreadedWSGIServer):
        def __init__(self, *args):
            super().__init__(*args)
            self.address = self.socket.getsockname()
            self.close_count = 0
            servers.append(self)

        def shutdown(self):
            pytest.fail("cleanup called shutdown before the serve loop started")

        def server_close(self):
            self.close_count += 1
            super().server_close()

    error = RuntimeError("synthetic handler setup failure")
    monkeypatch.setattr(app_module, "ThreadedWSGIServer", BoundServer)
    monkeypatch.setattr(app_module, "WSGIHandler", Mock(side_effect=error))

    async def exercise():
        app.loop = asyncio.get_running_loop()
        app.startup()
        try:
            with pytest.raises(RuntimeError, match="synthetic handler setup failure"):
                await asyncio.wait_for(app.server_ready, timeout=2)
            assert await asyncio.wait_for(asyncio.to_thread(app.cleanup), timeout=2)
            assert app._instance_lock is None
            (server,) = servers
            assert server.close_count == 1
            with socket.socket() as listener:
                listener.bind(server.address)
        finally:
            for server in servers:
                if server.socket.fileno() >= 0:
                    server.server_close()
            if app._instance_lock is not None:
                app_module.release_instance_lock(app._instance_lock)

    asyncio.run(exercise())


def test_positron_worker_start_failure_keeps_cleanup_available(
    monkeypatch, positron_app_module, running_positron_shell
) -> None:
    from django_tasks_db.management.commands import db_worker

    app_module = positron_app_module
    app = running_positron_shell
    app.exit = Mock()
    monkeypatch.setattr(app_module, "WSGIHandler", Mock())
    worker = Mock()
    monkeypatch.setattr(db_worker, "Worker", Mock(return_value=worker))
    worker_thread = Mock()
    worker_thread.start.side_effect = RuntimeError("synthetic worker start failure")
    worker_thread.join.side_effect = RuntimeError("cannot join an unstarted thread")

    async def exercise():
        app.loop = asyncio.get_running_loop()
        app.startup()
        try:
            port = await asyncio.wait_for(app.server_ready, timeout=2)
            monkeypatch.setattr(app_module, "Thread", Mock(return_value=worker_thread))
            try:
                await asyncio.wait_for(app.on_running(), timeout=2)
            except RuntimeError:
                app.cleanup()
                raise
            worker_thread.start.assert_called_once()
            worker_thread.join.assert_not_called()
            assert app._instance_lock is None
            assert not app.server_thread.is_alive()
            with socket.socket() as listener:
                listener.bind((app_module.HOST, port))
            app.main_window.dialog.assert_awaited_once()
            app.exit.assert_called_once()
        finally:
            # The real listener must also stop if a regression restores the
            # broken worker ownership and the test fails above.
            app._task_worker_thread = None
            app.cleanup()

    asyncio.run(exercise())


@pytest.mark.parametrize("outcome", ["raises", "returns", "before_ready", "shutdown"])
def test_positron_reports_unexpected_server_exit_on_ui_thread(
    monkeypatch, positron_app_module, running_positron_shell, outcome
) -> None:
    from threading import Event, get_ident

    app_module = positron_app_module
    app = running_positron_shell
    app.start_task_worker = Mock()
    app.exit = Mock()
    monkeypatch.setattr(app_module, "WSGIHandler", Mock())
    finish = Event()
    servers = []

    class RunningServer(app_module.ThreadedWSGIServer):
        def __init__(self, *args):
            super().__init__(*args)
            self.address = self.socket.getsockname()
            self.close_count = 0
            servers.append(self)

        def serve_forever(self):
            if outcome == "shutdown":
                super().serve_forever(poll_interval=0.01)
                return
            if outcome == "before_ready":
                return
            if not finish.wait(timeout=5):
                raise AssertionError("test did not trigger the serve loop exit")
            if outcome == "raises":
                raise RuntimeError("synthetic serve loop failure")

        def shutdown(self):
            assert outcome == "shutdown", "cleanup tried to shut down a finished serve loop"
            super().shutdown()

        def server_close(self):
            self.close_count += 1
            super().server_close()

    monkeypatch.setattr(app_module, "ThreadedWSGIServer", RunningServer)

    async def exercise():
        ui_thread = get_ident()
        app.loop = asyncio.get_running_loop()
        app.startup()
        dialog_shown = asyncio.Event()

        async def show_dialog(dialog):
            assert get_ident() == ui_thread
            assert dialog is app_module.toga.ErrorDialog.return_value
            dialog_shown.set()

        app.main_window.dialog.side_effect = show_dialog

        try:
            if outcome == "before_ready":
                # Let the server close before the UI can process its queued callback.
                app.server_thread.join(timeout=2)
                assert not app.server_thread.is_alive()
            await asyncio.wait_for(app.on_running(), timeout=2)
            if outcome == "before_ready":
                app.start_task_worker.assert_not_called()
                app_module.toga.ErrorDialog.assert_called_once_with(
                    "Startup failed",
                    "The local service could not start. Quit and relaunch the app.",
                )
            else:
                assert app.web_view.url == app.bootstrap_url(app.server_ready.result())

            if outcome == "shutdown":
                assert app.cleanup()
                await asyncio.sleep(0)
            elif outcome != "before_ready":
                finish.set()
                await asyncio.wait_for(dialog_shown.wait(), timeout=2)
                assert app.cleanup()

            assert app._instance_lock is None
            (server,) = servers
            assert server.close_count == 1
            with socket.socket() as listener:
                listener.bind(server.address)
            if outcome == "shutdown":
                app.main_window.dialog.assert_not_awaited()
                app.exit.assert_not_called()
            else:
                if outcome != "before_ready":
                    app_module.toga.ErrorDialog.assert_called_once_with(
                        "Local service stopped",
                        "The local service stopped. Quit and relaunch the app.",
                    )
                app.exit.assert_called_once()
        finally:
            finish.set()
            await asyncio.to_thread(app.server_thread.join, 2)
            if app._instance_lock is not None:
                app_module.release_instance_lock(app._instance_lock)

    asyncio.run(exercise())
