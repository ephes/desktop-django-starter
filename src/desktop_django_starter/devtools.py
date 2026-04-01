from __future__ import annotations

import csv
import io
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

try:
    from rich.console import Console
    from rich.table import Table
except ImportError:  # pragma: no cover - exercised only when rich is unavailable
    Console = None
    Table = None

EXCLUDED_LANGUAGES = "JSON,Markdown"
FALLBACK_LANGUAGE_BY_NAME = {
    "Justfile": "Justfile",
    "justfile": "Justfile",
}
FALLBACK_LANGUAGE_BY_SUFFIX = {
    ".bat": "DOS Batch",
    ".cjs": "JavaScript",
    ".cmd": "DOS Batch",
    ".css": "CSS",
    ".html": "HTML",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".py": "Python",
    ".toml": "TOML",
    ".xml": "XML",
    ".yaml": "YAML",
    ".yml": "YAML",
}
FALLBACK_EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".stage",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "docs/_build",
    "positron",
    "shells/electron/dist",
    "shells/electron/node_modules",
    "shells/tauri/node_modules",
    "shells/tauri/src-tauri/target",
    "tauri",
    "node_modules",
}


def count_lines_of_code() -> int:
    if shutil.which("cloc"):
        return _count_with_cloc()

    print("cloc not found, using Python fallback.", file=sys.stderr)
    return _count_with_python()


def _count_with_cloc() -> int:
    summary_cmd = [
        "cloc",
        ".",
        "--vcs=git",
        f"--exclude-lang={EXCLUDED_LANGUAGES}",
        "--csv",
        "--quiet",
    ]
    detail_cmd = [
        "cloc",
        ".",
        "--vcs=git",
        f"--exclude-lang={EXCLUDED_LANGUAGES}",
        "--by-file",
        "--csv",
        "--quiet",
    ]

    summary_output = _run_cloc(summary_cmd)
    detail_output = _run_cloc(detail_cmd)
    summary_info = _parse_cloc_summary_csv(summary_output)
    directory_stats = _aggregate_cloc_csv(detail_output)

    if Console is not None:
        console = Console()
        console.print("[blue]Overall Summary:[/blue]")
        if summary_info["metadata"]:
            console.print(f"[dim]{summary_info['metadata']}[/dim]")
        _print_rich_cloc_summary_table(console, summary_info["rows"])
        console.print()
        _print_rich_directory_table(console, directory_stats)
        console.print("[green]Lines of code counted successfully with cloc![/green]")
    else:
        print("Overall Summary:")
        if summary_info["metadata"]:
            print(summary_info["metadata"])
        print(_render_cloc_summary_table(summary_info["rows"]))
        print()
        print(_render_directory_table(directory_stats))
        print("Lines of code counted successfully with cloc!")
    return 0


def _run_cloc(command: list[str]) -> str:
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip()
        if stderr:
            print(stderr, file=sys.stderr)
        raise SystemExit(exc.returncode) from exc
    return result.stdout


def _aggregate_cloc_csv(csv_output: str) -> dict[str, dict[str, int]]:
    directory_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "lines": 0})
    reader = csv.DictReader(io.StringIO(csv_output))

    for row in reader:
        file_path = row.get("filename", "").strip()
        if not file_path or file_path == "SUM":
            continue

        try:
            line_count = int(row["code"])
        except (KeyError, TypeError, ValueError):
            continue

        bucket = bucket_for_path(file_path)
        directory_stats[bucket]["files"] += 1
        directory_stats[bucket]["lines"] += line_count

    return dict(directory_stats)


def _parse_cloc_summary_csv(csv_output: str) -> dict[str, str | list[dict[str, int | str]]]:
    reader = csv.DictReader(io.StringIO(csv_output))
    metadata = ""
    if reader.fieldnames and len(reader.fieldnames) > 5:
        metadata = reader.fieldnames[5]

    rows: list[dict[str, int | str]] = []
    for row in reader:
        language = row.get("language", "").strip()
        if not language:
            continue
        try:
            rows.append(
                {
                    "language": language,
                    "files": int(row["files"]),
                    "blank": int(row["blank"]),
                    "comment": int(row["comment"]),
                    "code": int(row["code"]),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue

    return {"metadata": metadata, "rows": rows}


def _count_with_python() -> int:
    language_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "lines": 0})
    directory_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "lines": 0})

    for path in _iter_fallback_files(Path.cwd()):
        language = _fallback_language_for_path(path)
        if language is None:
            continue

        try:
            with path.open(encoding="utf-8", errors="ignore") as handle:
                line_count = sum(1 for _ in handle)
        except OSError as exc:
            print(f"Warning: could not read {path}: {exc}", file=sys.stderr)
            continue

        language_stats[language]["files"] += 1
        language_stats[language]["lines"] += line_count

        bucket = bucket_for_path(path.relative_to(Path.cwd()))
        directory_stats[bucket]["files"] += 1
        directory_stats[bucket]["lines"] += line_count

    if Console is not None:
        console = Console()
        console.print("[blue]Overall Summary:[/blue]")
        _print_rich_summary_table(console, dict(language_stats))
        console.print()
        _print_rich_directory_table(console, dict(directory_stats))
        console.print("[green]Lines of code counted successfully with Python![/green]")
    else:
        print("Overall Summary:")
        print(_render_language_summary(language_stats))
        print()
        print(_render_directory_table(dict(directory_stats)))
        print("Lines of code counted successfully with Python!")
    return 0


def _iter_fallback_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(_is_excluded_dir(partial) for partial in _path_prefixes(path.relative_to(root))):
            continue
        yield path


