"""Log the raw accepted URL through each supported logging argument shape."""

import logging

import pytest
from django.test import override_settings

from desktop_django_starter.log_filters import RedactDesktopAuthToken

TOKEN = "synthetic-live-credential"
EARLIER = "synthetic-earlier-credential"


@pytest.mark.parametrize("form", ["message", "tuple", "mapping", "value-tuple", "value-mapping"])
@pytest.mark.parametrize(
    "path,query",
    [
        ("/desktop-auth/bootstrap/", f"%74oken={TOKEN}&next=%2F"),
        ("/desktop-auth/bootstrap/", f"token={EARLIER}&token={TOKEN}&next=%2F"),
        ("/desktop-auth/bootstrap/", f"to%6Ben={EARLIER}&%74oken={TOKEN}&next=%2F"),
        ("/desktop-auth/%62ootstrap/", f"%74oken={TOKEN}&next=%2F"),
        ("//desktop-auth/bootstrap/", f"token={TOKEN}&next=%2F"),
        ("///desktop-auth/%62ootstrap/", f"%74oken={TOKEN}&next=%2F"),
    ],
)
def test_formatted_logs_hide_every_canonical_token_member(client, form, path, query):
    url = f"{path}?{query}"
    # http.server routes a leading "//" as "/"; the request log keeps the raw line.
    with override_settings(DESKTOP_DJANGO_AUTH_TOKEN=TOKEN):
        assert client.get("/" + url.lstrip("/")).status_code == 302
    request_line = f"GET {url} HTTP/1.1"
    if form == "message":
        message, args = f'"{request_line}" 302 0', ()
    elif form == "tuple":
        message, args = '"%s" %s %s', (request_line, "302", "0")
    elif form == "mapping":
        message, args = '"%(request)s" %(status)s 0', ({"request": request_line, "status": 302},)
    elif form == "value-tuple":
        message = request_line.replace("%", "%%").replace(EARLIER, "%s").replace(TOKEN, "%s")
        args = (EARLIER, TOKEN) if EARLIER in query else (TOKEN,)
    else:
        message = (
            request_line.replace("%", "%%")
            .replace(EARLIER, "%(earlier)s")
            .replace(TOKEN, "%(token)s")
        )
        args = ({"earlier": EARLIER, "token": TOKEN},)
    record = logging.LogRecord("django.server", logging.INFO, __file__, 1, message, args, None)
    assert RedactDesktopAuthToken().filter(record)
    formatted = logging.Formatter("%(levelname)s %(message)s").format(record)
    assert TOKEN not in formatted
    assert EARLIER not in formatted
    assert formatted.count("[redacted]") == (2 if EARLIER in query else 1)
    assert "next=%2F HTTP/1.1" in formatted
    assert path in formatted
    # A second handler/filter pass must remain safe.
    RedactDesktopAuthToken().filter(record)
    assert logging.Formatter("%(message)s").format(record).count("[redacted]") == (
        2 if EARLIER in query else 1
    )


def test_log_redaction_keeps_unrelated_query_members_and_non_strings():
    line = (
        "GET /desktop-auth/bootstrap/?Token=public&token=secret"
        "&next=%2F&other_token=public HTTP/1.1"
    )
    record = logging.LogRecord(
        "django.server", logging.INFO, __file__, 1, "%s %s", (line, 302), None
    )
    RedactDesktopAuthToken().filter(record)
    assert record.getMessage() == line.replace("token=secret", "token=[redacted]") + " 302"
    record = logging.LogRecord(
        "django.server", logging.INFO, __file__, 1, "%s", ("/other/?token=public",), None
    )
    RedactDesktopAuthToken().filter(record)
    assert record.getMessage() == "/other/?token=public"


def test_malformed_unrelated_url_does_not_break_logging():
    record = logging.LogRecord("django.server", logging.INFO, __file__, 1, "GET //[?x=y", (), None)
    assert RedactDesktopAuthToken().filter(record)
    assert record.getMessage() == "GET //[?x=y"


@pytest.mark.parametrize(
    "message,args",
    [
        ("GET /desktop-auth/bootstrap/?token=%s %d", (TOKEN,)),
        ("GET /desktop-auth/bootstrap/?token=%(token)s", (TOKEN,)),
    ],
)
def test_unformattable_record_neither_raises_nor_leaks(message, args):
    record = logging.LogRecord("django.server", logging.INFO, __file__, 1, message, args, None)
    assert RedactDesktopAuthToken().filter(record)
    formatted = logging.Formatter("%(message)s").format(record)
    assert TOKEN not in formatted
    assert "token=[redacted]" in formatted
