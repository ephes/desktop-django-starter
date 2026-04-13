"""Preflight checks, prompt generation, and agent invocation for wrapping."""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from dds import __version__
from dds.config import (
    SUPPORTED_HARNESSES,
    ConfigError,
    WrapperConfig,
    default_config_path,
    detect_installed_harnesses,
    load_wrapper_config,
    save_wrapper_config,
)

ASSETS_PATH = Path(str(files("dds") / "_assets"))
PROMPT_TEMPLATE = ASSETS_PATH / "skills" / "wrap-existing-django-in-electron" / "prompt.md"
SKILL_PATH = ASSETS_PATH / "skills" / "wrap-existing-django-in-electron" / "SKILL.md"

# The token in prompt.md that references the starter repo.  The CLI replaces
# it with the absolute path to the installed assets so the agent can read files.
_STARTER_TOKEN = "../desktop-django-starter"
DEFAULT_PI_MODEL = "openai-codex/gpt-5.4"


def _summarize_claude_tool_use(content: dict[str, object]) -> str | None:
    """Return a compact, human-readable description for a Claude tool call."""
    name = content.get("name")
    if not isinstance(name, str):
        return None

    raw_input = content.get("input")
    input_data = raw_input if isinstance(raw_input, dict) else {}
    target = input_data.get("file_path") or input_data.get("path") or input_data.get("pattern")

    if isinstance(target, str) and target.strip():
        first_line = target.strip().splitlines()[0]
        if len(first_line) > 160:
            first_line = f"{first_line[:157]}..."
        return f"claude tool: {name} {first_line}"

    return f"claude tool: {name}"


def _terminate_claude_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return

    if os.name == "nt":
        process.terminate()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except OSError:
            process.terminate()

    try:
        process.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass

    if os.name == "nt":
        process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        except OSError:
            process.kill()
    process.wait()


def _format_claude_stream_event(line: str) -> list[str]:
    """Format one Claude stream-json event into concise progress lines."""
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        stripped = line.strip()
        return [stripped] if stripped else []

    event_type = event.get("type")
    if event_type == "system" and event.get("subtype") == "init":
        session_id = event.get("session_id")
        model = event.get("model")
        if session_id and model:
            return [f"claude session: {session_id} ({model})"]
        return []

    if event_type == "assistant":
        message = event.get("message")
        if not isinstance(message, dict):
            return []

        lines = []
        content_items = message.get("content")
        if not isinstance(content_items, list):
            return []

        for content in content_items:
            if not isinstance(content, dict):
                continue
            content_type = content.get("type")
            if content_type == "text":
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    lines.append(text.strip())
            elif content_type == "tool_use":
                summary = _summarize_claude_tool_use(content)
                if summary:
                    lines.append(summary)
        return lines

    if event_type == "user":
        message = event.get("message")
        if not isinstance(message, dict):
            return []
        content_items = message.get("content")
        if not isinstance(content_items, list):
            return []

        lines = []
        for content in content_items:
            if (
                isinstance(content, dict)
                and content.get("type") == "tool_result"
                and content.get("is_error") is True
            ):
                result = content.get("content", "")
                result_text = str(result).strip().splitlines()[0] if result else "unknown error"
                lines.append(f"claude tool error: {result_text}")
        return lines

    if event_type == "result":
        if event.get("is_error"):
            error = event.get("subtype") or event.get("stop_reason") or "unknown error"
            return [f"claude failed: {error}"]

        duration_ms = event.get("duration_ms")
        if isinstance(duration_ms, int):
            return [f"claude finished in {duration_ms / 1000:.1f}s"]
        return ["claude finished"]

    return []


