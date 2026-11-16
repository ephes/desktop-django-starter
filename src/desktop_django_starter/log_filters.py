"""Logging filters for the desktop runtime."""

from __future__ import annotations

import logging
import re
from urllib.parse import unquote, unquote_plus, urlsplit

BOOTSTRAP_PATH = "/desktop-auth/bootstrap/"
# http.server request targets contain no whitespace, and Django's QUERY_STRING
# runs to the end of the target: "#" and quotes are not query delimiters there.
_QUERY_URL = re.compile(r"(/[^\s\"'?#]*\?)(\S*)")


def _redact_query(match: re.Match[str]) -> str:
    prefix, query = match.groups()
    raw_path = prefix[:-1]
    # http.server routes a leading "//" as "/" (gh-87389), so compare the
    # normalized path too; urlsplit would read "//desktop-auth" as a netloc.
    paths = {"/" + unquote(raw_path).lstrip("/")}
    try:
        paths.add(unquote(urlsplit(raw_path).path))
    except ValueError:
        pass
    if BOOTSTRAP_PATH not in paths:
        return match.group()
    # Keep a closing quote of a quoted request line outside the query.
    stripped = query.rstrip("\"'")
    query, closing = stripped, query[len(stripped) :]
    members = []
    for member in query.split("&"):
        key = member.partition("=")[0]
        # Match Django's QueryDict decoding and redact all duplicates, including
        # those ignored by GET.get(), without re-encoding safe URL structure.
        if unquote_plus(key) == "token":
            member = key + "=[redacted]"
        members.append(member)
    return prefix + "&".join(members) + closing


class RedactDesktopAuthToken(logging.Filter):
    """Hide the session token in request-log lines for the auth bootstrap URL.

    Tauri and Positron open their web views at
    `/desktop-auth/bootstrap/?token=...`, and Django's development-server
    request log would otherwise write the live session token to stderr.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Format first so tuple/mapping placeholders inside the URL cannot
        # reintroduce a credential after redaction or lose their placeholder.
        try:
            message = record.getMessage()
        except Exception:
            # A malformed record must not raise at the logging call site, and
            # handleError would print its raw arguments. Keep only the
            # redacted template.
            message = str(record.msg)
        record.msg = _QUERY_URL.sub(_redact_query, message)
        record.args = ()
        return True
