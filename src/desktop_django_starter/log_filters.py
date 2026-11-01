"""Logging filters for the desktop runtime."""

from __future__ import annotations

import logging
import re

_BOOTSTRAP_TOKEN = re.compile(r"(/desktop-auth/bootstrap/\?(?:[^\s\"]*&)?token=)[^&\s\"]*")


def _redact(value: object) -> object:
    if isinstance(value, str):
        return _BOOTSTRAP_TOKEN.sub(r"\1[redacted]", value)
    return value


class RedactDesktopAuthToken(logging.Filter):
    """Hide the session token in request-log lines for the auth bootstrap URL.

    Tauri and Positron open their web views at
    `/desktop-auth/bootstrap/?token=...`, and Django's development-server
    request log would otherwise write the live session token to stderr.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_redact(arg) for arg in record.args)
        return True
