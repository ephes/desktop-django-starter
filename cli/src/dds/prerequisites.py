"""Local prerequisite checks shared by doctor and wrapper preflight."""

from __future__ import annotations

import os
import re
import subprocess

_NODE_MINIMUM = (22, 12)
_NODE_VERSION_TIMEOUT = 5
# Accept semver pre-release and build suffixes such as nightly or rc builds.
_NODE_VERSION = re.compile(
    rb"v([0-9]{1,10})\.([0-9]{1,10})\.[0-9]{1,10}(?:[-+][0-9A-Za-z.+-]{1,200})?"
)


class NodeVersionError(RuntimeError):
    """The Node version could not be determined or does not meet the minimum."""

    def __init__(self, detail: str) -> None:
        major, minor = _NODE_MINIMUM
        super().__init__(
            f"{detail}. Install Node.js {major}.{minor} or newer and put it first on PATH."
        )


def _in_absolute_path_entry(executable: str) -> bool:
    """Whether the lookup result lies directly in an absolute PATH directory.

    Relative hits come from the current directory (Windows checks it first) or
    from empty or relative PATH entries. They are never run.
    """
    if not os.path.isabs(executable):
        return False
    parent = os.path.normcase(os.path.normpath(os.path.dirname(executable)))
    return any(
        entry and os.path.isabs(entry) and os.path.normcase(os.path.normpath(entry)) == parent
        for entry in os.environ.get("PATH", "").split(os.pathsep)
    )


def probe_node_version(executable: str) -> str:
    """Return the reported version of the selected Node executable if supported."""
    if not _in_absolute_path_entry(executable):
        raise NodeVersionError(
            "node resolves to the current directory or a relative PATH entry and was not run"
        )
    try:
        result = subprocess.run(
            [executable, "--version"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=_NODE_VERSION_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise NodeVersionError("node --version timed out") from exc
    except subprocess.CalledProcessError as exc:
        raise NodeVersionError(f"node --version failed (exit {exc.returncode})") from exc
    except OSError as exc:
        raise NodeVersionError("could not run node --version") from exc

    match = _NODE_VERSION.fullmatch(result.stdout.strip())
    if match is None:
        raise NodeVersionError("node --version returned an unrecognized version")
    version = match[0].decode("ascii")
    if (int(match[1]), int(match[2])) < _NODE_MINIMUM:
        raise NodeVersionError(f"node {version} is too old")
    return version
