from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time

import pytest
from dds import wrap


@pytest.mark.skipif(os.name == "nt", reason="POSIX process groups required")
@pytest.mark.parametrize("leader_exits", [True, False])
@pytest.mark.parametrize("failure", [KeyboardInterrupt, ValueError])
@pytest.mark.parametrize("ignore_term", [True, False])
def test_run_claude_cleans_descendants(tmp_path, monkeypatch, leader_exits, failure, ignore_term):
    monkeypatch.setattr(wrap, "_CLAUDE_TERMINATION_GRACE", 0.2)
    pid_file = tmp_path / "descendant.pid"
    script = tmp_path / "child.py"
    term_handler = "signal.SIG_IGN" if ignore_term else "signal.SIG_DFL"
    script.write_text(
        "import os, signal, time\n"
        "pid = os.fork()\n"
        "if pid == 0:\n"
        f"    signal.signal(signal.SIGTERM, {term_handler})\n"
        f"    open({str(pid_file)!r}, 'w').write(str(os.getpid()))\n"
        "    while True: time.sleep(1)\n"
        "while not os.path.exists(" + repr(str(pid_file)) + "): time.sleep(.01)\n"
        "print('ready', flush=True)\n"
        + ("os._exit(0)\n" if leader_exits else "while True: time.sleep(1)\n")
    )
    monkeypatch.setattr(wrap, "_claude_command", lambda *args: [sys.executable, str(script)])
    processes = []
    real_popen = subprocess.Popen

    def launch(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(wrap.subprocess, "Popen", launch)

    def interrupt(line):
        assert line == "ready\n"
        if leader_exits:
            processes[0].wait(timeout=2)
        raise failure("injected reader failure")

    monkeypatch.setattr(wrap, "_format_claude_stream_event", interrupt)
    started = time.monotonic()
    try:
        with pytest.raises(failure):
            wrap._run_claude("unused", "unused", None)
        assert time.monotonic() - started < 8
        assert processes[0].poll() is not None
        assert processes[0].stdout.closed
        descendant = int(pid_file.read_text())
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                os.kill(descendant, 0)
            except ProcessLookupError:
                break
            time.sleep(0.02)
        else:
            pytest.fail("owned descendant survived cleanup")
    finally:
        if processes:
            try:
                os.killpg(processes[0].pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            processes[0].wait(timeout=2)
            if processes[0].stdout:
                processes[0].stdout.close()


@pytest.mark.parametrize("returncode", [0, 7])
def test_normal_completion_preserves_exit_code(monkeypatch, returncode):
    monkeypatch.setattr(
        wrap,
        "_claude_command",
        lambda *args: [sys.executable, "-c", f"print('done'); raise SystemExit({returncode})"],
    )
    if returncode:
        with pytest.raises(SystemExit) as error:
            wrap._run_claude("unused", "unused", None)
        assert error.value.code == returncode
    else:
        wrap._run_claude("unused", "unused", None)


@pytest.mark.skipif(os.name == "nt", reason="POSIX group signaling")
def test_group_permission_error_falls_back_to_leader(monkeypatch):
    monkeypatch.setattr(wrap, "_CLAUDE_TERMINATION_GRACE", 0.2)
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True
    )

    def denied(*args):
        raise PermissionError("no signalable group members")

    monkeypatch.setattr(wrap.os, "killpg", denied)
    try:
        wrap._terminate_claude_process(process)
        assert process.poll() is not None
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=2)


@pytest.mark.skipif(os.name == "nt", reason="POSIX zombie group behavior")
def test_reader_error_with_unreaped_exited_leader(monkeypatch):
    processes = []
    real_popen = subprocess.Popen

    def launch(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(wrap.subprocess, "Popen", launch)
    monkeypatch.setattr(
        wrap, "_claude_command", lambda *args: [sys.executable, "-c", "print('done', flush=True)"]
    )

    def fail(line):
        time.sleep(0.1)  # child exits, but has not been poll()ed/wait()ed
        raise ValueError("original reader error")

    monkeypatch.setattr(wrap, "_format_claude_stream_event", fail)
    with pytest.raises(ValueError, match="original reader error"):
        wrap._run_claude("unused", "unused", None)
    assert processes[0].poll() is not None
    assert processes[0].stdout.closed


@pytest.mark.skipif(os.name == "nt", reason="POSIX descendants")
def test_normal_completion_cleans_redirected_descendant(tmp_path, monkeypatch):
    monkeypatch.setattr(wrap, "_CLAUDE_TERMINATION_GRACE", 0.2)
    pid_file = tmp_path / "pid"
    script = (
        "import os, signal, time\n"
        "if os.fork() == 0:\n"
        "    sink = os.open(os.devnull, os.O_WRONLY)\n"
        "    os.dup2(sink, 1); os.dup2(sink, 2)\n"
        "    signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        f"    open({str(pid_file)!r}, 'w').write(str(os.getpid()))\n"
        "    while True: time.sleep(1)\n"
        f"while not os.path.exists({str(pid_file)!r}): time.sleep(.01)\n"
        "print('done', flush=True)\n"
    )
    monkeypatch.setattr(wrap, "_claude_command", lambda *args: [sys.executable, "-c", script])
    try:
        wrap._run_claude("unused", "unused", None)
        descendant = int(pid_file.read_text())
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                os.kill(descendant, 0)
            except ProcessLookupError:
                break
            time.sleep(0.02)
        else:
            pytest.fail("descendant survived normal completion")
    finally:
        if pid_file.exists():
            try:
                os.kill(int(pid_file.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_cleanup_error_does_not_replace_reader_error(monkeypatch):
    monkeypatch.setattr(
        wrap, "_claude_command", lambda *args: [sys.executable, "-c", "print('done', flush=True)"]
    )

    def fail(line):
        time.sleep(0.1)
        raise ValueError("original reader error")

    cleanup_calls = []

    def cleanup_fails(process):
        cleanup_calls.append(process)
        raise subprocess.TimeoutExpired("synthetic", 0.2)

    monkeypatch.setattr(wrap, "_format_claude_stream_event", fail)
    monkeypatch.setattr(wrap, "_terminate_claude_process", cleanup_fails)
    with pytest.raises(ValueError, match="original reader error"):
        wrap._run_claude("unused", "unused", None)
    assert len(cleanup_calls) == 1


@pytest.mark.parametrize("record", ["null", "[]", "42", '"text"', "true", "whitespace-error"])
@pytest.mark.parametrize("returncode", [0, 7])
def test_malformed_progress_preserves_completion(monkeypatch, capsys, record, returncode):
    if record == "whitespace-error":
        record = json.dumps(
            {
                "type": "user",
                "message": {
                    "content": [{"type": "tool_result", "is_error": True, "content": " \t\n "}]
                },
            }
        )
    records = [
        json.dumps(
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "before"}]}}
        ),
        record,
        json.dumps(
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "after"}]}}
        ),
        json.dumps({"type": "result", "is_error": False}),
    ]
    script = f"print({chr(10).join(records)!r}); raise SystemExit({returncode})"
    monkeypatch.setattr(wrap, "_claude_command", lambda *args: [sys.executable, "-c", script])
    if returncode:
        with pytest.raises(SystemExit) as error:
            wrap._run_claude("unused", "unused", None)
        assert error.value.code == returncode
    else:
        wrap._run_claude("unused", "unused", None)
    output = capsys.readouterr().out
    expected = "before\n"
    if "tool_result" in record:
        expected += "claude tool error: unknown error\n"
    assert expected + "after\nclaude finished" in output
