import ctypes
import importlib.util
import json
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
    assert process.wait(timeout=10) == 0


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
