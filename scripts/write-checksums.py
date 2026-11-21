#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import hashlib
import os
import stat
import sys
import tempfile
from contextlib import suppress
from pathlib import Path


def artifact_generation(info: os.stat_result) -> tuple[int, ...]:
    # Windows pathname stat and descriptor stat can report different ctimes.
    timestamp = info.st_birthtime_ns if os.name == "nt" else info.st_ctime_ns
    return (
        stat.S_IFMT(info.st_mode),
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        timestamp,
    )


def verify_artifact(path: Path, expected: os.stat_result) -> None:
    try:
        current = path.stat()
    except (FileNotFoundError, NotADirectoryError) as error:
        raise SystemExit(f"Artifact changed: {path}") from error
    if artifact_generation(current) != artifact_generation(expected):
        raise SystemExit(f"Artifact changed: {path}")


def open_artifact(path: str, flags: int) -> int:
    return os.open(path, flags | getattr(os, "O_NONBLOCK", 0))


def sha256_digest(path: Path, expected: os.stat_result) -> str:
    digest = hashlib.sha256()
    with open(path, "rb", buffering=0, opener=open_artifact) as handle:
        before = os.fstat(handle.fileno())
        if artifact_generation(before) != artifact_generation(expected):
            raise SystemExit(f"Artifact changed: {path}")
        remaining = before.st_size
        while remaining:
            chunk = handle.read(min(remaining, 1024 * 1024))
            if not chunk:
                raise SystemExit(f"Artifact changed: {path}")
            digest.update(chunk)
            remaining -= len(chunk)
        after = os.fstat(handle.fileno())
        if (
            artifact_generation(after) != artifact_generation(before)
            or after.st_ctime_ns != before.st_ctime_ns
        ):
            raise SystemExit(f"Artifact changed: {path}")
        verify_artifact(path, expected)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write a SHA-256 manifest for one platform artifact set."
    )
    parser.add_argument(
        "--glob",
        action="append",
        dest="patterns",
        required=True,
        help="Required artifact glob; must match at least one regular file.",
    )
    parser.add_argument(
        "--optional-glob",
        action="append",
        dest="optional_patterns",
        default=[],
        help="Include matching regular files when present, for example optional signatures.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to the checksum manifest to write.",
    )
    return parser.parse_args()


def resolve_matches(
    patterns: list[str], optional_patterns: list[str]
) -> list[tuple[Path, os.stat_result]]:
    matches: list[tuple[Path, os.stat_result]] = []
    seen: set[Path] = set()
    missing_patterns: list[str] = []
    for pattern in [*patterns, *optional_patterns]:
        found = False
        for match in sorted(map(Path, glob.glob(pattern))):
            if not match.is_file():
                continue
            info = match.stat()
            if not stat.S_ISREG(info.st_mode):
                raise SystemExit(f"Artifact changed: {match}")
            found = True
            resolved = match.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            matches.append((match, info))
        if not found and pattern in patterns:
            missing_patterns.append(pattern)
    if missing_patterns:
        raise SystemExit(f"No artifacts matched required pattern(s): {', '.join(missing_patterns)}")
    return matches


def main() -> int:
    args = parse_args()
    matches = resolve_matches(args.patterns, args.optional_patterns)
    if not matches:
        raise SystemExit(f"No artifacts matched: {', '.join(args.patterns)}")

    names: set[str] = set()
    for path, _ in matches:
        if path.resolve() == args.output.resolve() or (
            args.output.exists() and path.samefile(args.output)
        ):
            raise SystemExit(f"Manifest output is also an input: {path}")
        if path.name in names:
            raise SystemExit(f"Ambiguous artifact basename: {path.name}")
        if "\n" in path.name or "\r" in path.name or "\\" in path.name:
            raise SystemExit(f"Unsupported artifact basename: {path.name!r}")
        names.add(path.name)

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        mode = stat.S_IMODE(output.stat().st_mode)
    else:
        creation_mask = os.umask(0)
        os.umask(creation_mask)
        mode = 0o666 & ~creation_mask
    lines = [f"{sha256_digest(path, info)}  {path.name}" for path, info in matches]
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write("\n".join(lines) + "\n")
        temporary.chmod(mode)
        for path, info in matches:
            verify_artifact(path, info)
        os.replace(temporary, output)
    except BaseException:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                with suppress(OSError, ValueError):
                    print(
                        f"Could not remove checksum staging file {temporary.name!r}.",
                        file=sys.stderr,
                    )
        raise
    print(f"Wrote {args.output} for {len(matches)} artifact(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
