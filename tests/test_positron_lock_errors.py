from pathlib import Path

import pytest

POSITRON_SRC = Path(__file__).resolve().parents[1] / "shells" / "positron" / "src"


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.syspath_prepend(str(POSITRON_SRC))
    from desktop_django_starter_positron import runtime

    return runtime


class FailingHandle:
    def __init__(self, handle, failure=None, close_error=False):
        self.handle = handle
        self.failure = failure
        self.close_error = close_error
        self.failed = False
        self.close_calls = 0

    def __getattr__(self, name):
        method = getattr(self.handle, name)
        if name != self.failure:
            return method

        def fail(*args, **kwargs):
            self.failed = True
            raise OSError(f"injected {name}")

        return fail

    def close(self):
        self.close_calls += 1
        self.handle.close()
        if self.close_error:
            raise OSError("injected close")


@pytest.mark.parametrize(
    "failure", ["lock-before", "lock-after", "seek", "truncate", "write", "flush"]
)
@pytest.mark.parametrize("cleanup_error", [False, True])
def test_acquisition_error_closes_handle_and_preserves_error(
    tmp_path, monkeypatch, runtime, failure, cleanup_error
):
    real_open = Path.open
    real_lock = runtime.locks.lock
    handles = []
    unlock_calls = []

    def open_handle(path, *args, **kwargs):
        handle = FailingHandle(real_open(path, *args, **kwargs), failure, cleanup_error)
        handles.append(handle)
        return handle

    def lock(handle, flags):
        if failure == "lock-before":
            handle.failed = True
            raise OSError("injected lock-before")
        acquired = real_lock(handle, flags)
        assert acquired
        if failure == "lock-after":
            handle.failed = True
            raise OSError("injected lock-after")
        return acquired

    real_unlock = runtime.locks.unlock

    def unlock(handle):
        unlock_calls.append(handle)
        if cleanup_error:
            raise OSError("injected unlock")
        return real_unlock(handle)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", open_handle)
        patch.setattr(runtime.locks, "lock", lock)
        patch.setattr(runtime.locks, "unlock", unlock)
        with pytest.raises(OSError, match=f"injected {failure}") as error:
            runtime.acquire_instance_lock(tmp_path)
        assert handles[0].failed
        assert handles[0].close_calls >= 1
        assert handles[0].closed
        if not failure.startswith("lock-"):
            assert unlock_calls == handles

    # Keep the failure traceback alive: GC must not be what releases the lock.
    assert error.value.__traceback__ is not None
    later = runtime.acquire_instance_lock(tmp_path)
    assert later is not None
    runtime.release_instance_lock(later)


@pytest.mark.parametrize("close_error", [False, True])
def test_unlock_error_closes_handle_and_preserves_error(
    tmp_path, monkeypatch, runtime, close_error
):
    handle = FailingHandle(runtime.acquire_instance_lock(tmp_path), close_error=close_error)
    unlock_calls = []

    def unlock(handle):
        unlock_calls.append(handle)
        raise OSError("injected unlock")

    with monkeypatch.context() as patch:
        patch.setattr(runtime.locks, "unlock", unlock)
        with pytest.raises(OSError, match="injected unlock") as error:
            runtime.release_instance_lock(handle)
        assert unlock_calls == [handle]
        assert handle.close_calls == 1
        assert handle.closed

    assert error.value.__traceback__ is not None
    later = runtime.acquire_instance_lock(tmp_path)
    assert later is not None
    runtime.release_instance_lock(later)
