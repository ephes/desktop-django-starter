"""Execute Positron's real lifecycle without loading a native widget backend."""

import asyncio
import importlib
import sys
from pathlib import Path
from threading import Event, get_ident
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
            self._title = kwargs.get("title")
            self.on_title_change = lambda: None

        @property
        def title(self):
            return self._title

        @title.setter
        def title(self, value):
            self._title = value
            self.on_title_change()

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
        assert shell.app.on_exit == shell.app.confirm_exit
        assert shell.app.main_window.shown == 1
        assert shell.app.main_window.errors == []
        assert shell.app.cleanup()
        assert len(shell.releases) == 1
        assert len(shell.closed) == 1

    asyncio.run(run())


async def start_without_worker(shell, monkeypatch):
    monkeypatch.setattr(shell.app, "start_task_worker", lambda: None)
    shell.app.loop = asyncio.get_running_loop()
    shell.app.startup()
    await asyncio.wait_for(shell.app.on_running(), timeout=3)


def test_exit_check_is_single_flight_and_cancel_allows_retry(shell, monkeypatch):
    entered = Event()
    release = Event()
    reads = []
    cleanups = []
    cleanup = shell.app.cleanup

    def counts():
        reads.append(True)
        entered.set()
        assert release.wait(3)
        return {"running_tasks": 1, "queued_tasks": 0}

    def clean():
        cleanups.append(True)
        return cleanup()

    monkeypatch.setattr(shell.app, "_background_task_counts", counts)
    monkeypatch.setattr(shell.app, "cleanup", clean)

    async def run():
        await start_without_worker(shell, monkeypatch)
        decisions = iter([False, True])
        dialogs = []

        async def dialog(message):
            dialogs.append(message)
            return next(decisions)

        shell.app.main_window.dialog = dialog
        first = asyncio.create_task(shell.app.confirm_exit(None))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            second = await asyncio.wait_for(shell.app.confirm_exit(None), timeout=1)
            assert second is False
            assert reads == [True]
            assert dialogs == []
        finally:
            release.set()
        assert await first is False
        assert dialogs == [
            (
                "A background task is still running",
                "Quitting waits for 1 running background task to finish.\n\nQuit anyway?",
            )
        ]
        assert cleanups == []
        assert shell.app._exit_prompt_open is False
        assert await shell.app.confirm_exit(None) is True
        assert len(dialogs) == 2
        assert cleanups == [True]

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["cancel", "dialog", "counts"])
def test_exit_claim_is_released_after_cancellation_and_errors(shell, monkeypatch, failure):
    entered = Event()
    release = Event()

    def counts():
        entered.set()
        assert release.wait(3)
        if failure == "counts":
            raise RuntimeError("synthetic count failure")
        return {"running_tasks": 1, "queued_tasks": 0}

    monkeypatch.setattr(shell.app, "_background_task_counts", counts)

    async def run():
        await start_without_worker(shell, monkeypatch)

        async def dialog(message):
            if failure == "dialog":
                raise RuntimeError("synthetic dialog failure")
            return True

        shell.app.main_window.dialog = dialog
        pending = asyncio.create_task(shell.app.confirm_exit(None))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            if failure == "cancel":
                pending.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await pending
            else:
                release.set()
                if failure == "dialog":
                    with pytest.raises(RuntimeError, match="dialog failure"):
                        await pending
                else:
                    assert await pending is True
        finally:
            release.set()
        assert shell.app._exit_prompt_open is False
        monkeypatch.setattr(shell.app, "_background_task_counts", lambda: {})
        assert await shell.app.confirm_exit(None) is True
        assert len(shell.releases) == 1

    asyncio.run(run())


def test_smoke_exit_skips_activity_and_dialog(shell, monkeypatch):
    async def run():
        await start_without_worker(shell, monkeypatch)
        monkeypatch.setenv("DESKTOP_DJANGO_SMOKE_TEST", "1")
        monkeypatch.setattr(shell.app, "_background_task_counts", lambda: pytest.fail("count read"))
        assert await shell.app.confirm_exit(None) is True
        assert shell.app._exit_prompt_open is False
        assert len(shell.releases) == 1

    asyncio.run(run())


