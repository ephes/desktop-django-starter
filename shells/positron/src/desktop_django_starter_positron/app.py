from __future__ import annotations

import asyncio
import os
import secrets
import socketserver
from threading import Thread
from typing import BinaryIO
from urllib.parse import urlencode
from wsgiref.simple_server import WSGIServer

import django
import toga
from django.core import management as django_manage
from django.core.handlers.wsgi import WSGIHandler
from django.core.servers.basehttp import WSGIRequestHandler

from .runtime import (
    HOST,
    WORKER_ID,
    acquire_instance_lock,
    django_environment,
    ensure_project_imports,
    release_instance_lock,
)

SMOKE_EXIT_DELAY_SECONDS = 0.75
AUTH_BOOTSTRAP_PATH = "/desktop-auth/bootstrap/"


class ThreadedWSGIServer(socketserver.ThreadingMixIn, WSGIServer):
    """WSGI server with one thread per request, matching the Positron shell model."""


class DesktopDjangoStarterPositron(toga.App):
    def startup(self) -> None:
        self._httpd: ThreadedWSGIServer | None = None
        self._instance_lock: BinaryIO | None = None
        self._task_worker = None
        self._task_worker_thread: Thread | None = None
        self._smoke_exit_scheduled = False
        self._startup_error_message: str | None = None
        self.auth_token = secrets.token_hex(32)
        self.server_ready: asyncio.Future[int] = asyncio.Future()

        self.web_view = toga.WebView(on_webview_load=self.on_webview_load)
        self.on_exit = self.cleanup
        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_window.content = self.web_view

        self._instance_lock = acquire_instance_lock(self.paths.data)
        if self._instance_lock is None:
            self._startup_error_message = (
                "Desktop Django Starter Positron is already running for this user data directory."
            )
            return

        self.server_thread = Thread(target=self.web_server, daemon=True)
        self.server_thread.start()

    async def on_running(self) -> None:
        if self._startup_error_message is not None:
            self.main_window.show()
            self.main_window.error_dialog(
                "Already running",
                self._startup_error_message,
                on_result=lambda *_args: self.exit(),
            )
            return

        port = await self.server_ready
        self.start_task_worker()
        self.web_view.url = self.bootstrap_url(port)
        self.main_window.show()

    def bootstrap_url(self, port: int) -> str:
        query = urlencode({"token": self.auth_token, "next": "/"})
        return f"http://{HOST}:{port}{AUTH_BOOTSTRAP_PATH}?{query}"

    def on_webview_load(self, _widget, **_kwargs) -> None:
        if os.environ.get("DESKTOP_DJANGO_SMOKE_TEST") != "1" or self._smoke_exit_scheduled:
            return

        self._smoke_exit_scheduled = True
        self.loop.call_later(SMOKE_EXIT_DELAY_SECONDS, self.finish_smoke_test)

    def finish_smoke_test(self) -> None:
        self.main_window.close()
        self.exit()

    def cleanup(self, _app, **_kwargs) -> bool:
        self.stop_task_worker()

        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()

        if hasattr(self, "server_thread") and self.server_thread.is_alive():
            self.server_thread.join(timeout=5)

        release_instance_lock(self._instance_lock)
        self._instance_lock = None

        return True

    def bundle_dir(self):
        bundle_dir = self.paths.cache / "bundle"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        return bundle_dir

    def runtime_environment(self, port: int | None = None) -> dict[str, str]:
        return django_environment(
            app_data_dir=self.paths.data,
            bundle_dir=self.bundle_dir(),
            port=port,
            auth_token=self.auth_token,
        )

    def configure_django(self) -> None:
        ensure_project_imports()
        os.environ.update(self.runtime_environment())
        django.setup(set_prefix=False)

    def prepare_runtime(self) -> None:
        django_manage.call_command("collectstatic", interactive=False, verbosity=0, clear=False)
        django_manage.call_command("migrate", interactive=False, verbosity=0)

    def web_server(self) -> None:
        try:
            self.configure_django()
            self.prepare_runtime()

            self._httpd = ThreadedWSGIServer((HOST, 0), WSGIRequestHandler)
            self._httpd.daemon_threads = True
            self._httpd.set_app(WSGIHandler())

            _host, port = self._httpd.socket.getsockname()
            self.loop.call_soon_threadsafe(self.server_ready.set_result, port)
            self._httpd.serve_forever()
        except Exception as error:  # pragma: no cover - surfaced during manual shell startup
            if not self.server_ready.done():
                self.loop.call_soon_threadsafe(self.server_ready.set_exception, error)

    def start_task_worker(self) -> None:
        if self._task_worker_thread is not None and self._task_worker_thread.is_alive():
            return

        from django_tasks import DEFAULT_TASK_BACKEND_ALIAS
        from django_tasks_db.management.commands.db_worker import Worker

        self._task_worker = Worker(
            queue_names=["default"],
            interval=1.0,
            batch=False,
            backend_name=DEFAULT_TASK_BACKEND_ALIAS,
            startup_delay=True,
            max_tasks=None,
            worker_id=WORKER_ID,
        )
        self._task_worker_thread = Thread(target=self._task_worker.run, daemon=True)
        self._task_worker_thread.start()

    def stop_task_worker(self) -> None:
        if self._task_worker is None:
            return

        self._task_worker.running = False
        if self._task_worker_thread is not None:
            self._task_worker_thread.join(timeout=5)
        self._task_worker = None
        self._task_worker_thread = None


def main() -> DesktopDjangoStarterPositron:
    return DesktopDjangoStarterPositron(
        "desktop_django_starter_positron",
        "io.github.desktopdjangostarter.positron",
    )
