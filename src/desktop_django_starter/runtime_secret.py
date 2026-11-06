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
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

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


def _open_key_windows(key_path: Path) -> int:
    """Open the entry itself, including reparse points, using the Windows API."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    # GENERIC_READ, shared read/write/delete, OPEN_EXISTING,
    # FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS.
    handle = create_file(str(key_path), 0x80000000, 0x7, None, 3, 0x02200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]
    try:
        return msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)  # type: ignore[attr-defined]
    except BaseException:
        close_handle(handle)
        raise


def _read_secret_key(key_path: Path) -> str | None:
    descriptor = None
    try:
        if sys.platform == "win32":
            descriptor = _open_key_windows(key_path)
        else:
            descriptor = os.open(key_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & 0x400  # reparse point
            or info.st_size > SECRET_KEY_MAX_BYTES
            or (sys.platform != "win32" and info.st_uid != os.getuid())
        ):
            raise ValueError("expected a small, owner-held regular file")
        # Bounded even if the file grows after fstat. No pathname is reopened.
        with os.fdopen(descriptor, "rb") as key_file:
            descriptor = None
            raw_key = key_file.read(SECRET_KEY_MAX_BYTES + 1)
            if len(raw_key) > SECRET_KEY_MAX_BYTES:
                raise ValueError("key file is too large")
            key = raw_key.decode("ascii").strip()
            if not key:
                raise ValueError("key is empty")
            if sys.platform != "win32" and stat.S_IMODE(info.st_mode) & 0o077:
                os.fchmod(key_file.fileno(), SECRET_KEY_FILE_MODE)
        return key
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        raise ImproperlyConfigured(
            f"The packaged secret key file {key_path} is unsafe or invalid. "
            "Use a regular file owned by this user with at most 4096 ASCII bytes, "
            "or remove the key entry to generate a new key (this signs out existing sessions)."
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