def test_worker_ownership_survives_bounded_join_until_task_finishes(shell, monkeypatch):
    from django_tasks_db.management.commands import db_worker

    entered = Event()
    release = Event()
    workers = []
    worker_errors = []

    class Worker:
        def __init__(self, **kwargs):
            self.running = True
            workers.append(self)

        def run(self):
            entered.set()
            if not release.wait(3):
                worker_errors.append("worker was not released")

    monkeypatch.setattr(db_worker, "Worker", Worker)

    async def run():
        # Use real start_task_worker, including the real owned thread.
        shell.app.loop = asyncio.get_running_loop()
        shell.app.startup()
        try:
            await asyncio.wait_for(shell.app.on_running(), timeout=3)
            assert await asyncio.to_thread(entered.wait, 2)
            worker = shell.app._task_worker
            thread = shell.app._task_worker_thread
            real_join = thread.join
            # Keep a real live worker, shortening only the public bounded join.
            monkeypatch.setattr(thread, "join", lambda timeout=None: real_join(timeout=0.01))
            assert shell.app.cleanup() is False
            assert worker.running is False
            assert thread.is_alive()
            assert shell.app._task_worker is worker
            assert shell.app._task_worker_thread is thread
            assert shell.app._instance_lock is not None
            assert shell.releases == []
            assert shell.closed == []
            shell.app.start_task_worker()
            assert workers == [worker]
        finally:
            release.set()
        real_join(timeout=2)
        assert not thread.is_alive()
        assert worker_errors == []
        assert shell.app.cleanup() is True
        assert shell.app._task_worker is None
        assert shell.app._task_worker_thread is None
        assert shell.app._instance_lock is None
        assert len(shell.releases) == 1
        assert len(shell.closed) == 1
        assert shell.app.cleanup() is True
        assert len(shell.releases) == 1
        assert len(shell.closed) == 1

    asyncio.run(run())


@pytest.mark.parametrize("smoke", [False, True])
def test_confirmed_exit_waits_responsively_for_worker_and_finishes(shell, monkeypatch, smoke):
    from django_tasks_db.management.commands import db_worker

    entered = Event()
    release = Event()
    worker_errors = []

    class Worker:
        def __init__(self, **kwargs):
            self.running = True

        def run(self):
            entered.set()
            if not release.wait(3):
                worker_errors.append("worker was not released")

    monkeypatch.setattr(db_worker, "Worker", Worker)
    monkeypatch.setattr(shell.app, "_background_task_counts", lambda: {"running_tasks": 1})
    if smoke:
        monkeypatch.setenv("DESKTOP_DJANGO_SMOKE_TEST", "1")

    async def run():
        shell.app.loop = asyncio.get_running_loop()
        shell.app.startup()
        await asyncio.wait_for(shell.app.on_running(), 2)
        assert await asyncio.to_thread(entered.wait, 2)
        thread = shell.app._task_worker_thread
        real_join = thread.join
        join_threads = []
        main_thread = get_ident()

        def short_join(timeout=None):
            join_threads.append(get_ident())
            real_join(timeout=0.01)

        monkeypatch.setattr(thread, "join", short_join)
        noticed = asyncio.Event()
        shell.app.main_window.on_title_change = noticed.set
        dialogs = []

        async def dialog(message):
            dialogs.append(message)
            return True

        shell.app.main_window.dialog = dialog
        pending = asyncio.create_task(shell.app.on_exit(None))
        try:
            await asyncio.wait_for(noticed.wait(), 2)
            assert not pending.done()
            assert shell.app._instance_lock is not None
            assert shell.app._task_worker_thread is thread
            assert shell.releases == []
            assert shell.closed == []
            assert shell.app.main_window.title == "Synthetic shell — Finishing background work"
            assert join_threads and main_thread not in join_threads
            assert len(dialogs) == (0 if smoke else 1)
            assert await shell.app.on_exit(None) is False
        finally:
            release.set()
        assert await asyncio.wait_for(pending, 2) is True
        real_join(timeout=2)
        assert worker_errors == []
        assert shell.app._task_worker_thread is None
        assert len(shell.releases) == 1
        assert len(shell.closed) == 1

    asyncio.run(run())


def test_real_activity_reader_returns_counts_and_closes_connections(shell, monkeypatch):
    from django.db import connections

    from desktop_django_starter import activity

    counts = {"running_tasks": 1, "queued_tasks": 2}
    closes = []
    monkeypatch.setattr(activity, "background_task_counts", lambda: counts)
    monkeypatch.setattr(connections, "close_all", lambda: closes.append(True))
    assert shell.app._background_task_counts() == counts
    assert closes == [True]
