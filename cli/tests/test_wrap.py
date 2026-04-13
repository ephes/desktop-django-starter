from __future__ import annotations

import json
from pathlib import Path

import pytest
from dds.cli import main
from dds.config import (
    ConfigError,
    WrapperConfig,
    default_config_path,
    load_wrapper_config,
    save_wrapper_config,
)
from dds.wrap import (
    HarnessResolutionError,
    _claude_command,
    _codex_command,
    _format_claude_stream_event,
    _pi_command,
    _resolve_run_config,
    run_init,
)


def _event(data: dict[str, object]) -> str:
    return json.dumps(data)


def test_format_claude_stream_event_skips_hook_payloads() -> None:
    assert (
        _format_claude_stream_event(
            _event(
                {
                    "type": "system",
                    "subtype": "hook_response",
                    "output": "large hook context",
                }
            )
        )
        == []
    )


def test_format_claude_stream_event_reports_session_start() -> None:
    assert _format_claude_stream_event(
        _event(
            {
                "type": "system",
                "subtype": "init",
                "session_id": "abc-123",
                "model": "claude-opus-4-6",
            }
        )
    ) == ["claude session: abc-123 (claude-opus-4-6)"]


def test_format_claude_stream_event_skips_incomplete_session_start() -> None:
    assert (
        _format_claude_stream_event(
            _event({"type": "system", "subtype": "init", "session_id": "abc-123"})
        )
        == []
    )


def test_format_claude_stream_event_skips_empty_assistant_content() -> None:
    assert (
        _format_claude_stream_event(_event({"type": "assistant", "message": {"content": []}})) == []
    )


def test_format_claude_stream_event_reports_text_and_tool_use() -> None:
    assert _format_claude_stream_event(
        _event(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "Creating Electron files."},
                        {
                            "type": "tool_use",
                            "name": "Write",
                            "input": {"file_path": "/tmp/app/electron/main.js"},
                        },
                    ]
                },
            }
        )
    ) == [
        "Creating Electron files.",
        "claude tool: Write /tmp/app/electron/main.js",
    ]


def test_format_claude_stream_event_does_not_print_bash_commands() -> None:
    assert _format_claude_stream_event(
        _event(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "input": {"command": "export TOKEN=secret && npm test"},
                        },
                    ]
                },
            }
        )
    ) == ["claude tool: Bash"]


def test_format_claude_stream_event_reports_tool_errors() -> None:
    assert _format_claude_stream_event(
        _event(
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "is_error": True,
                            "content": "ENOENT: no such file or directory\nsecond line",
                        }
                    ]
                },
            }
        )
    ) == ["claude tool error: ENOENT: no such file or directory"]


def test_format_claude_stream_event_reports_result() -> None:
    assert _format_claude_stream_event(
        _event({"type": "result", "is_error": False, "duration_ms": 12345})
    ) == ["claude finished in 12.3s"]
    assert _format_claude_stream_event(_event({"type": "result", "is_error": False})) == [
        "claude finished"
    ]
    assert _format_claude_stream_event(
        _event({"type": "result", "is_error": True, "subtype": "error_max_budget_usd"})
    ) == ["claude failed: error_max_budget_usd"]


def test_format_claude_stream_event_preserves_non_json_lines() -> None:
    assert _format_claude_stream_event("plain output\n") == ["plain output"]
    assert _format_claude_stream_event("{broken") == ["{broken"]


def test_claude_command_includes_model_when_set() -> None:
    command = _claude_command("prompt", "/tmp/assets", "claude-opus-4-6")

    assert command == [
        "claude",
        "--dangerously-skip-permissions",
        "-p",
        "prompt",
        "--add-dir",
        "/tmp/assets",
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        "claude-opus-4-6",
    ]


def test_pi_command_uses_default_or_custom_model() -> None:
    assert _pi_command("prompt", None) == [
        "pi",
        "--model",
        "openai-codex/gpt-5.4",
        "--thinking",
        "high",
        "-p",
        "prompt",
    ]
    assert _pi_command("prompt", "openai/gpt-5.4-mini") == [
        "pi",
        "--model",
        "openai/gpt-5.4-mini",
        "--thinking",
        "high",
        "-p",
        "prompt",
    ]


def test_codex_command_includes_model_before_prompt_when_set() -> None:
    assert _codex_command("prompt", "/tmp/assets", "gpt-5.4") == [
        "codex",
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "--add-dir",
        "/tmp/assets",
        "--model",
        "gpt-5.4",
        "prompt",
    ]


