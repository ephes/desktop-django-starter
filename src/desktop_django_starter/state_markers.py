"""Bounded state marker objects with unambiguous JSON member claims."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .state_files import regular_reader


def _unique_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate state marker member")
        result[key] = value
    return result


def read_state_marker(path: Path, *, max_bytes: int) -> dict[str, Any]:
    """Reject duplicate decoded names in every object, including nested objects."""
    with regular_reader(path, stable=True) as stream:
        raw = stream.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("state marker exceeds byte budget")
    marker = json.loads(raw, object_pairs_hook=_unique_members)
    if not isinstance(marker, dict):
        raise ValueError("state marker must be an object")
    return marker
