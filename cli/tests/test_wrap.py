from __future__ import annotations

import json

from dds.wrap import _claude_command, _codex_command, _format_claude_stream_event, _pi_command


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
