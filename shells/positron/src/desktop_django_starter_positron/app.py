from __future__ import annotations

import asyncio
import os
import secrets
import socketserver
from pathlib import Path
from threading import Thread
from typing import BinaryIO
from urllib.parse import urlencode
from wsgiref.simple_server import WSGIServer

import django
import toga
from django.conf import settings
from django.core import management as django_manage
from django.core.handlers.wsgi import WSGIHandler
from django.core.servers.basehttp import WSGIRequestHandler

from .runtime import (
    HOST,
    WORKER_ID,
    acquire_instance_lock,
    django_environment,
    ensure_project_imports,
    exit_confirmation_message,
    positron_app_version,
    positron_runtime_mode,
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
        self._exit_prompt_open = False
        self.auth_token = secrets.token_hex(32)
        self.server_ready: asyncio.Future[int] = asyncio.Future()

        self.web_view = toga.WebView(on_webview_load=self.on_webview_load)
        self.on_exit = self.confirm_exit
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
        # request_exit() runs on_exit, which skips the prompt in smoke mode
        # and then cleans up.
        self.request_exit()

    async def confirm_exit(self, _app, **_kwargs) -> bool:
        """on_exit handler: ask before quitting while background tasks run.

        Toga runs an async on_exit as a task and exits only if it returns True.
        Idle, smoke mode, or a failed count all quit normally.
        """
        if self._exit_prompt_open:
            return False

        message = None
        if os.environ.get("DESKTOP_DJANGO_SMOKE_TEST") != "1" and self._django_ready():
            try:
                counts = await asyncio.to_thread(self._background_task_counts)
            except Exception as error:  # never trap the user in the app
                print(f"Could not read background task activity: {error}")
            else:
                message = exit_confirmation_message(counts)

        if message is not None:
            self._exit_prompt_open = True
            try:
                should_quit = await self.main_window.dialog(
                    toga.QuestionDialog("A background task is still running", message)
                )
            finally:
                self._exit_prompt_open = False
            if not should_quit:
                return False

        return self.cleanup()

    def _django_ready(self) -> bool:
        return (
            self.server_ready.done()
            and not self.server_ready.cancelled()
            and self.server_ready.exception() is None
        )

    @staticmethod
    def _background_task_counts() -> dict[str, int]:
        from django.db import connections

        from desktop_django_starter.activity import background_task_counts

        try:
            return background_task_counts()
        finally:
            connections.close_all()

    def cleanup(self, *_args, **_kwargs) -> bool:
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
            app_version=positron_app_version(self.version),
        )

    def configure_django(self) -> None:
        ensure_project_imports()
        os.environ.update(self.runtime_environment())
        django.setup(set_prefix=False)

    def prepare_runtime(self) -> None:
        # Packaged settings put the database in this version's state directory
        # (<app-data>/state/<version>/app.sqlite3); ask Django rather than
        # rebuilding the path. Seeding is idempotent, so seeding a database an
        # upgrade copied forward is harmless.
        database_path = Path(settings.DATABASES["default"]["NAME"])
        should_seed_demo_content = (
            positron_runtime_mode() == "packaged" and not database_path.exists()
        )
        django_manage.call_command("collectstatic", interactive=False, verbosity=0, clear=False)
        django_manage.call_command("migrate", interactive=False, verbosity=0)
        if should_seed_demo_content:
            django_manage.call_command("seed_demo_content", verbosity=0)

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

        from django.tasks import DEFAULT_TASK_BACKEND_ALIAS
        from django_tasks_db.management.commands.db_worker import Worker

        self._task_worker = Worker(
            queue_names=["default"],
            interval=1.0,
            batch=False,
            backend_name=DEFAULT_TASK_BACKEND_ALIAS,
            startup_delay=True,
            max_tasks=None,
            worker_id=WORKER_ID,
            excluded_queue_names=[],
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
