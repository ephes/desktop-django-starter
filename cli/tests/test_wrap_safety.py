"""Synthetic, platform-independent regressions for wrapping admission and streams."""

from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pytest
from dds import wrap
from dds.config import WrapperConfig, default_config_path, save_wrapper_config


@pytest.mark.parametrize("run_agent", [False, True])
@pytest.mark.parametrize("force", [False, True])
def test_failed_status_never_launches(monkeypatch, tmp_path, capsys, run_agent, force):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "manage.py").touch()
    calls = []

    def git(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(
            returncode=128 if command[1] == "status" else 0,
            stdout="",
            stderr="synthetic index failure " + "x" * 10000,
        )

    monkeypatch.setattr(wrap.subprocess, "run", git)
    monkeypatch.setattr(wrap.shutil, "which", lambda name: name)
    monkeypatch.setattr(wrap, "SKILL_PATH", tmp_path / "manage.py")
    monkeypatch.setattr(wrap, "_run_claude", lambda *args: pytest.fail("agent launched"))
    monkeypatch.setattr(wrap.os, "execvp", lambda *args: pytest.fail("agent launched"))
    with pytest.raises(SystemExit) as error:
        wrap.run_wrap(
            run_agent=run_agent, agent="claude", model=None, force=force, emit_prompt=False
        )
    assert error.value.code == 1
    output = capsys.readouterr()
    assert "git status failed (exit 128)" in output.err
    assert "synthetic index failure" in output.err
    assert len(output.err) < 1200
    assert "Working tree clean" not in output.out
    assert ["git", "status", "--porcelain"] in calls


@pytest.mark.parametrize(
    "dirty,force,passes", [(False, False, True), (True, False, False), (True, True, True)]
)
def test_successful_status_retains_dirty_policy(monkeypatch, tmp_path, dirty, force, passes):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "manage.py").touch()
    monkeypatch.setattr(wrap, "SKILL_PATH", tmp_path / "manage.py")
    monkeypatch.setattr(wrap.shutil, "which", lambda name: name)
    monkeypatch.setattr(
        wrap.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout=" M manage.py" if dirty else "", stderr=""
        ),
    )
    if passes:
        wrap.run_wrap(run_agent=False, agent=None, model=None, force=force, emit_prompt=False)
    else:
        with pytest.raises(SystemExit):
            wrap.run_wrap(run_agent=False, agent=None, model=None, force=force, emit_prompt=False)


@pytest.mark.parametrize("harness", ["claude", "codex", "pi"])
@pytest.mark.parametrize("model", [None, "explicit-model"])
def test_saved_model_belongs_to_harness(harness, model):
    save_wrapper_config(WrapperConfig("claude", "saved-model"), default_config_path())
    resolved = wrap._resolve_run_config(harness, model)
    expected = model or ("saved-model" if harness == "claude" else None)
    assert resolved.model == expected
    assert resolved.model_source == ("cli" if model else "config" if expected else None)


@pytest.mark.parametrize("harness", ["claude", "codex", "pi"])
def test_setup_reuses_only_matching_model(monkeypatch, harness):
    save_wrapper_config(WrapperConfig("claude", "saved-model"), default_config_path())
    monkeypatch.setattr(
        wrap,
        "detect_installed_harnesses",
        lambda: {name: name for name in ("claude", "codex", "pi")},
    )
    answers = iter([harness, ""])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    result = wrap._run_setup_flow(
        existing_config=WrapperConfig("claude", "saved-model"), config_path=default_config_path()
    )
    assert result.model == ("saved-model" if harness == "claude" else None)
    assert wrap.load_wrapper_config() == result


class FakeProcess:
    def __init__(self, data, returncode):
        self.stdout = io.BytesIO(data)
        self.returncode = returncode

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def wait(self):
        return self.returncode


@pytest.fixture
def fake_claude(monkeypatch):
    cleaned = []

    def install(data, returncode=0):
        process = FakeProcess(data, returncode)
        monkeypatch.setattr(wrap.subprocess, "Popen", lambda *args, **kwargs: process)
        monkeypatch.setattr(wrap, "_terminate_claude_process", lambda child: cleaned.append(child))
        return process, cleaned

    return install


@pytest.mark.parametrize("returncode", [0, 7])
@pytest.mark.parametrize("terminal", [None, True, False, "false", "missing-flag"])
def test_claude_requires_successful_terminal_result(fake_claude, capsys, terminal, returncode):
    event = {"type": "result"}
    if terminal != "missing-flag":
        event["is_error"] = terminal
    data = b'{"type":"system","subtype":"init"}\n'
    if terminal is not None:
        data += json.dumps(event).encode() + b"\n"
    process, cleaned = fake_claude(data, returncode)
    if terminal is False and returncode == 0:
        wrap._run_claude("unused", "unused", None)
    else:
        with pytest.raises(SystemExit) as error:
            wrap._run_claude("unused", "unused", None)
        assert error.value.code == (returncode or 1)
        if returncode == 0:
            assert "terminal result" in capsys.readouterr().err
    assert cleaned == [process]
    assert process.stdout.closed


