"""The update check request (neoaprs/updatefetch.py) against a fake version page: the query carries
the version, platform and installation number and nothing else, and a missing page, a refusal or too
much data is None.
"""
import asyncio
import http.server
import socketserver
import threading
import time
import urllib.error
import urllib.request
from email.message import Message
from datetime import UTC, datetime
from io import BytesIO

import pytest

from neoaprs import updatefetch
from neoaprs.updatefetch import MAX_BYTES, MAX_RETRY_AFTER_SEC, _NotDowngraded, fetch, fetch_url, get, get_answer, request_url, retry_after
from tests.support.fakeversionpage import version_page


def test_the_query_has_the_version_and_the_platform_after_what_the_address_has() -> None:
    assert request_url("https://oh2gba.eu/neoaprs/version.php", "0.1.0", "linux") == "https://oh2gba.eu/neoaprs/version.php?v=0.1.0&os=linux"
    assert request_url("https://example.org/v.php?x=1", "0.1.0", "linux-arm") == "https://example.org/v.php?x=1&v=0.1.0&os=linux-arm"


def test_the_number_of_the_installation_is_the_last_of_the_query_when_there_is_one() -> None:
    number = "0123456789abcdef0123456789abcdef"
    assert request_url("https://oh2gba.eu/neoaprs/version.php", "0.1.0", "linux", number) == f"https://oh2gba.eu/neoaprs/version.php?v=0.1.0&os=linux&id={number}"


async def test_the_page_is_asked_with_the_version_and_the_platform_and_nothing_else() -> None:
    page = await version_page({"version": "0.2.0", "url": "https://example.org/", "message": ""})
    body = await fetch(page.url, "0.1.0", "linux-appimage")
    assert body is not None and b'"0.2.0"' in body
    (path, headers), = page.requests
    assert path == "/version.php?v=0.1.0&os=linux-appimage"
    assert headers["user-agent"] == "NeoAPRS/0.1.0 (linux-appimage)"
    assert set(headers) <= {"user-agent", "host", "accept-encoding", "connection"}, "no cookie, no identity, nothing else is sent"


async def test_the_number_is_sent_as_id_and_the_user_agent_does_not_carry_it() -> None:
    page = await version_page({"version": "0.2.0", "url": "", "message": ""})
    await fetch(page.url, "0.1.0", "linux", "0123456789abcdef0123456789abcdef")
    (path, headers), = page.requests
    assert path == "/version.php?v=0.1.0&os=linux&id=0123456789abcdef0123456789abcdef" and headers["user-agent"] == "NeoAPRS/0.1.0 (linux)"


async def test_a_page_that_says_no_or_is_not_there_is_none() -> None:
    page = await version_page({})
    page.status = 503
    assert await fetch(page.url, "0.1.0", "linux") is None
    await page.stop()
    assert await fetch(page.url, "0.1.0", "linux") is None, "nothing listens"


@pytest.mark.expects_errors
async def test_an_error_nobody_expected_on_the_thread_is_none_and_not_a_request_that_never_ends(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> bytes:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(updatefetch, "get", boom)
    monkeypatch.setattr(updatefetch, "get_url", boom)
    assert await asyncio.wait_for(fetch("https://example.org/v.php", "0.1.0", "linux"), 5.0) is None
    assert await asyncio.wait_for(fetch_url("https://example.org/CHANGELOG.md", "0.1.0", "linux", 100), 5.0) is None


async def test_a_page_that_hangs_is_none_after_the_timeout() -> None:
    page = await version_page({})
    page.hang = True
    assert await asyncio.to_thread(get, page.url, "0.1.0", "linux", "", 0.3) is None


async def test_an_answer_longer_than_its_limit_is_a_failed_fetch_and_not_half_a_file() -> None:
    page = await version_page()
    page.body = b"x" * (MAX_BYTES * 4)
    assert await fetch(page.url, "0.1.0", "linux") is None
    page.body = b"x" * MAX_BYTES
    body = await fetch(page.url, "0.1.0", "linux")
    assert body is not None and len(body) == MAX_BYTES
    assert await fetch_url(page.url, "0.1.0", "linux", MAX_BYTES - 1) is None


def _dripping_server() -> tuple[socketserver.ThreadingTCPServer, str]:
    class Drip(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Length", "4096")
            self.end_headers()
            try:
                for _ in range(4096):
                    self.wfile.write(b"x")
                    self.wfile.flush()
                    time.sleep(0.1)
            except OSError:
                pass

        def log_message(self, *args: object) -> None:
            pass

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Drip)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/v.php"


def test_a_server_that_drips_its_answer_is_given_up_on_at_the_deadline() -> None:
    server, url = _dripping_server()
    try:
        began = time.monotonic()
        assert get_answer(url, "0.1.0", "linux", timeout_sec=0.5) is None
        assert time.monotonic() - began < 3.0
    finally:
        server.shutdown()
        server.server_close()


async def test_a_task_that_waits_for_a_stuck_thread_is_freed(monkeypatch: pytest.MonkeyPatch) -> None:
    release = threading.Event()
    monkeypatch.setattr(updatefetch, "TIMEOUT_SEC", 0.2)
    monkeypatch.setattr(updatefetch, "FEED_GRACE_SEC", 0.1)
    monkeypatch.setattr(updatefetch, "get_url", lambda *args, **kwargs: release.wait(10) and None)
    try:
        assert await asyncio.wait_for(fetch_url("https://example.org/c.md", "0.1.0", "linux", 100), 3.0) is None
    finally:
        release.set()


def test_a_retry_after_is_read_safely_and_never_longer_than_an_hour() -> None:
    for text in ("1" * 400, "9" * 5000, "99999999999", "\u0661\u0662"):
        said = retry_after(text)
        assert said is None or 0.0 <= said <= MAX_RETRY_AFTER_SEC
    assert retry_after("1" * 400) == MAX_RETRY_AFTER_SEC and retry_after("120") == 120.0 and retry_after("\u0661\u0662") is None
    assert retry_after("Fri, 31 Dec 9999 23:59:59 GMT", datetime(2026, 1, 1, tzinfo=UTC)) == MAX_RETRY_AFTER_SEC


async def test_an_address_that_is_not_a_web_address_is_none() -> None:
    assert await fetch("not a url", "0.1.0", "linux") is None
    assert await fetch("file:///etc/passwd", "0.1.0", "linux") is None


def test_a_redirect_from_https_to_http_is_refused_and_one_to_https_followed() -> None:
    handler, request = _NotDowngraded(), urllib.request.Request("https://oh2gba.eu/neoaprs/version.php")
    with pytest.raises(urllib.error.HTTPError):
        handler.redirect_request(request, BytesIO(), 302, "Found", Message(), "http://example.org/")
    followed = handler.redirect_request(request, BytesIO(), 302, "Found", Message(), "https://example.org/v.php")
    assert followed is not None and followed.full_url == "https://example.org/v.php"