def test_save_and_load_wrapper_config_round_trip(tmp_path: Path) -> None:
    config_path = tmp_path / "dds" / "config.toml"

    saved_path = save_wrapper_config(
        WrapperConfig(harness="codex", model="gpt-5.4"),
        config_path,
    )

    assert saved_path == config_path
    assert config_path.read_text() == '[wrap]\nharness = "codex"\nmodel = "gpt-5.4"\n'
    assert load_wrapper_config(config_path) == WrapperConfig("codex", "gpt-5.4")


def test_load_wrapper_config_rejects_invalid_harness(tmp_path: Path) -> None:
    config_path = tmp_path / "dds" / "config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text('[wrap]\nharness = "unknown"\n')

    with pytest.raises(ConfigError):
        load_wrapper_config(config_path)


def test_resolve_run_config_prefers_cli_harness_over_saved_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    save_wrapper_config(WrapperConfig("claude", "saved-model"), default_config_path())

    resolved = _resolve_run_config("codex", None)

    assert resolved.harness == "codex"
    assert resolved.harness_source == "cli"
    assert resolved.model == "saved-model"
    assert resolved.model_source == "config"


def test_resolve_run_config_prefers_cli_model_over_saved_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    save_wrapper_config(WrapperConfig("codex", "saved-model"), default_config_path())

    resolved = _resolve_run_config(None, "gpt-5.4-mini")

    assert resolved.harness == "codex"
    assert resolved.harness_source == "config"
    assert resolved.model == "gpt-5.4-mini"
    assert resolved.model_source == "cli"


def test_resolve_run_config_auto_detects_single_installed_harness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr("dds.wrap.detect_installed_harnesses", lambda: {"codex": "/bin/codex"})

    resolved = _resolve_run_config(None, None)

    assert resolved.harness == "codex"
    assert resolved.harness_source == "auto"
    assert resolved.model is None


def test_resolve_run_config_runs_inline_setup_for_tty_first_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(
        "dds.wrap.detect_installed_harnesses",
        lambda: {"claude": "/bin/claude", "codex": "/bin/codex"},
    )
    monkeypatch.setattr("dds.wrap._stdin_is_tty", lambda: True)
    monkeypatch.setattr(
        "dds.wrap._run_setup_flow",
        lambda *, existing_config, config_path: WrapperConfig("codex", "gpt-5.4"),
    )

    resolved = _resolve_run_config(None, None)

    assert resolved.harness == "codex"
    assert resolved.harness_source == "config"
    assert resolved.model == "gpt-5.4"
    output = capsys.readouterr().out
    assert "Running first-time setup before `dds wrap --run`." in output


def test_resolve_run_config_fails_interactive_when_no_harnesses_found(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr("dds.wrap.detect_installed_harnesses", lambda: {})
    monkeypatch.setattr("dds.wrap._stdin_is_tty", lambda: True)

    with pytest.raises(HarnessResolutionError, match="no supported harness CLI was found on PATH"):
        _resolve_run_config(None, None)

    output = capsys.readouterr().out
    assert "Running first-time setup before `dds wrap --run`." not in output


def test_resolve_run_config_fails_non_interactive_when_multiple_harnesses_found(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(
        "dds.wrap.detect_installed_harnesses",
        lambda: {"claude": "/bin/claude", "codex": "/bin/codex"},
    )
    monkeypatch.setattr("dds.wrap._stdin_is_tty", lambda: False)

    with pytest.raises(HarnessResolutionError, match="Run `dds init` to save a default harness"):
        _resolve_run_config(None, None)


def test_resolve_run_config_fails_non_interactive_when_no_harnesses_found(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr("dds.wrap.detect_installed_harnesses", lambda: {})
    monkeypatch.setattr("dds.wrap._stdin_is_tty", lambda: False)

    with pytest.raises(HarnessResolutionError, match="no supported harness CLI was found on PATH"):
        _resolve_run_config(None, None)


def test_run_init_requires_tty(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("dds.wrap._stdin_is_tty", lambda: False)

    with pytest.raises(SystemExit, match="1"):
        run_init()

    assert "`dds init` requires an interactive terminal" in capsys.readouterr().err


def test_cli_help_includes_init_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--help"])

    assert "init" in capsys.readouterr().out
