"""Preflight checks, prompt generation, and agent invocation for wrapping."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

from dds import __version__

ASSETS_PATH = Path(str(files("dds") / "_assets"))
PROMPT_TEMPLATE = ASSETS_PATH / "skills" / "wrap-existing-django-in-electron" / "prompt.md"
SKILL_PATH = ASSETS_PATH / "skills" / "wrap-existing-django-in-electron" / "SKILL.md"

# The token in prompt.md that references the starter repo.  The CLI replaces
# it with the absolute path to the installed assets so the agent can read files.
_STARTER_TOKEN = "../desktop-django-starter"


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
        dirnames[:] = [
            d for d in dirnames
            if d not in exclude and not d.startswith(".")
        ]
        if "manage.py" in filenames:
            results.append(os.path.join(dirpath, "manage.py"))
    results.sort()
    return results


def _shell_quote(s: str) -> str:
    """Quote a string for safe shell copy-paste display."""
    if re.search(r"[^A-Za-z0-9_./:=@-]", s):
        return "'" + s.replace("'", "'\\''") + "'"
    return s


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
    agent: str,
    force: bool,
    emit_prompt: bool,
) -> None:
    # --emit-prompt: just output the resolved prompt and exit
    if emit_prompt:
        print(_generate_prompt())
        return

    pf = _Preflight()
    print("Preflight")
    print(f"  dds {__version__}")
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
    if run_agent:
        if not shutil.which(agent):
            pf.error(f"{agent} not found on PATH")
        else:
            pf.ok(f"{agent} found")

    # Verdict
    print()
    if not pf.passed:
        print(f"Preflight failed ({pf.errors} error(s)).")
        sys.exit(1)
    print("Preflight passed.")

    # --- Run or print ---
    if run_agent:
        resolved_prompt = _generate_prompt()
        assets_str = str(ASSETS_PATH)

        if agent == "claude":
            os.execvp(
                "claude",
                [
                    "claude",
                    "--dangerously-skip-permissions",
                    "-p",
                    resolved_prompt,
                    "--add-dir",
                    assets_str,
                ],
            )
        elif agent == "pi":
            # pi doesn't support --add-dir; absolute paths in prompt are sufficient
            os.execvp(
                "pi",
                [
                    "pi",
                    "--model",
                    "openai-codex/gpt-5.4",
                    "--thinking",
                    "high",
                    "-p",
                    resolved_prompt,
                ],
            )
        elif agent == "codex":
            os.execvp(
                "codex",
                [
                    "codex",
                    "exec",
                    "--dangerously-bypass-approvals-and-sandbox",
                    "--add-dir",
                    assets_str,
                    resolved_prompt,
                ],
            )
    else:
        print()
        print("To wrap this project:")
        print()
        print("  dds wrap --run")
        print()
        print("With a different agent:")
        print()
        print("  dds wrap --run --agent pi")
        print("  dds wrap --run --agent codex")
        print()
        print("Or generate the resolved prompt for manual use:")
        print()
        print("  dds wrap --emit-prompt")
