"""Small filesystem admission helpers for private desktop state generations."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import BinaryIO

from django.core.exceptions import ImproperlyConfigured

from .runtime_secret import _open_key_windows


def state_error(detail: str) -> ImproperlyConfigured:
    return ImproperlyConfigured(
        f"App state is unsafe or incomplete ({detail}); close all app processes and repair "
        "or restore the retained generation from backup before retrying."
    )


def identity(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


def _generation(info: os.stat_result) -> tuple[int, ...]:
    return (*identity(info), info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def admit(path: Path, *, directory: bool = False) -> os.stat_result:
    info = path.lstat()
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if (
        not expected(info.st_mode)
        or getattr(info, "st_file_attributes", 0) & 0x400
        or (os.name != "nt" and info.st_uid != os.getuid())
        or (not directory and info.st_nlink != 1)
    ):
        raise state_error("expected an owned direct directory or single-link regular file")
    return info


@contextmanager
def directory_guard(path: Path, *, parent_fd: int | None = None) -> Iterator[int | None]:
    """Pin POSIX directory identity; Windows conservatively rechecks its name.

    System parent aliases (e.g. macOS /tmp) are allowed. The app-data directory
    itself and every state directory must be direct, owned entries.
    """
    before = admit(path, directory=True)
    descriptor = None
    try:
        if os.name != "nt":
            descriptor = os.open(
                path.name if parent_fd is not None else path,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent_fd,
            )
            if identity(os.fstat(descriptor)) != identity(before):
                raise state_error("directory changed while opening")
        yield descriptor
        if identity(admit(path, directory=True)) != identity(before):
            raise state_error("directory changed during initialization")
    except BaseException:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
        raise
    else:
        if descriptor is not None:
            os.close(descriptor)


@contextmanager
def regular_reader(
    path: Path, *, parent_fd: int | None = None, stable: bool = False
) -> Iterator[BinaryIO]:
    before = admit(path)
    signature = _generation if stable else identity
    descriptor = (
        _open_key_windows(path)
        if os.name == "nt"
        else os.open(
            path.name if parent_fd is not None else path,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=parent_fd,
        )
    )
    try:
        # Keep ownership here even if fdopen fails after creating its raw stream.
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            if signature(os.fstat(stream.fileno())) != signature(before):
                raise state_error("file changed while opening")
            yield stream
            if signature(os.fstat(stream.fileno())) != signature(before) or signature(
                admit(path)
            ) != signature(before):
                raise state_error("file changed during initialization")
    except BaseException:
        with suppress(OSError):
            os.close(descriptor)
        raise
    else:
        os.close(descriptor)


def optional_file(path: Path) -> bool:
    try:
        admit(path)
    except FileNotFoundError:
        return False
    return True


@contextmanager
def copy_media(source: Path, destination: Path) -> Iterator[None]:
    """Stage bounded media before the database backup and verify it afterwards."""
    try:
        source.lstat()
    except FileNotFoundError:
        has_media = False
    else:
        has_media = True
    if not has_media:
        # The legacy layout may start without a media directory.
        yield
        try:
            source.lstat()
        except FileNotFoundError:
            return
        raise state_error("media tree appeared during database backup")

    limits = []
    for suffix, default in [("ENTRIES", 100_000), ("BYTES", 2 * 1024**3), ("DEPTH", 64)]:
        try:
            limit = int(os.environ.get(f"DESKTOP_DJANGO_MEDIA_MAX_{suffix}", str(default)))
            if limit <= 0:
                raise ValueError
        except ValueError as error:
            raise state_error(
                f"media {suffix.lower()} budget must be a positive integer"
            ) from error
        limits.append(limit)
    max_entries, max_bytes, max_depth = limits
    entries = 0
    source_bytes = 0
    directories: list[tuple[Path, tuple[int, ...]]] = []
    files: list[tuple[Path, tuple[int, ...]]] = []

    def copy_directory(src: Path, dst: Path, depth: int, parent_fd: int | None = None) -> None:
        nonlocal entries, source_bytes
        if depth > max_depth:
            raise state_error("media depth budget exceeded")
        with directory_guard(src, parent_fd=parent_fd) as source_fd:
            source_info = admit(src, directory=True) if source_fd is None else os.fstat(source_fd)
            directories.append((src, _generation(source_info)))
            dst.mkdir(mode=0o700)
            # scandir streams entries instead of allocating the entire tree.
            with os.scandir(source_fd if source_fd is not None else src) as children:
                for entry in children:
                    entries += 1
                    if entries > max_entries:
                        raise state_error("media entry budget exceeded")
                    child = src / entry.name
                    target = dst / entry.name
                    if stat.S_ISDIR(child.lstat().st_mode):
                        copy_directory(child, target, depth + 1, source_fd)
                    else:
                        with (
                            regular_reader(child, parent_fd=source_fd, stable=True) as reader,
                            target.open("xb") as writer,
                        ):
                            initial = os.fstat(reader.fileno())
                            remaining = initial.st_size
                            if remaining > max_bytes - source_bytes:
                                raise state_error("media byte budget exceeded")
                            while remaining:
                                chunk = reader.read(min(1024 * 1024, remaining))
                                if not chunk:
                                    raise state_error("media file truncated during copy")
                                remaining -= len(chunk)
                                source_bytes += len(chunk)
                                if writer.write(chunk) != len(chunk):
                                    raise state_error("short write while copying a media file")
                        files.append((child, _generation(initial)))

    try:
        copy_directory(source, destination, 0)
    except (OSError, ImproperlyConfigured) as error:
        raise state_error("media tree refused or copy failed") from error

    yield

    try:
        # Earlier entries can change during traversal or the database backup.
        # The entry budget bounds the number of retained signatures plus the root.
        for directory, generation in reversed(directories):
            if _generation(admit(directory, directory=True)) != generation:
                raise state_error("media directory changed during copy")
        for file, generation in files:
            if _generation(admit(file)) != generation:
                raise state_error("media file changed during copy")
    except (OSError, ImproperlyConfigured) as error:
        raise state_error("media tree refused or copy failed") from error