@pytest.mark.parametrize("newline", [False, True])
def test_oversized_record_is_bounded_and_reaped(fake_claude, monkeypatch, capsys, newline):
    # The fake also models an endless producer: no unbounded read is permitted.
    monkeypatch.setattr(wrap, "_CLAUDE_MAX_EVENT_BYTES", 128)
    process, cleaned = fake_claude(b"x" * 10000 + (b"\n" if newline else b""))
    sizes = []
    stream = process.stdout

    class LimitedPipe:
        closed = False

        def readline(self, size=-1):
            assert 0 < size <= 129
            sizes.append(size)
            return stream.readline(size)

        def close(self):
            self.closed = True
            stream.close()

    process.stdout = LimitedPipe()
    with pytest.raises(SystemExit) as error:
        wrap._run_claude("unused", "unused", None)
    assert error.value.code == 1
    assert sizes == [129]
    assert cleaned == [process]
    assert process.stdout.closed
    assert "event exceeds 128 bytes" in capsys.readouterr().err


def test_split_utf8_and_final_unterminated_record(fake_claude, capsys):
    data = (
        json.dumps(
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "Grüße 🐎"}]}},
            ensure_ascii=False,
        )
        + "\n"
        + json.dumps({"type": "result", "is_error": False})
    ).encode()
    process, cleaned = fake_claude(b"")

    class SplitBytes(io.RawIOBase):
        def readable(self):
            return True

        def readinto(self, buffer):
            nonlocal data
            chunk, data = data[:1], data[1:]
            buffer[: len(chunk)] = chunk
            return len(chunk)

    process.stdout = io.BufferedReader(SplitBytes())
    wrap._run_claude("unused", "unused", None)
    assert "Grüße 🐎" in capsys.readouterr().out
    assert cleaned == [process]
    assert process.stdout.closed


@pytest.mark.parametrize("kind", ["tool", "text", "plain"])
def test_display_budget_per_event(fake_claude, capsys, kind):
    payload = "ü" * 10000
    if kind == "tool":
        event = {
            "type": "user",
            "message": {"content": [{"type": "tool_result", "is_error": True, "content": payload}]},
        }
    else:
        event = {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": payload} for _ in range(5)]},
        }
    record = payload if kind == "plain" else json.dumps(event)
    fake_claude((record + '\n{"type":"result","is_error":false}\n').encode())
    wrap._run_claude("unused", "unused", None)
    output = capsys.readouterr().out
    assert "[truncated]" in output
    assert len(output.encode()) < 4300


@pytest.mark.parametrize(
    "events",
    [
        [{"type": "result", "is_error": False}, {"type": "result", "is_error": False}],
        [{"type": "result", "is_error": False, "subtype": "error_during_execution"}],
    ],
)
def test_invalid_terminal_sequence_fails(fake_claude, events):
    fake_claude("\n".join(json.dumps(event) for event in events).encode())
    with pytest.raises(SystemExit) as error:
        wrap._run_claude("unused", "unused", None)
    assert error.value.code == 1


@pytest.mark.parametrize("newline", [False, True])
def test_oversized_child_is_terminated_and_reaped(monkeypatch, newline):
    import subprocess
    import sys
    import time

    processes = []
    real_popen = subprocess.Popen

    def launch(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    script = (
        "import sys, time; sys.stdout.buffer.write(b'x' * 1024 "
        + ("+ b'\\n'" if newline else "")
        + "); sys.stdout.buffer.flush(); time.sleep(30)"
    )
    monkeypatch.setattr(wrap, "_CLAUDE_MAX_EVENT_BYTES", 128)
    monkeypatch.setattr(wrap, "_CLAUDE_TERMINATION_GRACE", 0.1)
    monkeypatch.setattr(wrap, "_claude_command", lambda *args: [sys.executable, "-c", script])
    monkeypatch.setattr(wrap.subprocess, "Popen", launch)
    started = time.monotonic()
    try:
        with pytest.raises(SystemExit) as error:
            wrap._run_claude("unused", "unused", None)
        assert error.value.code == 1
        assert time.monotonic() - started < 8
        assert processes[0].poll() is not None
        assert processes[0].stdout.closed
    finally:
        if processes:
            if processes[0].poll() is None:
                processes[0].kill()
            processes[0].wait(timeout=2)


def test_wrap_help_explains_harness_models_and_failed_inspection(capsys):
    from dds.cli import main

    with pytest.raises(SystemExit) as error:
        main(["wrap", "--help"])
    assert error.value.code == 0
    help_text = " ".join(capsys.readouterr().out.split())
    assert "saved model is used only for its matching harness" in help_text
    assert "failed Git inspection still blocks" in help_text
