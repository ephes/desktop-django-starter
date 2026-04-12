#!/usr/bin/env node

const fs = require("node:fs");
const path = require("node:path");

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(1);
}

function normalizeRelative(filePath) {
  return filePath.split(path.sep).join("/");
}

function readMetadata(targetRoot) {
  const metadataPath = path.join(targetRoot, "electron", "wrap-target.json");
  if (!fs.existsSync(metadataPath)) {
    fail(`wrap-target metadata not found: ${metadataPath}`);
  }

  return JSON.parse(fs.readFileSync(metadataPath, "utf8"));
}

function readRequired(filePath) {
  if (!fs.existsSync(filePath)) {
    fail(`required target file not found: ${filePath}`);
  }

  return fs.readFileSync(filePath, "utf8");
}

function writeIfChanged(filePath, source) {
  const existing = fs.existsSync(filePath) ? fs.readFileSync(filePath, "utf8") : null;
  if (existing === source) {
    return;
  }

  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, source);
}

function insertAfter(source, anchor, addition, marker, filePath) {
  if (source.includes(marker)) {
    return source;
  }

  if (!source.includes(anchor)) {
    fail(`expected scaffold text not found in ${filePath}: ${anchor}`);
  }

  return source.replace(anchor, `${anchor}${addition}`);
}

function insertAfterRegex(source, pattern, addition, marker, filePath) {
  if (source.includes(marker)) {
    return source;
  }

  const match = source.match(pattern);
  if (!match || typeof match.index !== "number") {
    fail(`expected scaffold pattern not found in ${filePath}: ${pattern}`);
  }

  const anchor = match[0];
  const insertAt = match.index + anchor.length;
  return `${source.slice(0, insertAt)}${addition}${source.slice(insertAt)}`;
}

function insertBeforeRegex(source, pattern, addition, marker, filePath) {
  if (source.includes(marker)) {
    return source;
  }

  const match = source.match(pattern);
  if (!match || typeof match.index !== "number") {
    fail(`expected scaffold pattern not found in ${filePath}: ${pattern}`);
  }

  return `${source.slice(0, match.index)}${addition}${source.slice(match.index)}`;
}

function replaceRequired(source, searchValue, replaceValue, filePath) {
  if (!source.includes(searchValue)) {
    fail(`expected scaffold text not found in ${filePath}: ${searchValue}`);
  }

  return source.replace(searchValue, replaceValue);
}

function appendBlockIfMissing(source, block, marker) {
  if (source.includes(marker)) {
    return source;
  }

  const trimmed = source.replace(/\s*$/, "");
  return `${trimmed}\n\n${block}`;
}

