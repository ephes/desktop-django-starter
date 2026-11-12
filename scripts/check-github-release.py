#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys

GH_TIMEOUT_SECONDS = 30
MAX_ERROR_DETAIL = 800


class ReleaseCheckError(Exception):
    pass


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
    try:
        result = subprocess.run(
            ["gh", *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=GH_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise ReleaseCheckError(f"gh timed out after {GH_TIMEOUT_SECONDS} seconds") from None
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip()[:MAX_ERROR_DETAIL]
        raise ReleaseCheckError(f"gh exited {exc.returncode}: {detail}") from None
    except OSError:
        raise ReleaseCheckError(
            "could not launch gh; check its installation and permissions"
        ) from None
    except UnicodeError:
        raise ReleaseCheckError("gh returned invalid UTF-8 output") from None
    return result.stdout


def read_release(tag: str) -> dict:
    try:
        release = json.loads(run_gh("release", "view", tag, "--json", "isDraft,assets"))
    except ValueError:
        raise ReleaseCheckError("gh returned invalid release JSON") from None
    if (
        not isinstance(release, dict)
        or type(release.get("isDraft")) is not bool
        or not isinstance(release.get("assets"), list)
        or any(
            not isinstance(asset, dict)
            or not isinstance(asset.get("name"), str)
            or not asset["name"]
            for asset in release["assets"]
        )
    ):
        raise ReleaseCheckError("gh returned invalid release data")
    return release


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
        release = read_release(args.tag)
    except ReleaseCheckError as exc:
        print(f"Release verification failed: {exc}", file=sys.stderr)
        return 1
    assets = {asset["name"] for asset in release["assets"]}
    missing = [name for name in expected_assets(args.tag) if name not in assets]

    invalid = [
        asset["name"]
        for asset in release["assets"]
        if asset["name"] in expected_assets(args.tag)
        and (type(asset.get("size")) is not int or asset["size"] <= 0)
    ]

    if missing:
        print(f"Release {args.tag} is missing {len(missing)} expected asset(s):")
        for name in missing:
            print(f"- {name}")
    if invalid:
        print(
            f"Release {args.tag} has {len(invalid)} expected asset(s) with empty or invalid size:"
        )
        for name in invalid:
            print(f"- {name}")
    if missing or invalid:
        print("Leave the release as a draft until the asset set is complete and nonempty.")
        return 1

    print(f"Release {args.tag} has the full hosted Electron asset set.")
    if release["isDraft"]:
        print("The release is still a draft.")
    else:
        print("The release is already published.")

    if args.publish and release["isDraft"]:
        try:
            run_gh("release", "edit", args.tag, "--draft=false")
        except ReleaseCheckError as exc:
            print(
                f"Release edit outcome is uncertain: {exc}. "
                "Verify the release state before trying again; no retry was attempted.",
                file=sys.stderr,
            )
            return 1
        print(f"Published release {args.tag}.")
    elif args.publish:
        print("Nothing to do: the release was already published.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
