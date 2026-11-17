import ctypes
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "desktop_process_guard.py"


def load_guard():
    spec = importlib.util.spec_from_file_location("desktop_process_guard", GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("failure", ["create", "configure", "assign", None])
def test_windows_job_admission_closes_failed_handles(monkeypatch, failure) -> None:
    guard = load_guard()
    kernel = SimpleNamespace(
        CreateJobObjectW=Mock(return_value=0 if failure == "create" else 123),
        SetInformationJobObject=Mock(return_value=failure != "configure"),
        AssignProcessToJobObject=Mock(return_value=failure != "assign"),
        GetCurrentProcess=Mock(return_value=456),
        CloseHandle=Mock(return_value=True),
    )
    monkeypatch.setattr(ctypes, "WinDLL", Mock(return_value=kernel), raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 5, raising=False)
    monkeypatch.setattr(ctypes, "WinError", lambda _: OSError("private host detail"), raising=False)

    if failure:
        with pytest.raises(OSError):
            guard.join_kill_on_close_job()
        assert guard._job_handle is None
    else:
        guard.join_kill_on_close_job()
        assert guard._job_handle == 123
    assert kernel.CloseHandle.call_args_list == (
        [((123,), {})] if failure in {"configure", "assign"} else []
    )
    if failure in {"create", "configure"}:
        kernel.AssignProcessToJobObject.assert_not_called()


def test_windows_job_failure_refuses_manage_command(monkeypatch, capsys) -> None:
    guard = load_guard()
    monkeypatch.setattr(guard, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(guard, "join_kill_on_close_job", Mock(side_effect=OSError("secret")))
    run = Mock()
    watch = Mock()
    monkeypatch.setattr(guard, "run_manage_command", run)
    monkeypatch.setattr(guard, "exit_when_stdin_closes", watch)

    with pytest.raises(SystemExit) as error:
        guard.main(["--watch-stdin", "--", "manage.py"])
    assert error.value.code == 1
    run.assert_not_called()
    watch.assert_not_called()
    assert capsys.readouterr().err == "desktop_process_guard: backend job admission failed\n"


def test_parse_arguments_splits_guard_options_from_the_command() -> None:
    guard = load_guard()

    options, command = guard.parse_arguments(
        ["--app-key", "abc", "--instance", "run-1", "--watch-stdin", "--", "manage.py", "migrate"]
    )

    assert options == {"watch_stdin": True, "app_key": "abc", "instance": "run-1"}
    assert command == ["manage.py", "migrate"]


@pytest.mark.parametrize(
    "argv",
    [["manage.py"], ["--bogus", "--", "manage.py"], ["--instance", "x", "--"]],
)
def test_parse_arguments_rejects_bad_input(argv) -> None:
    with pytest.raises(SystemExit):
        load_guard().parse_arguments(argv)


def test_guard_runs_manage_py_in_process_with_its_arguments(tmp_path: Path) -> None:
    manage = tmp_path / "manage.py"
    manage.write_text(
        "import json, os, sys\n"
        "if __name__ == '__main__':\n"
        "    print(json.dumps([os.getpid(), os.getppid(), sys.argv[1:], sys.path[0]]))\n"
    )

    process = subprocess.Popen(
        [sys.executable, str(GUARD), "--instance", "t", "--", str(manage), "check", "--deploy"],
        stdout=subprocess.PIPE,
        text=True,
    )
    output, _ = process.communicate(timeout=20)

    pid, parent_pid, args, path0 = json.loads(output)
    # manage.py runs inside the guard's own interpreter, not in a child the
    # guard starts. On Windows a venv's python.exe is a launcher that runs the
    # real interpreter as its child, so there the parent is the PID we started.
    assert process.pid in {pid, parent_pid}
    assert args == ["check", "--deploy"]
    assert path0 == str(tmp_path)


def test_guard_exits_when_the_shell_closes_stdin(tmp_path: Path) -> None:
    manage = tmp_path / "manage.py"
    manage.write_text("import time\nif __name__ == '__main__':\n    time.sleep(60)\n")

    process = subprocess.Popen(
        [sys.executable, str(GUARD), "--watch-stdin", "--", str(manage)],
        stdin=subprocess.PIPE,
    )
    time.sleep(0.5)
    assert process.poll() is None

    process.stdin.close()  # what the OS does when the shell process dies
    assert process.wait(timeout=10) in ({0} if sys.platform == "win32" else {0, -9})


@pytest.mark.skipif(ctypes.sizeof(ctypes.c_void_p) != 8, reason="64-bit layout")
def test_job_object_structure_matches_the_windows_64_bit_layout() -> None:
    structure = load_guard().job_object_structures()

    # sizeof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION) on 64-bit Windows.
    assert ctypes.sizeof(structure) == 144
    assert structure.BasicLimitInformation.offset == 0
    assert structure.IoInfo.offset == 64


def test_guarded_command_exits_cleanly_while_the_watchdog_is_reading(tmp_path: Path) -> None:
    manage = tmp_path / "manage.py"
    manage.write_text("if __name__ == '__main__':\n    print('migrated')\n")

    process = subprocess.Popen(
        [sys.executable, str(GUARD), "--watch-stdin", "--", str(manage)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    exit_code = process.wait(timeout=20)
    errors = process.stderr.read()

    assert exit_code == 0, errors
    assert "Fatal Python error" not in errors
    assert process.stdout.read().strip() == "migrated"
    process.stdin.close()


def wait_until(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("owned process did not reach the expected state")


def posix_process_running(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # Linux containers may not promptly reap orphan zombies. They have exited.
    stat = Path(f"/proc/{pid}/stat")
    if sys.platform == "linux" and stat.exists():
        return stat.read_text().split(") ", 1)[1][0] != "Z"
    return True


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")
@pytest.mark.parametrize("retirement", ["pipe", "sigterm"])
def test_posix_guard_retires_descendants_from_shared_group(tmp_path, retirement):
    import os
    import signal

    ready = tmp_path / "ready.json"
    manage = tmp_path / "manage.py"
    manage.write_text(
        "import json, os, signal, subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', "
        "'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)'])\n"
        f"with open({str(ready)!r}, 'w') as output:\n"
        "    json.dump([os.getpid(), os.getpgrp(), child.pid], output)\n"
        "time.sleep(60)\n"
    )
    # Deliberately share the test runner's group at launch. The guard must
    # isolate itself before executing manage.py, never signal this group.
    process = subprocess.Popen(
        [sys.executable, str(GUARD), "--watch-stdin", "--", str(manage)],
        stdin=subprocess.PIPE,
    )
    child_pid = None
    try:
        wait_until(lambda: ready.exists() and ready.stat().st_size > 0)
        leader, group, child_pid = json.loads(ready.read_text())
        assert posix_process_running(child_pid)
        if retirement == "pipe":
            process.stdin.close()
        else:
            process.send_signal(signal.SIGTERM)
        process.wait(timeout=10)
        wait_until(lambda: not posix_process_running(child_pid))
        assert leader == group
        assert group != os.getpgrp()
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        process.stdin.close()
        if child_pid is not None and posix_process_running(child_pid):
            os.kill(child_pid, signal.SIGKILL)


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows Job Object acceptance")
@pytest.mark.parametrize("retirement", ["pipe", "crash"])
def test_windows_owned_child_cleanup(tmp_path, retirement):
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    ready = tmp_path / "ready.json"
    manage = tmp_path / "manage.py"
    manage.write_text(
        "import json, os, subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"with open({str(ready)!r}, 'w') as output:\n"
        "    json.dump([os.getpid(), child.pid], output)\n"
        "time.sleep(60)\n"
    )
    process = subprocess.Popen(
        [sys.executable, str(GUARD), "--watch-stdin", "--", str(manage)],
        stdin=subprocess.PIPE,
    )
    handles = []
    try:
        wait_until(lambda: ready.exists() and ready.stat().st_size > 0)
        for pid in json.loads(ready.read_text()):
            handle = kernel.OpenProcess(0x100001, False, pid)  # SYNCHRONIZE | TERMINATE
            assert handle, ctypes.get_last_error()
            handles.append(handle)
        if retirement == "pipe":
            process.stdin.close()
        else:
            assert kernel.TerminateProcess(handles[0], 1)
        for handle in handles:
            assert kernel.WaitForSingleObject(handle, 10000) == 0
        process.wait(timeout=10)
    finally:
        for handle in handles:
            kernel.TerminateProcess(handle, 1)
            kernel.CloseHandle(handle)
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        process.stdin.close()
