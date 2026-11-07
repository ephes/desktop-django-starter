"""Execute Positron's real lifecycle without loading a native widget backend."""

import asyncio
import importlib
import sys
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

POSITRON_SRC = Path(__file__).resolve().parents[1] / "shells" / "positron" / "src"


@pytest.fixture
def shell(monkeypatch, tmp_path):
    class WebView:
        def __init__(self, **kwargs):
            self.url = None

    class Window:
        def __init__(self, **kwargs):
            self.errors = []
            self.shown = 0

        def show(self):
            self.shown += 1

        def error_dialog(self, title, message, **kwargs):
            self.errors.append((title, message))

    monkeypatch.setitem(
        sys.modules,
        "toga",
        SimpleNamespace(
            App=object,
            WebView=WebView,
            MainWindow=Window,
            QuestionDialog=lambda *args: args,
        ),
    )
    monkeypatch.syspath_prepend(str(POSITRON_SRC))
    module_name = "desktop_django_starter_positron.app"
    monkeypatch.delitem(sys.modules, module_name, raising=False)
    module = importlib.import_module(module_name)
    monkeypatch.setattr(module, "ensure_project_imports", lambda: None)
    monkeypatch.setattr(module.django, "setup", lambda **kwargs: None)
    monkeypatch.setattr(module.os, "environ", dict(module.os.environ))
    monkeypatch.setattr(
        module,
        "settings",
        SimpleNamespace(DATABASES={"default": {"NAME": str(tmp_path / "app.sqlite3")}}),
    )
    monkeypatch.setenv("DESKTOP_DJANGO_RUNTIME_MODE", "packaged")
    monkeypatch.delenv("DESKTOP_DJANGO_SMOKE_TEST", raising=False)
    calls = []
    command_options = {}

    def command(name, **kwargs):
        calls.append(name)
        command_options[name] = kwargs

    monkeypatch.setattr(module.django_manage, "call_command", command)
    monkeypatch.setattr(module.secrets, "token_hex", lambda size: "synthetic-startup-key")
    releases = []
    real_release = module.release_instance_lock

    def release(handle):
        if handle is not None:
            releases.append(handle)
        real_release(handle)

    monkeypatch.setattr(module, "release_instance_lock", release)
    instance = module.DesktopDjangoStarterPositron()
    instance.paths = SimpleNamespace(data=tmp_path / "data", cache=tmp_path / "cache")
    instance.formal_name = "Synthetic shell"
    instance.version = "1.2.3"
    stopped = Event()
    closed = []

    class Server:
        def __init__(self, *args):
            self.socket = SimpleNamespace(getsockname=lambda: ("127.0.0.1", 4567))

        def set_app(self, app):
            pass

        def serve_forever(self):
            if not stopped.wait(5):
                raise TimeoutError("synthetic server was not stopped")

        def shutdown(self):
            stopped.set()

        def server_close(self):
            closed.append(self)

    monkeypatch.setattr(module, "ThreadedWSGIServer", Server)
    monkeypatch.setattr(module, "WSGIHandler", lambda: object())
    yield SimpleNamespace(
        app=instance,
        module=module,
        calls=calls,
        releases=releases,
        closed=closed,
        Server=Server,
        command_options=command_options,
    )
    stopped.set()
    if hasattr(instance, "server_thread"):
        instance.server_thread.join(timeout=3)
        assert not instance.server_thread.is_alive()
    if getattr(instance, "_instance_lock", None) is not None:
        real_release(instance._instance_lock)
    sys.modules.pop(module_name, None)


@pytest.mark.parametrize("failure", ["migrate", "bind", "readiness"])
def test_startup_failure_is_displayed_and_releases_owned_resources(shell, monkeypatch, failure):
    def command(name, **kwargs):
        shell.calls.append(name)
        if name == "migrate" and failure == "migrate":
            raise RuntimeError("synthetic migrate failure")

    class Server(shell.Server):
        def __init__(self, *args):
            if failure == "bind":
                raise RuntimeError("synthetic bind failure")
            super().__init__(*args)

        def set_app(self, app):
            if failure == "readiness":
                raise RuntimeError("synthetic readiness failure")

        def shutdown(self):
            pytest.fail("must not shutdown a server that never entered serve_forever")

    monkeypatch.setattr(shell.module.django_manage, "call_command", command)
    monkeypatch.setattr(shell.module, "ThreadedWSGIServer", Server)
    worker_starts = []
    monkeypatch.setattr(shell.app, "start_task_worker", lambda: worker_starts.append(True))

    async def run():
        shell.app.loop = asyncio.get_running_loop()
        shell.app.startup()
        await asyncio.wait_for(shell.app.on_running(), timeout=3)
        assert worker_starts == []
        assert shell.app.web_view.url is None
        assert shell.app.main_window.errors == [("Startup failed", f"synthetic {failure} failure")]
        assert shell.app._instance_lock is None
        assert len(shell.releases) == 1
        assert len(shell.closed) == (1 if failure == "readiness" else 0)
        assert shell.calls[:2] == ["collectstatic", "migrate"]

    asyncio.run(run())


def test_healthy_startup_opens_bootstrap_after_readiness(shell, monkeypatch):
    worker_starts = []
    monkeypatch.setattr(shell.app, "start_task_worker", lambda: worker_starts.append(True))

    async def run():
        shell.app.loop = asyncio.get_running_loop()
        shell.app.startup()
        await asyncio.wait_for(shell.app.on_running(), timeout=3)
        assert shell.calls == ["collectstatic", "migrate", "seed_demo_content"]
        assert worker_starts == [True]
        assert shell.app.web_view.url == (
            "http://127.0.0.1:4567/desktop-auth/bootstrap/?token=synthetic-startup-key&next=%2F"
        )
        assert shell.command_options["collectstatic"]["clear"] is False
        assert shell.app.main_window.shown == 1
        assert shell.app.main_window.errors == []
        assert shell.app.cleanup()
        assert len(shell.releases) == 1
        assert len(shell.closed) == 1

    asyncio.run(run())
