"""Per-install Django secret key for the packaged desktop runtime.

Packaged builds must not share one hardcoded ``SECRET_KEY``: every install
would then sign sessions, CSRF tokens and password-reset links with a value
that is public in this repository. Instead, the packaged settings generate one
random key per app-data directory on first start and reuse it afterwards.
"""

from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

SECRET_KEY_FILENAME = "secret_key"
SECRET_KEY_FILE_MODE = 0o600


def load_or_create_secret_key(app_data_dir: Path) -> str:
    """Return the install's secret key, creating it once if it is missing.

    The key file lives in ``app_data_dir`` and is created owner-only (``0600``
    on POSIX; on Windows it relies on the per-user app-data ACLs). Creation is
    race-safe: the key is fully written to a private temp file first and then
    hard-linked into place, so a concurrent process either wins the link or
    reads the complete key written by the winner.
    """

    key_path = app_data_dir / SECRET_KEY_FILENAME
    existing_key = _read_secret_key(key_path)
    if existing_key is not None:
        return existing_key

    app_data_dir.mkdir(parents=True, exist_ok=True)
    temp_path = app_data_dir / f".{SECRET_KEY_FILENAME}.{secrets.token_hex(8)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    file_descriptor = os.open(temp_path, flags, SECRET_KEY_FILE_MODE)
    try:
        with os.fdopen(file_descriptor, "wb") as temp_file:
            temp_file.write(secrets.token_urlsafe(50).encode("ascii"))
            temp_file.flush()
            os.fsync(temp_file.fileno())
        try:
            os.link(temp_path, key_path)
        except FileExistsError:
            # Another process created the key first; use theirs.
            pass
    finally:
        temp_path.unlink(missing_ok=True)

    created_key = _read_secret_key(key_path)
    if created_key is None:
        raise ImproperlyConfigured(f"Could not create the packaged secret key at {key_path}.")
    return created_key


def _read_secret_key(key_path: Path) -> str | None:
    try:
        raw_key = key_path.read_bytes()
    except FileNotFoundError:
        return None

    _restrict_permissions(key_path)
    key = raw_key.decode("ascii").strip() if raw_key.isascii() else ""
    if not key:
        raise ImproperlyConfigured(
            f"The packaged secret key file {key_path} is empty or invalid. "
            "Delete it to generate a new key (this signs out existing sessions)."
        )
    return key


def _restrict_permissions(key_path: Path) -> None:
    if os.name == "nt":
        return
    current_mode = stat.S_IMODE(key_path.stat().st_mode)
    if current_mode & 0o077:
        os.chmod(key_path, SECRET_KEY_FILE_MODE)
