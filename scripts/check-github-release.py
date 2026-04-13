#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify that a GitHub release has the full hosted Electron asset set."
    )
    parser.add_argument(
        "tag",
        help="Release tag to inspect, for example v0.1.5.",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Publish the release after verification passes.",
    )
    return parser.parse_args()


def run_gh(*args: str) -> str:
    result = subprocess.run(
        ["gh", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def expected_assets(tag: str) -> list[str]:
    version = tag.removeprefix("v")
    return [
        f"desktop-django-starter-macos-{version}-arm64.dmg",
        f"desktop-django-starter-macos-{version}-arm64.dmg.blockmap",
        f"desktop-django-starter-macos-{version}-arm64.zip",
        f"desktop-django-starter-macos-{version}-arm64.zip.blockmap",
        f"desktop-django-starter-windows-{version}-x64.exe",
        f"desktop-django-starter-windows-{version}-x64.exe.blockmap",
        f"desktop-django-starter-linux-{version}-x86_64.AppImage",
        "latest-mac.yml",
        "latest.yml",
        "latest-linux.yml",
    ]


def main() -> int:
    args = parse_args()
    try:
        release = json.loads(run_gh("release", "view", args.tag, "--json", "isDraft,assets"))
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(exc.stderr)
        return 1
    assets = {asset["name"] for asset in release["assets"]}
    missing = [name for name in expected_assets(args.tag) if name not in assets]

    if missing:
        print(f"Release {args.tag} is missing {len(missing)} expected asset(s):")
        for name in missing:
            print(f"- {name}")
        print("Leave the release as a draft until the asset set is complete.")
        return 1

    print(f"Release {args.tag} has the full hosted Electron asset set.")
    if release["isDraft"]:
        print("The release is still a draft.")
    else:
        print("The release is already published.")

    if args.publish and release["isDraft"]:
        run_gh("release", "edit", args.tag, "--draft=false")
        print(f"Published release {args.tag}.")
    elif args.publish:
        print("Nothing to do: the release was already published.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