def _path_prefixes(path: Path) -> list[str]:
    prefixes: list[str] = []
    parts = list(path.parts)
    for index in range(1, len(parts)):
        prefixes.append("/".join(parts[:index]))
    return prefixes


def _is_excluded_dir(path_fragment: str) -> bool:
    return path_fragment in FALLBACK_EXCLUDED_DIRS


def _fallback_language_for_path(path: Path) -> str | None:
    if path.name in FALLBACK_LANGUAGE_BY_NAME:
        return FALLBACK_LANGUAGE_BY_NAME[path.name]
    return FALLBACK_LANGUAGE_BY_SUFFIX.get(path.suffix.lower())


def bucket_for_path(path: str | Path) -> str:
    path_obj = Path(path)
    parts = [part for part in path_obj.parts if part not in {".", ""}]
    if not parts:
        return "."
    if len(parts) == 1:
        return "."
    if parts[0] == "src" and len(parts) >= 2:
        return f"src/{parts[1]}"
    if parts[0] == "tests":
        return f"tests/{parts[1]}" if len(parts) >= 3 else "tests"
    return parts[0]


def _render_language_summary(language_stats: dict[str, dict[str, int]]) -> str:
    rows = []
    total_files = 0
    total_lines = 0

    sorted_languages = sorted(
        language_stats.items(),
        key=lambda item: item[1]["lines"],
        reverse=True,
    )
    for language, stats in sorted_languages:
        rows.append((language, str(stats["files"]), str(stats["lines"])))
        total_files += stats["files"]
        total_lines += stats["lines"]

    rows.append(("SUM", str(total_files), str(total_lines)))
    return _render_table("Language", rows)


def _render_cloc_summary_table(rows: list[dict[str, int | str]]) -> str:
    rendered_rows = [
        (
            str(row["language"]),
            str(row["files"]),
            str(row["blank"]),
            str(row["comment"]),
            str(row["code"]),
        )
        for row in rows
    ]
    return _render_table(
        "Language",
        rendered_rows,
        headers=("Language", "Files", "Blank", "Comment", "Code"),
    )


def _render_directory_table(directory_stats: dict[str, dict[str, int]]) -> str:
    rows = [
        (directory, str(stats["files"]), str(stats["lines"]))
        for directory, stats in sorted(
            directory_stats.items(),
            key=lambda item: item[1]["lines"],
            reverse=True,
        )
    ]
    return _render_table("Directory", rows, title="Lines of Code by Directory")


def _print_rich_summary_table(
    console: Console,
    language_stats: dict[str, dict[str, int]],
) -> None:
    table = Table()
    table.add_column("Language", style="cyan", no_wrap=True)
    table.add_column("Files", justify="right", style="magenta")
    table.add_column("Lines", justify="right", style="green")

    total_files = 0
    total_lines = 0
    sorted_languages = sorted(
        language_stats.items(),
        key=lambda item: item[1]["lines"],
        reverse=True,
    )
    for language, stats in sorted_languages:
        table.add_row(language, str(stats["files"]), str(stats["lines"]))
        total_files += stats["files"]
        total_lines += stats["lines"]

    table.add_section()
    table.add_row("SUM", str(total_files), str(total_lines))
    console.print(table)


def _print_rich_cloc_summary_table(
    console: Console,
    rows: list[dict[str, int | str]],
) -> None:
    table = Table(padding=(0, 1))
    table.add_column("Language", style="cyan", no_wrap=True)
    table.add_column("Files", justify="right", style="magenta")
    table.add_column("Blank", justify="right")
    table.add_column("Comment", justify="right")
    table.add_column("Code", justify="right", style="green")

    for row in rows:
        if row["language"] == "SUM":
            table.add_section()
        table.add_row(
            str(row["language"]),
            str(row["files"]),
            str(row["blank"]),
            str(row["comment"]),
            str(row["code"]),
        )

    console.print(table)


def _print_rich_directory_table(
    console: Console,
    directory_stats: dict[str, dict[str, int]],
) -> None:
    table = Table(title="Lines of Code by Directory", padding=(0, 1))
    table.add_column("Directory", style="cyan", no_wrap=True)
    table.add_column("Files", justify="right", style="magenta")
    table.add_column("Lines", justify="right", style="green")

    sorted_dirs = sorted(
        directory_stats.items(),
        key=lambda item: item[1]["lines"],
        reverse=True,
    )
    for directory, stats in sorted_dirs:
        table.add_row(directory, str(stats["files"]), str(stats["lines"]))

    console.print(table)


def _render_table(
    first_column: str,
    rows: list[tuple[str, ...]],
    title: str | None = None,
    headers: tuple[str, ...] | None = None,
) -> str:
    headers = headers or (first_column, "Files", "Lines")
    widths = [
        max(len(header), *(len(row[index]) for row in rows))
        for index, header in enumerate(headers)
    ]

    border = "+-" + "-+-".join("-" * width for width in widths) + "-+"
    header_cells = []
    for index, header in enumerate(headers):
        if index == 0:
            header_cells.append(header.ljust(widths[index]))
        else:
            header_cells.append(header.rjust(widths[index]))
    header = "| " + " | ".join(header_cells) + " |"

    output = []
    if title:
        output.append(title)
    output.append(border)
    output.append(header)
    output.append(border)
    for row in rows:
        cells = []
        for index, value in enumerate(row):
            if index == 0:
                cells.append(value.ljust(widths[index]))
            else:
                cells.append(value.rjust(widths[index]))
        output.append("| " + " | ".join(cells) + " |")
    output.append(border)
    return "\n".join(output)
