#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import hashlib
import os
import stat
import tempfile
from pathlib import Path


def sha256_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
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
        help="Artifact glob to include in the checksum manifest.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to the checksum manifest to write.",
    )
    return parser.parse_args()


def resolve_matches(patterns: list[str]) -> list[Path]:
    matches: list[Path] = []
    seen: set[Path] = set()
    for pattern in patterns:
        for match in sorted(Path(path) for path in glob.glob(pattern)):
            resolved = match.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            matches.append(match)
    return matches


def main() -> int:
    args = parse_args()
    matches = resolve_matches(args.patterns)
    if not matches:
        raise SystemExit(f"No artifacts matched: {', '.join(args.patterns)}")

    names: set[str] = set()
    for path in matches:
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
    lines = [f"{sha256_digest(path)}  {path.name}" for path in matches]
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write("\n".join(lines) + "\n")
        temporary.chmod(mode)
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print(f"Wrote {args.output} for {len(matches)} artifact(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
