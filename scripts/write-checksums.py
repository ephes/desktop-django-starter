#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import hashlib
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

    args.output.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{sha256_digest(path)}  {path.name}" for path in matches]
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {args.output} for {len(matches)} artifact(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