def _claude_command(resolved_prompt: str, assets_str: str, model: str | None) -> list[str]:
    command = [
        "claude",
        "--dangerously-skip-permissions",
        "-p",
        resolved_prompt,
        "--add-dir",
        assets_str,
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    if model:
        command.extend(["--model", model])
    return command


def _pi_command(resolved_prompt: str, model: str | None) -> list[str]:
    return [
        "pi",
        "--model",
        model or DEFAULT_PI_MODEL,
        "--thinking",
        "high",
        "-p",
        resolved_prompt,
    ]


def _codex_command(resolved_prompt: str, assets_str: str, model: str | None) -> list[str]:
    command = [
        "codex",
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "--add-dir",
        assets_str,
    ]
    if model:
        command.extend(["--model", model])
    command.append(resolved_prompt)
    return command


def _run_claude(resolved_prompt: str, assets_str: str, model: str | None) -> None:
    """Run Claude with streaming progress and exit with Claude's return code."""
    command = _claude_command(resolved_prompt, assets_str, model)

    print("Starting Claude. Progress will stream below.")
    with subprocess.Popen(  # noqa: S603
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        start_new_session=os.name != "nt",
        text=True,
    ) as process:
        if process.stdout is None:
            raise RuntimeError("Claude stdout pipe was not created.")
        try:
            for line in process.stdout:
                for formatted in _format_claude_stream_event(line):
                    print(formatted, flush=True)
        except KeyboardInterrupt:
            _terminate_claude_process(process)
            raise

        returncode = process.wait()

    if returncode != 0:
        sys.exit(returncode)


def _generate_prompt() -> str:
    """Read prompt.md and resolve starter-repo paths to the installed assets."""
    template = PROMPT_TEMPLATE.read_text()
    # Escape sed-special characters in the replacement path
    assets_str = str(ASSETS_PATH)
    resolved = template.replace(_STARTER_TOKEN, assets_str)

    # Defensive: fail if any expected starter-path references remain
    if _STARTER_TOKEN in resolved:
        print("error: unresolved starter-path references remain in prompt", file=sys.stderr)
        sys.exit(1)

    return resolved


def _find_manage_py() -> list[str]:
    """Find manage.py files, excluding venvs and hidden dirs."""
    results = []
    exclude = {".git", ".venv", "venv", "env", "node_modules", "__pycache__"}
    for dirpath, dirnames, filenames in os.walk("."):
        # Prune excluded directories in-place
        dirnames[:] = [d for d in dirnames if d not in exclude and not d.startswith(".")]
        if "manage.py" in filenames:
            results.append(os.path.join(dirpath, "manage.py"))
    results.sort()
    return results


def _shell_quote(s: str) -> str:
    """Quote a string for safe shell copy-paste display."""
    if re.search(r"[^A-Za-z0-9_./:=@-]", s):
        return "'" + s.replace("'", "'\\''") + "'"
    return s


class HarnessResolutionError(RuntimeError):
    """Raised when the run harness cannot be resolved safely."""


@dataclass(frozen=True)
class _ResolvedRunConfig:
    harness: str
    model: str | None
    harness_source: str
    model_source: str | None
    config_path: Path


def _stdin_is_tty() -> bool:
    return bool(getattr(sys.stdin, "isatty", lambda: False)())


def _model_prompt_hint(harness: str) -> str:
    if harness == "pi":
        return f" for example {DEFAULT_PI_MODEL}"
    if harness == "codex":
        return " for example gpt-5.4"
    return ""


def _prompt_for_harness(options: list[str], default: str) -> str:
    while True:
        answer = input(f"Default harness [{default}]: ").strip()
        if not answer:
            return default
        if answer in options:
            return answer
        if answer.isdigit():
            index = int(answer) - 1
            if 0 <= index < len(options):
                return options[index]
        supported = ", ".join(options)
        print(f"Please enter one of: {supported}, or the matching number.")


def _prompt_for_model(current_model: str | None, harness: str) -> str | None:
    current = current_model or ""
    if current:
        prompt = (
            "Default model (optional; press Enter to keep current, '-' to clear"
            f"{_model_prompt_hint(harness)}) [{current}]: "
        )
    else:
        prompt = (
            "Default model (optional; press Enter to use the harness default"
            f"{_model_prompt_hint(harness)}): "
        )

    answer = input(prompt).strip()
    if not answer:
        return current_model
    if answer == "-":
        return None
    return answer


def _run_setup_flow(*, existing_config: WrapperConfig | None, config_path: Path) -> WrapperConfig:
    installed = detect_installed_harnesses()
    if not installed:
        supported = ", ".join(SUPPORTED_HARNESSES)
        raise HarnessResolutionError(
            "No supported harness CLI was found on PATH. "
            f"Install one of: {supported}, then run `dds init`."
        )

    print("Wrapper setup")
    print(f"  config: {config_path}")
    print("  detected harnesses:")
    for harness, resolved_path in installed.items():
        print(f"    - {harness}: {resolved_path}")
    print()
    print("Choose the default harness for `dds wrap --run`.")
    options = list(installed)
    default = (
        existing_config.harness
        if existing_config and existing_config.harness in installed
        else options[0]
    )
    for index, harness in enumerate(options, start=1):
        marker = " (current)" if harness == default else ""
        print(f"  {index}. {harness}{marker}")

    harness = _prompt_for_harness(options, default)
    model = _prompt_for_model(existing_config.model if existing_config else None, harness)
    config = WrapperConfig(harness=harness, model=model)
    saved_path = save_wrapper_config(config, config_path)

    print()
    print(f"Saved wrapper defaults to {saved_path}")
    if config.model:
        print(f"Default model: {config.model}")
    else:
        print("Default model: use each harness CLI default")
    print()
    return config


def _describe_harness_source(resolved: _ResolvedRunConfig) -> str:
    if resolved.harness_source == "cli":
        return "CLI override"
    if resolved.harness_source == "config":
        return f"saved default ({resolved.config_path})"
    if resolved.harness_source == "auto":
        return "auto-detected"
    return resolved.harness_source


def _describe_model_source(resolved: _ResolvedRunConfig) -> str:
    if resolved.model_source == "cli":
        return "CLI override"
    if resolved.model_source == "config":
        return f"saved default ({resolved.config_path})"
    if resolved.model_source is None:
        return "harness default"
    return resolved.model_source


def _resolve_run_config(agent: str | None, model: str | None) -> _ResolvedRunConfig:
    config_path = default_config_path()
    try:
        saved_config = load_wrapper_config(config_path)
    except ConfigError as exc:
        raise HarnessResolutionError(
            f"Wrapper config is invalid: {exc}. Run `dds init` to rewrite it."
        ) from exc

    resolved_model = model if model is not None else saved_config.model if saved_config else None
    model_source = (
        "cli" if model is not None else "config" if saved_config and saved_config.model else None
    )

    if agent is not None:
        return _ResolvedRunConfig(
            harness=agent,
            model=resolved_model,
            harness_source="cli",
            model_source=model_source,
            config_path=config_path,
        )

    if saved_config is not None:
        return _ResolvedRunConfig(
            harness=saved_config.harness,
            model=resolved_model,
            harness_source="config",
            model_source=model_source,
            config_path=config_path,
        )

    installed = detect_installed_harnesses()
    if len(installed) == 1:
        harness = next(iter(installed))
        return _ResolvedRunConfig(
            harness=harness,
            model=resolved_model,
            harness_source="auto",
            model_source=model_source,
            config_path=config_path,
        )

    if _stdin_is_tty() and installed:
        print(f"No wrapper defaults found at {config_path}.")
        print("Running first-time setup before `dds wrap --run`.")
        print()
        config = _run_setup_flow(existing_config=None, config_path=config_path)
        return _ResolvedRunConfig(
            harness=config.harness,
            model=resolved_model if model is not None else config.model,
            harness_source="config",
            model_source="cli" if model is not None else "config" if config.model else None,
            config_path=config_path,
        )

    installed_names = ", ".join(installed) if installed else "none"
    if installed:
        raise HarnessResolutionError(
            "No wrapper defaults are configured, and multiple supported harnesses are "
            f"installed on PATH ({installed_names}). Run `dds init` to save a default "
            "harness, or pass `--harness` explicitly."
        )

    supported = ", ".join(SUPPORTED_HARNESSES)
    raise HarnessResolutionError(
        "No wrapper defaults are configured, and no supported harness CLI was found on PATH. "
        f"Install one of: {supported}, then run `dds init` or pass `--harness` explicitly."
    )


class _Preflight:
    """Accumulates preflight results."""

    def __init__(self) -> None:
        self.errors = 0
        self.warnings = 0

    def ok(self, msg: str) -> None:
        print(f"  ok {msg}")

    def warn(self, msg: str) -> None:
        print(f"  ! {msg}")
        self.warnings += 1

    def error(self, msg: str) -> None:
        print(f"  x {msg}", file=sys.stderr)
        self.errors += 1

    @property
    def passed(self) -> bool:
        return self.errors == 0


def run_wrap(
    *,
    run_agent: bool,
    agent: str | None,
    model: str | None,
    force: bool,
    emit_prompt: bool,
) -> None:
    # --emit-prompt: just output the resolved prompt and exit
    if emit_prompt:
        print(_generate_prompt())
        return

    resolved_run: _ResolvedRunConfig | None = None
    if run_agent:
        try:
            resolved_run = _resolve_run_config(agent, model)
        except HarnessResolutionError as exc:
            print(f"error: {exc}", file=sys.stderr)
            sys.exit(1)

    pf = _Preflight()
    print("Preflight")
    print(f"  dds {__version__}")
    if resolved_run is not None:
        print(f"  harness: {resolved_run.harness} ({_describe_harness_source(resolved_run)})")
        if resolved_run.model:
            print(f"  model: {resolved_run.model} ({_describe_model_source(resolved_run)})")
        else:
            print("  model: harness default")
    print()

    # 1. Git repo (hard error, always)
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        capture_output=True,
    )
    if result.returncode != 0:
        pf.error("Not a git repository")
    else:
        pf.ok("Git repository")

    # 2. Assets valid (hard error, always)
    if not SKILL_PATH.is_file():
        pf.error(f"Bundled assets invalid: SKILL.md not found at {SKILL_PATH}")
    else:
        pf.ok(f"Assets: {ASSETS_PATH}")

    # 3. Clean worktree (--force downgrades to warning)
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        if force:
            pf.warn("Working tree has uncommitted changes (--force, continuing)")
        else:
            pf.error("Working tree has uncommitted changes (use --force to override)")
    else:
        pf.ok("Working tree clean")

    # 4. manage.py discovery (at least one)
    manage_files = _find_manage_py()
    if not manage_files:
        pf.error("No manage.py found (is this a Django project?)")
    elif len(manage_files) == 1:
        pf.ok(f"manage.py: {manage_files[0]}")
    else:
        pf.ok("manage.py found (multiple — the agent will inspect):")
        for f in manage_files:
            print(f"       {f}")

    # 5. electron/ doesn't exist (--force downgrades to warning)
    if Path("electron").is_dir():
        if force:
            pf.warn("electron/ already exists (--force, continuing)")
        else:
            pf.error("electron/ already exists (use --force to re-wrap)")
    else:
        pf.ok("No existing electron/ directory")

    # 6. Required CLIs: warning in print mode, hard error with --run
    for cmd in ("node", "npm", "just"):
        if shutil.which(cmd):
            pf.ok(f"{cmd} found")
        elif run_agent:
            pf.error(f"{cmd} not found (required for wrapping and verification)")
        else:
            pf.warn(f"{cmd} not found (required for post-wrap verification)")

    # 7. Agent CLI (hard error only with --run)
    if resolved_run is not None:
        if not shutil.which(resolved_run.harness):
            if resolved_run.harness_source == "config":
                pf.error(
                    f"{resolved_run.harness} not found on PATH "
                    "(saved default from "
                    f"{resolved_run.config_path}; run `dds init` or pass --harness)"
                )
            else:
                pf.error(f"{resolved_run.harness} not found on PATH")
        else:
            pf.ok(f"{resolved_run.harness} found ({_describe_harness_source(resolved_run)})")

    # Verdict
    print()
    if not pf.passed:
        print(f"Preflight failed ({pf.errors} error(s)).")
        sys.exit(1)
    print("Preflight passed.")

    # --- Run or print ---
    if resolved_run is not None:
        resolved_prompt = _generate_prompt()
        assets_str = str(ASSETS_PATH)

        if resolved_run.harness == "claude":
            _run_claude(resolved_prompt, assets_str, resolved_run.model)
        elif resolved_run.harness == "pi":
            # pi doesn't support --add-dir; absolute paths in prompt are sufficient
            os.execvp("pi", _pi_command(resolved_prompt, resolved_run.model))
        elif resolved_run.harness == "codex":
            os.execvp("codex", _codex_command(resolved_prompt, assets_str, resolved_run.model))
    else:
        print()
        print("To wrap this project:")
        print()
        print("  dds init")
        print("  dds wrap --run")
        print()
        print("With a different agent:")
        print()
        print("  dds wrap --run --agent pi")
        print("  dds wrap --run --agent codex")
        print()
        print("With a specific model:")
        print()
        print("  dds wrap --run --harness pi --model openai-codex/gpt-5.4")
        print()
        print("Or generate the resolved prompt for manual use:")
        print()
        print("  dds wrap --emit-prompt")


def run_init() -> None:
    config_path = default_config_path()
    if not _stdin_is_tty():
        print(
            "error: `dds init` requires an interactive terminal. "
            "Run it in a TTY, or pass `--harness` directly to `dds wrap --run`.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        existing_config = load_wrapper_config(config_path)
    except ConfigError as exc:
        print(f"warning: existing wrapper config is invalid: {exc}", file=sys.stderr)
        existing_config = None

    try:
        _run_setup_flow(existing_config=existing_config, config_path=config_path)
    except HarnessResolutionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