function resolveSettingsPatchPath(targetRoot, metadata) {
  const candidatePaths = [
    metadata.django.developmentSettingsPath,
    metadata.django.settingsBasePath
  ].filter(Boolean);

  for (const relativePath of candidatePaths) {
    const absolutePath = path.join(targetRoot, relativePath);
    if (!fs.existsSync(absolutePath)) {
      continue;
    }

    const source = fs.readFileSync(absolutePath, "utf8");
    if (
      /['"]django\.middleware\.security\.SecurityMiddleware['"]/.test(source)
      && /['"]django\.contrib\.auth\.middleware\.AuthenticationMiddleware['"]/.test(source)
    ) {
      return relativePath;
    }
  }

  return metadata.django.developmentSettingsPath;
}

function toPythonPathExpression(baseName, relativePath) {
  if (!relativePath) {
    fail(`missing required packaged path for ${baseName}`);
  }

  const parts = normalizeRelative(relativePath).split("/").filter(Boolean);
  return parts.reduce((expression, part) => `${expression} / ${JSON.stringify(part)}`, baseName);
}

function toOptionalPythonPathExpression(baseName, relativePath) {
  if (!relativePath) {
    return "None";
  }

  return toPythonPathExpression(baseName, relativePath);
}

function updateSettings(targetRoot, metadata) {
  const relativeSettingsPath = resolveSettingsPatchPath(targetRoot, metadata);
  const settingsPath = path.join(targetRoot, relativeSettingsPath);
  let source = readRequired(settingsPath);
  const desktopModule = `${metadata.django.packageModule}.desktop_middleware`;

  if (!source.includes("import os\n") && !source.includes("import os\r\n")) {
    source = insertAfterRegex(
      source,
      /^(?:from .+\n|import .+\n)+/m,
      "import os\n",
      "import os\n",
      settingsPath
    );
  }
  source = insertAfterRegex(
    source,
    /^\s*['"]django\.middleware\.security\.SecurityMiddleware['"],\r?\n/m,
    `    "${desktopModule}.DesktopAuthTokenMiddleware",\n`,
    `${desktopModule}.DesktopAuthTokenMiddleware`,
    settingsPath
  );
  source = insertAfter(
    source,
    `    "${desktopModule}.DesktopAuthTokenMiddleware",\n`,
    `    "${desktopModule}.DesktopRuntimeMiddleware",\n`,
    `${desktopModule}.DesktopRuntimeMiddleware`,
    settingsPath
  );
  source = insertAfterRegex(
    source,
    /^\s*['"]django\.contrib\.auth\.middleware\.AuthenticationMiddleware['"],\r?\n/m,
    `    "${desktopModule}.DesktopAutoLoginMiddleware",\n`,
    `${desktopModule}.DesktopAutoLoginMiddleware`,
    settingsPath
  );
  source = appendBlockIfMissing(
    source,
    'DESKTOP_ALLOWED_HOSTS = ["localhost", "127.0.0.1", "::1", "testserver"]\n'
      + '_desktop_existing_allowed_hosts = globals().get("ALLOWED_HOSTS", [])\n'
      + 'if isinstance(_desktop_existing_allowed_hosts, str):\n'
      + '    _desktop_existing_allowed_hosts = [_desktop_existing_allowed_hosts]\n'
      + 'ALLOWED_HOSTS = list(dict.fromkeys([*_desktop_existing_allowed_hosts, *DESKTOP_ALLOWED_HOSTS]))\n'
      + 'DESKTOP_DJANGO_AUTH_TOKEN = os.environ.get("DESKTOP_DJANGO_AUTH_TOKEN", "")\n'
      + 'DESKTOP_AUTO_LOGIN_ENABLED = os.environ.get("DESKTOP_AUTO_LOGIN_ENABLED") == "1"\n'
      + 'DESKTOP_AUTO_LOGIN_USERNAME = os.environ.get("DESKTOP_AUTO_LOGIN_USERNAME", "")\n'
      + "DESKTOP_PACKAGED_RUNTIME = False\n",
    "DESKTOP_ALLOWED_HOSTS"
  );

  writeIfChanged(settingsPath, source);
}

function updateUrls(targetRoot, metadata) {
  const urlsPath = path.join(targetRoot, metadata.django.urlsPath);
  let source = readRequired(urlsPath);

  if (!source.includes("JsonResponse")) {
    if (source.includes("from django.http import")) {
      source = source.replace(
        /^from django\.http import ([^\n]+)$/m,
        (_match, names) => {
          const nameSet = new Set(names.split(",").map((name) => name.trim()).filter(Boolean));
          for (const name of ["Http404", "HttpRequest", "HttpResponse", "JsonResponse"]) {
            nameSet.add(name);
          }
          return `from django.http import ${Array.from(nameSet).join(", ")}`;
        }
      );
    } else {
      source = insertBeforeRegex(
        source,
        /^urlpatterns\s*=\s*\[/m,
        "from django.http import Http404, HttpRequest, HttpResponse, JsonResponse\n",
        "from django.http import Http404, HttpRequest, HttpResponse, JsonResponse",
        urlsPath
      );
    }
  }

  if (!source.includes("re_path")) {
    if (source.includes("from django.urls import")) {
      source = source.replace(
        /^from django\.urls import ([^\n]+)$/m,
        (_match, names) => {
          const nameSet = new Set(names.split(",").map((name) => name.trim()).filter(Boolean));
          nameSet.add("re_path");
          return `from django.urls import ${Array.from(nameSet).join(", ")}`;
        }
      );
    } else {
      source = insertBeforeRegex(
        source,
        /^urlpatterns\s*=\s*\[/m,
        "from django.urls import re_path\n",
        "from django.urls import re_path",
        urlsPath
      );
    }
  }

  if (!source.includes("static_serve")) {
    source = insertBeforeRegex(
      source,
      /^urlpatterns\s*=\s*\[/m,
      "from django.views.static import serve as static_serve\n",
      "from django.views.static import serve as static_serve",
      urlsPath
    );
  }

  source = insertBeforeRegex(
    source,
    /^urlpatterns\s*=\s*\[/m,
    "def health_view(_request: HttpRequest) -> JsonResponse:\n"
      + '    return JsonResponse({"status": "ok"})\n'
      + "\n"
      + "def packaged_static_view(request: HttpRequest, path: str) -> HttpResponse:\n"
      + "    if not settings.DESKTOP_PACKAGED_RUNTIME:\n"
      + '        raise Http404("Static files are served by Django only in packaged mode.")\n'
      + "    return static_serve(request, path, document_root=settings.STATIC_ROOT)\n"
      + "\n"
      + "def packaged_media_view(request: HttpRequest, path: str) -> HttpResponse:\n"
      + "    if not settings.DESKTOP_PACKAGED_RUNTIME:\n"
      + '        raise Http404("Media files are served by Django only in packaged mode.")\n'
      + "    return static_serve(request, path, document_root=settings.MEDIA_ROOT)\n"
      + "\n",
    "def health_view(",
    urlsPath
  );

  source = insertAfterRegex(
    source,
    /^urlpatterns\s*=\s*\[\n/m,
    '    path("health/", health_view),\n',
    'path("health/", health_view)',
    urlsPath
  );

  source = appendBlockIfMissing(
    source,
    "if settings.DESKTOP_PACKAGED_RUNTIME:\n"
      + "    urlpatterns += [\n"
      + '        re_path(r"^static/(?P<path>.*)$", packaged_static_view),\n'
      + '        re_path(r"^media/(?P<path>.*)$", packaged_media_view),\n'
      + "    ]\n",
    "if settings.DESKTOP_PACKAGED_RUNTIME:"
  );

  writeIfChanged(urlsPath, source);
}

function buildDesktopMiddlewareSource() {
  return `from __future__ import annotations

import secrets
from collections.abc import Callable

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.db import OperationalError, ProgrammingError
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden

from .desktop_runtime import ensure_runtime_database

DESKTOP_AUTH_HEADER = "X-Desktop-Django-Token"


class DesktopAuthTokenMiddleware:
    """Require the desktop shell token when configured."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        expected_token = getattr(settings, "DESKTOP_DJANGO_AUTH_TOKEN", "")
        if not expected_token:
            return self.get_response(request)

        request_token = request.headers.get(DESKTOP_AUTH_HEADER, "")
        if secrets.compare_digest(request_token, expected_token):
            return self.get_response(request)

        return HttpResponseForbidden("Forbidden")


class DesktopRuntimeMiddleware:
    """Initialize the runtime database on the first real desktop app request."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        desktop_runtime_enabled = (
            getattr(settings, "DESKTOP_PACKAGED_RUNTIME", False)
            or bool(getattr(settings, "DESKTOP_DJANGO_AUTH_TOKEN", ""))
            or getattr(settings, "DESKTOP_AUTO_LOGIN_ENABLED", False)
        )
        if desktop_runtime_enabled and request.path not in {"/health/", "/favicon.ico"}:
            ensure_runtime_database()
        return self.get_response(request)


class DesktopAutoLoginMiddleware:
    """Log the configured desktop user in for shell requests."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def _resolve_desktop_user(self):
        username = getattr(settings, "DESKTOP_AUTO_LOGIN_USERNAME", "")

        user_model = get_user_model()
        if username:
            return user_model.objects.filter(username=username).first()

        users = list(user_model.objects.order_by("pk")[:2])
        if len(users) == 1:
            return users[0]

        return None

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.user.is_authenticated or not settings.DESKTOP_AUTO_LOGIN_ENABLED:
            return self.get_response(request)

        try:
            user = self._resolve_desktop_user()
        except (OperationalError, ProgrammingError):
            return self.get_response(request)

        if user is not None:
            login(request, user)

        return self.get_response(request)
`;
}

function buildDesktopRuntimeSource() {
  return `from __future__ import annotations

import shutil
import threading
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.db import connections

_runtime_database_lock = threading.Lock()
_runtime_database_ready = False


def _runtime_database_path() -> Path | None:
    default_database = settings.DATABASES.get("default", {})
    database_name = default_database.get("NAME")
    if not database_name:
        return None
    return Path(database_name)


def _runtime_database_uses_sqlite() -> bool:
    default_database = settings.DATABASES.get("default", {})
    return "sqlite" in default_database.get("ENGINE", "")


def _runtime_database_has_schema() -> bool:
    database_path = _runtime_database_path()
    if database_path is None or not database_path.exists():
        return False

    connection = connections["default"]
    with connection.cursor() as cursor:
        table_names = connection.introspection.table_names(cursor)
    return "django_migrations" in table_names


def ensure_runtime_database() -> None:
    """Apply migrations for empty desktop runtime databases on first app access."""

    global _runtime_database_ready

    if _runtime_database_ready or not _runtime_database_uses_sqlite():
        return

    if _runtime_database_has_schema():
        _runtime_database_ready = True
        return

    with _runtime_database_lock:
        if _runtime_database_ready:
            return

        database_path = _runtime_database_path()
        if database_path is not None:
            database_path.parent.mkdir(parents=True, exist_ok=True)

        connections.close_all()
        call_command("migrate", interactive=False, run_syncdb=True, verbosity=0)
        connections.close_all()
        _runtime_database_ready = True


def bootstrap_packaged_runtime(
    app_data_dir: Path,
    seed_database_path: Path | None,
    seed_media_path: Path | None,
) -> tuple[Path, Path]:
    """Populate runtime data from the staged backend bundle when missing."""

    app_data_dir.mkdir(parents=True, exist_ok=True)

    database_path = app_data_dir / "app.sqlite3"
    media_root = app_data_dir / "media"

    if not database_path.exists():
        database_path.parent.mkdir(parents=True, exist_ok=True)
        if seed_database_path and seed_database_path.exists():
            shutil.copy2(seed_database_path, database_path)

    media_root.mkdir(parents=True, exist_ok=True)
    if seed_media_path and seed_media_path.exists():
        shutil.copytree(seed_media_path, media_root, dirs_exist_ok=True)

    return database_path, media_root
`;
}

function buildPackagedSettingsSource(metadata) {
  const seedDatabasePath = toOptionalPythonPathExpression("bundle_dir", metadata.django.seedDatabasePath);
  const seedMediaPath = toOptionalPythonPathExpression("bundle_dir", metadata.django.seedMediaPath);
  const usesSettingsPackage = Boolean(metadata.django.settingsContainerModule);
  const baseSettingsImport = usesSettingsPackage
    ? `from .settings import base as base_settings\nfrom .settings.base import *  # noqa: F403`
    : `from . import settings as base_settings\nfrom .settings import *  # noqa: F403`;

  return `"""Settings for the packaged desktop runtime."""

from __future__ import annotations

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

${baseSettingsImport}
from .desktop_runtime import bootstrap_packaged_runtime

DEBUG = False
DESKTOP_PACKAGED_RUNTIME = True
# Keep development-only tooling out of the packaged desktop runtime.
PACKAGED_EXCLUDED_APPS = {"django_extensions"}
INSTALLED_APPS = [
    app for app in base_settings.INSTALLED_APPS if app not in PACKAGED_EXCLUDED_APPS
]

bundle_dir = Path(os.environ.get("DESKTOP_DJANGO_BUNDLE_DIR", BASE_DIR))  # noqa: F405
app_data_dir = Path(
    os.environ.get("DESKTOP_DJANGO_APP_DATA_DIR", BASE_DIR / ".desktop-data")  # noqa: F405
)

secret_key = os.environ.get("DJANGO_SECRET_KEY")
if not secret_key:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set for packaged settings.")

SECRET_KEY = secret_key
seed_database_path = ${seedDatabasePath}
seed_media_path = ${seedMediaPath}
database_path, media_root = bootstrap_packaged_runtime(
    app_data_dir=app_data_dir,
    seed_database_path=seed_database_path,
    seed_media_path=seed_media_path,
)

DATABASES = {
    **base_settings.DATABASES,
    "default": {
        **base_settings.DATABASES["default"],
        "NAME": database_path,
    },
}
MEDIA_ROOT = str(media_root)
STATIC_ROOT = bundle_dir / "staticfiles"  # noqa: F405
`;
}

function updateManagePy(targetRoot, metadata) {
  const managePyPath = path.join(targetRoot, metadata.django.developmentManagePath);
  let source = readRequired(managePyPath);
  const uncommentedSource = source
    .split("\n")
    .filter((line) => !line.trimStart().startsWith("#"))
    .join("\n");

  if (uncommentedSource.includes('os.environ.setdefault("DJANGO_SETTINGS_MODULE"')) {
    return;
  }

  source = source.replace(
    /os\.environ\[\s*["']DJANGO_SETTINGS_MODULE["']\s*\]\s*=\s*(["'][^"']+["'])/,
    'os.environ.setdefault("DJANGO_SETTINGS_MODULE", $1)'
  );

  writeIfChanged(managePyPath, source);
}

function buildJustAppendix() {
  return `

# Wrapped desktop shell shortcuts
# Install the wrapped Electron shell dependencies in this target repo.
desktop-install:
    npm --prefix electron install

# Start the wrapped Electron shell in development mode.
desktop-start:
    npm --prefix electron run start

# Rebuild the staged packaged backend bundle for the wrapped shell.
desktop-stage:
    npm --prefix electron run stage-backend

# Start the wrapped Electron shell against the packaged backend contract.
desktop-packaged-start:
    npm --prefix electron run start:packaged

# Run the packaged Electron smoke launch and exit after the first page load.
desktop-smoke:
    npm --prefix electron run smoke:packaged
`;
}

function updateJustfile(targetRoot) {
  const justfilePath = path.join(targetRoot, "justfile");
  if (!fs.existsSync(justfilePath)) {
    return;
  }

  let source = fs.readFileSync(justfilePath, "utf8");
  if (source.includes("desktop-install:")) {
    return;
  }

  source = `${source.replace(/\s*$/, "")}${buildJustAppendix()}`;
  writeIfChanged(justfilePath, `${source}\n`);
}

function updateDjangoResumeHeadwindNavigation(targetRoot) {
  const detailPath = path.join(
    targetRoot,
    "src",
    "django_resume",
    "templates",
    "django_resume",
    "pages",
    "headwind",
    "resume_detail.html"
  );
  const cvPath = path.join(
    targetRoot,
    "src",
    "django_resume",
    "templates",
    "django_resume",
    "pages",
    "headwind",
    "resume_cv.html"
  );

  if (fs.existsSync(detailPath)) {
    let source = readRequired(detailPath);
    source = insertAfter(
      source,
      '      <div class="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">\n',
      '        <p>\n'
        + '          <a href="{% url \'django_resume:list\' %}" class="text-blue-600 hover:underline">← Back to all resumes</a>\n'
        + "        </p>\n",
      "Back to all resumes",
      detailPath
    );
    writeIfChanged(detailPath, source);
  }

  if (fs.existsSync(cvPath)) {
    let source = readRequired(cvPath);
    source = insertAfter(
      source,
      '    <div class="max-w-5xl mx-auto px-6 py-8 print:px-0 print:py-4">\n',
      '      <p class="mb-6 print:hidden">\n'
        + '        <a href="{% url \'django_resume:list\' %}" class="text-blue-600 hover:underline">← Back to all resumes</a>\n'
        + "      </p>\n",
      "Back to all resumes",
      cvPath
    );
    writeIfChanged(cvPath, source);
  }
}

function writeDesktopFiles(targetRoot, metadata) {
  writeIfChanged(
    path.join(targetRoot, metadata.django.desktopMiddlewarePath),
    buildDesktopMiddlewareSource()
  );
  writeIfChanged(
    path.join(targetRoot, metadata.django.desktopRuntimePath),
    buildDesktopRuntimeSource()
  );
  writeIfChanged(
    path.join(targetRoot, metadata.django.packagedSettingsPath),
    buildPackagedSettingsSource(metadata)
  );
}

function main() {
  const targetRootArg = process.argv[2];
  if (!targetRootArg) {
    fail("usage: prepare-django-desktop-scaffold.cjs TARGET_REPO");
  }

  const targetRoot = path.resolve(targetRootArg);
  const metadata = readMetadata(targetRoot);

  updateSettings(targetRoot, metadata);
  updateUrls(targetRoot, metadata);
  updateManagePy(targetRoot, metadata);
  writeDesktopFiles(targetRoot, metadata);
  updateJustfile(targetRoot);
  updateDjangoResumeHeadwindNavigation(targetRoot);

  process.stdout.write(`Prepared Django desktop scaffold for ${targetRoot}\n`);
}

main();
