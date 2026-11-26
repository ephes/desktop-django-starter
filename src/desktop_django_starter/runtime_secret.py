"""Per-install Django secret key for the packaged desktop runtime.

Packaged builds must not share one hardcoded ``SECRET_KEY``: every install
would then sign sessions, CSRF tokens and password-reset links with a value
that is public in this repository. Instead, the packaged settings generate one
random key per app-data directory on first start and reuse it afterwards.
"""

from __future__ import annotations

import logging
import os
import secrets
import stat
import sys
from contextlib import suppress
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .state_files import _open_key_windows, sync_directory

logger = logging.getLogger(__name__)

SECRET_KEY_FILENAME = "secret_key"
SECRET_KEY_FILE_MODE = 0o600
SECRET_KEY_MAX_BYTES = 4096


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
        # The creator might still be syncing the link, or its sync might have failed.
        sync_directory(app_data_dir)
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
        sync_directory(app_data_dir)
    except BaseException as publication_error:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError as cleanup_error:
            publication_error.add_note(f"Could not remove temporary secret key: {cleanup_error}")
        raise

    try:
        temp_path.unlink(missing_ok=True)
    except OSError:
        # The durable key is already installed. Reporting cleanup is best effort.
        with suppress(Exception):
            logger.warning("Could not remove temporary secret key at %s", temp_path, exc_info=True)

    created_key = _read_secret_key(key_path)
    if created_key is None:
        raise ImproperlyConfigured(f"Could not create the packaged secret key at {key_path}.")
    return created_key


def _read_secret_key(key_path: Path) -> str | None:
    descriptor = None
    try:
        try:
            if sys.platform == "win32":
                descriptor = _open_key_windows(key_path)
            else:
                descriptor = os.open(key_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return None
        info = os.fstat(descriptor)
        if (
            not _is_direct_regular_file(info)
            or info.st_size > SECRET_KEY_MAX_BYTES
            or (sys.platform != "win32" and info.st_uid != os.getuid())
        ):
            raise ValueError("expected a small, owner-held regular file")
        # Read only from the admitted descriptor, even if the file grows after fstat.
        with os.fdopen(descriptor, "rb", buffering=0) as key_file:
            descriptor = None
            raw_key = key_file.read(SECRET_KEY_MAX_BYTES + 1)
            if len(raw_key) > SECRET_KEY_MAX_BYTES:
                raise ValueError("key file is too large")
            after = os.fstat(key_file.fileno())
            if (
                after.st_ctime_ns != info.st_ctime_ns
                and info.st_nlink == 2
                and after.st_nlink == 1
                and _key_content_generation(after) == _key_content_generation(info)
            ):
                # The creator may have removed its temporary hard link.
                # Require identical bytes and a stable descriptor on a single reread.
                key_file.seek(0)
                if key_file.read(SECRET_KEY_MAX_BYTES + 1) == raw_key:
                    info, after = after, os.fstat(key_file.fileno())
            if (
                len(raw_key) != info.st_size
                or _key_content_generation(after) != _key_content_generation(info)
                or after.st_ctime_ns != info.st_ctime_ns
            ):
                raise ImproperlyConfigured(
                    f"The packaged secret key file {key_path} changed while being read. "
                    "Close other app processes and finish any key maintenance before retrying."
                )
            key = raw_key.decode("ascii").strip()
            if not key:
                raise ValueError("key is empty")
            if sys.platform != "win32" and stat.S_IMODE(info.st_mode) & 0o077:
                os.fchmod(key_file.fileno(), SECRET_KEY_FILE_MODE)

            try:
                named = key_path.lstat()
            except FileNotFoundError:
                named = None
            # Permission repair and retiring the temporary link can change ctime.
            if (
                named is None
                or not _is_direct_regular_file(named)
                or not os.path.samestat(info, named)
            ):
                raise ImproperlyConfigured(
                    f"The packaged secret key path {key_path} changed while being read. "
                    "Close other app processes and finish any key maintenance before retrying."
                )
        return key
    except (OSError, ValueError) as error:
        raise ImproperlyConfigured(
            f"The packaged secret key file {key_path} is unsafe or invalid. "
            "Use a regular file owned by this user with at most 4096 ASCII bytes, "
            "or remove the key entry to generate a new key (this signs out existing sessions)."
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _is_direct_regular_file(info: os.stat_result) -> bool:
    return stat.S_ISREG(info.st_mode) and not (
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def _key_content_generation(info: os.stat_result) -> tuple[int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns
