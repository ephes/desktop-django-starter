"""Entry point for the dds CLI."""

from __future__ import annotations

import argparse
import sys

from dds import __version__


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="dds",
        description="Wrap any Django project in an Electron shell.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    subparsers = parser.add_subparsers(dest="command")

    # --- wrap ---
    wrap_parser = subparsers.add_parser(
        "wrap", help="Wrap the Django project in the current directory"
    )
    wrap_parser.add_argument(
        "--run",
        action="store_true",
        help="Invoke the agent after preflight passes (default: preflight only)",
    )
    wrap_parser.add_argument(
        "--agent",
        default="claude",
        choices=["claude", "pi", "codex"],
        help="Agent to use (default: claude)",
    )
    wrap_parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass dirty-worktree and existing-electron/ checks",
    )
    wrap_parser.add_argument(
        "--emit-prompt",
        action="store_true",
        help="Print the resolved wrapping prompt to stdout and exit",
    )

    # --- doctor ---
    subparsers.add_parser("doctor", help="Check prerequisites for wrapping")

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "wrap":
        from dds.wrap import run_wrap

        run_wrap(
            run_agent=args.run,
            agent=args.agent,
            force=args.force,
            emit_prompt=args.emit_prompt,
        )
    elif args.command == "doctor":
        from dds.doctor import run_doctor

        run_doctor()
