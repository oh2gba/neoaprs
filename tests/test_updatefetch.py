"""The request of the update check (neoaprs/updatefetch.py) against a fake version page on the loopback: the query carries the version and the platform and nothing else, the User-Agent says the same, and a page that
is not there, says no or sends too much is None."""
import asyncio
import urllib.error
import urllib.request
from email.message import Message
from io import BytesIO

import pytest

from neoaprs.updatefetch import MAX_BYTES, _NotDowngraded, fetch, get, request_url
from tests.support.fakeversionpage import version_page


def test_the_query_has_the_version_and_the_platform_after_what_the_address_has() -> None:
    assert request_url("https://oh2gba.eu/neoaprs/version.php", "0.1.0", "linux") == "https://oh2gba.eu/neoaprs/version.php?v=0.1.0&os=linux"
    assert request_url("https://example.org/v.php?x=1", "0.1.0", "linux-arm") == "https://example.org/v.php?x=1&v=0.1.0&os=linux-arm"


async def test_the_page_is_asked_with_the_version_and_the_platform_and_nothing_else() -> None:
    page = await version_page({"version": "0.2.0", "url": "https://example.org/", "message": ""})
    body = await fetch(page.url, "0.1.0", "linux-appimage")
    assert body is not None and b'"0.2.0"' in body
    (path, headers), = page.requests
    assert path == "/version.php?v=0.1.0&os=linux-appimage"
    assert headers["user-agent"] == "NeoAPRS/0.1.0 (linux-appimage)"
    assert set(headers) <= {"user-agent", "host", "accept-encoding", "connection"}, "no cookie, no identity, nothing else is sent"


async def test_a_page_that_says_no_or_is_not_there_is_none() -> None:
    page = await version_page({})
    page.status = 503
    assert await fetch(page.url, "0.1.0", "linux") is None
    await page.stop()
    assert await fetch(page.url, "0.1.0", "linux") is None, "nothing listens"


async def test_a_page_that_hangs_is_none_after_the_timeout() -> None:
    page = await version_page({})
    page.hang = True
    assert await asyncio.to_thread(get, page.url, "0.1.0", "linux", 0.3) is None


async def test_only_the_first_bytes_of_a_long_answer_are_read() -> None:
    page = await version_page()
    page.body = b"x" * (MAX_BYTES * 4)
    body = await fetch(page.url, "0.1.0", "linux")
    assert body is not None and len(body) == MAX_BYTES


async def test_an_address_that_is_not_a_web_address_is_none() -> None:
    assert await fetch("not a url", "0.1.0", "linux") is None
    assert await fetch("file:///etc/passwd", "0.1.0", "linux") is None


def test_a_redirect_from_https_to_http_is_refused_and_one_to_https_followed() -> None:
    handler, request = _NotDowngraded(), urllib.request.Request("https://oh2gba.eu/neoaprs/version.php")
    with pytest.raises(urllib.error.HTTPError):
        handler.redirect_request(request, BytesIO(), 302, "Found", Message(), "http://example.org/")
    followed = handler.redirect_request(request, BytesIO(), 302, "Found", Message(), "https://example.org/v.php")
    assert followed is not None and followed.full_url == "https://example.org/v.php"
