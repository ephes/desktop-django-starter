"""Unlock failures must release ownership without hiding initialization errors."""

import os
import sys
from types import SimpleNamespace

import pytest

from desktop_django_starter import state_staging


@pytest.mark.parametrize("platform", ["posix", "nt"])
@pytest.mark.parametrize("primary", [False, True])
def test_unlock_failure_always_closes_owned_descriptor(
    monkeypatch, tmp_path, caplog, platform, primary
):
    closed = []
    real_close = os.close

    def close(descriptor):
        closed.append(descriptor)
        real_close(descriptor)

    def unlock(*args):
        raise OSError("injected unlock failure")

    if platform == "nt":
        monkeypatch.setitem(
            sys.modules,
            "msvcrt",
            SimpleNamespace(
                LK_NBLCK=1, LK_UNLCK=2, locking=lambda fd, mode, n: unlock() if mode == 2 else None
            ),
        )
    else:
        import fcntl

        real_flock = fcntl.flock
        monkeypatch.setattr(
            fcntl,
            "flock",
            lambda fd, mode: unlock() if mode == fcntl.LOCK_UN else real_flock(fd, mode),
        )
    # A local os proxy selects the branch without changing pathlib's host platform.
    monkeypatch.setattr(
        state_staging,
        "os",
        SimpleNamespace(
            **{name: getattr(os, name) for name in dir(os) if name not in {"name", "close"}},
            name=platform,
            close=close,
        ),
    )
    expected = ValueError if primary else OSError
    with pytest.raises(expected, match="staging failed" if primary else "unlock failure"):
        with state_staging.initialization_lock(tmp_path):
            if primary:
                raise ValueError("staging failed")
    assert len(closed) == 1
    with pytest.raises(OSError):
        os.fstat(closed[0])
    if primary:
        assert "unlock" in caplog.text.lower()
    # Closing the descriptor releases a POSIX lock even when explicit unlock failed.
    if platform == "posix":
        descriptor = os.open(tmp_path / state_staging.LOCK_FILENAME, os.O_RDWR)
        try:
            real_flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            real_close(descriptor)


@pytest.mark.skipif(os.name == "nt", reason="exercises the POSIX flock path")
def test_unlock_failure_is_reported_when_called_from_an_exception_handler(monkeypatch, tmp_path):
    """A caller's handled exception is not the body's error and must not hide unlock failure."""
    import fcntl

    real_flock = fcntl.flock

    def flock(descriptor, mode):
        if mode == fcntl.LOCK_UN:
            raise OSError("injected unlock failure")
        return real_flock(descriptor, mode)

    monkeypatch.setattr(fcntl, "flock", flock)
    try:
        raise KeyError("caller context")
    except KeyError:
        with pytest.raises(OSError, match="unlock failure"):
            with state_staging.initialization_lock(tmp_path):
                pass
