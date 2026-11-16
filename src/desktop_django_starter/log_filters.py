"""Logging filters for the desktop runtime."""

from __future__ import annotations

import logging
import re
from urllib.parse import unquote, unquote_plus, urlsplit

_QUERY_URL = re.compile(r"(/[^\s\"'?#]*\?)([^\s\"'#]*)")


def _redact_query(match: re.Match[str]) -> str:
    prefix, query = match.groups()
    try:
        path = unquote(urlsplit(prefix).path)
    except ValueError:
        return match.group()
    if path != "/desktop-auth/bootstrap/":
        return match.group()
    members = []
    for member in query.split("&"):
        key = member.partition("=")[0]
        # Match Django's QueryDict decoding and redact all duplicates, including
        # those ignored by GET.get(), without re-encoding safe URL structure.
        if unquote_plus(key) == "token":
            member = key + "=[redacted]"
        members.append(member)
    return prefix + "&".join(members)


class RedactDesktopAuthToken(logging.Filter):
    """Hide the session token in request-log lines for the auth bootstrap URL.

    Tauri and Positron open their web views at
    `/desktop-auth/bootstrap/?token=...`, and Django's development-server
    request log would otherwise write the live session token to stderr.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Format first so tuple/mapping placeholders inside the URL cannot
        # reintroduce a credential after redaction or lose their placeholder.
        record.msg = _QUERY_URL.sub(_redact_query, record.getMessage())
        record.args = ()
        return True
