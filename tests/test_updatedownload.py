"""The downloads of Update now (neoaprs/updatedownload.py) against a fake server: the file is written with its SHA-256 and its progress, a cancel is seen between two pieces, a file that is cut short or too large
fails, an address that is not allowed is not asked, and a redirect to one ends the download. No test reaches the network: the opener is a stand-in."""
import asyncio
import hashlib
import io
import threading
import urllib.request
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

from neoaprs.updateasset import url_allowed
from neoaprs.updatedownload import Cancelled, DownloadError, _Guarded, fetch_bytes, fetch_file, in_thread, open_url


class FakeResponse:
    def __init__(self, body: bytes, length: int | None = None, url: str = "https://github.com/x", before: threading.Event | None = None) -> None:
        self._body = io.BytesIO(body)
        self.headers = Message()
        if length is not None:
            self.headers["Content-Length"] = str(length)
        self.url = url
        self.closed = False
        self.reads = 0

    def read(self, size: int = -1) -> bytes:
        self.reads += 1
        return self._body.read(size)

    def geturl(self) -> str:
        return self.url

    def close(self) -> None:
        self.closed = True


def opener_of(response: FakeResponse, asked: list[str] | None = None) -> Any:
    def opener(url: str, allowed: Any) -> FakeResponse:
        if asked is not None:
            asked.append(url)
        return response
    return opener


BODY = bytes(range(256)) * 4000          # about 1 MB: four pieces


def test_a_file_is_written_with_its_sha256_and_its_progress(tmp_path: Path) -> None:
    response = FakeResponse(BODY, len(BODY))
    seen: list[tuple[int, int | None]] = []
    target = tmp_path / "x.part"
    digest = fetch_file("https://github.com/x", target, url_allowed, lambda done, total: seen.append((done, total)), threading.Event(), opener_of(response))
    assert digest == hashlib.sha256(BODY).hexdigest()
    assert target.read_bytes() == BODY
    assert seen[-1] == (len(BODY), len(BODY)) and len(seen) >= 4 and all(t == len(BODY) for _, t in seen)
    assert response.closed


def test_a_server_that_does_not_say_the_size_is_told_as_none(tmp_path: Path) -> None:
    seen: list[int | None] = []
    fetch_file("https://github.com/x", tmp_path / "x", url_allowed, lambda done, total: seen.append(total), threading.Event(), opener_of(FakeResponse(b"abc")))
    assert seen == [None]


def test_a_cancel_is_seen_between_two_pieces(tmp_path: Path) -> None:
    cancelled = threading.Event()
    response = FakeResponse(BODY, len(BODY))
    with pytest.raises(Cancelled):
        fetch_file("https://github.com/x", tmp_path / "x", url_allowed, lambda done, total: cancelled.set(), cancelled, opener_of(response))
    assert response.reads == 1 and response.closed


def test_a_file_cut_short_or_larger_than_the_limit_fails(tmp_path: Path) -> None:
    with pytest.raises(DownloadError, match="cut short: 3 of 10 bytes"):
        fetch_file("https://github.com/x", tmp_path / "x", url_allowed, lambda d, t: None, threading.Event(), opener_of(FakeResponse(b"abc", 10)))
    with pytest.raises(DownloadError, match="more than an update can be"):
        fetch_file("https://github.com/x", tmp_path / "x", url_allowed, lambda d, t: None, threading.Event(), opener_of(FakeResponse(b"abc", 3)), limit=2)
    with pytest.raises(DownloadError, match="more than an update can be"):
        fetch_file("https://github.com/x", tmp_path / "x", url_allowed, lambda d, t: None, threading.Event(), opener_of(FakeResponse(BODY)), limit=1000)


def test_a_small_file_is_read_whole_and_refused_when_too_long() -> None:
    assert fetch_bytes("https://github.com/SHA256SUMS", url_allowed, opener=opener_of(FakeResponse(b"sums\n"))) == b"sums\n"
    with pytest.raises(DownloadError, match="longer than 4 bytes"):
        fetch_bytes("https://github.com/SHA256SUMS", url_allowed, limit=4, opener=opener_of(FakeResponse(b"sums\n")))


def test_an_address_that_is_not_allowed_is_not_asked() -> None:
    with pytest.raises(DownloadError, match="not one of GitHub's addresses"):
        open_url("http://github.com/oh2gba/neoaprs/releases/download/v0.7.0/SHA256SUMS", url_allowed)
    with pytest.raises(DownloadError, match="not one of GitHub's addresses"):
        open_url("https://evil.example/SHA256SUMS", url_allowed)


@pytest.mark.parametrize("target", ["https://evil.example/x", "http://objects.githubusercontent.com/x", "https://github.com.evil.example/x"])
def test_a_redirect_to_an_address_that_is_not_allowed_ends_the_download(target: str) -> None:
    handler = _Guarded(url_allowed)
    request = urllib.request.Request("https://github.com/oh2gba/neoaprs/releases/download/v0.7.0/SHA256SUMS")
    with pytest.raises(DownloadError, match="not one of GitHub's addresses"):
        handler.redirect_request(request, io.BytesIO(), 302, "Found", Message(), target)        # type: ignore[arg-type]


def test_a_redirect_to_githubs_hosts_of_release_files_is_followed() -> None:
    handler = _Guarded(url_allowed)
    request = urllib.request.Request("https://github.com/oh2gba/neoaprs/releases/download/v0.7.0/SHA256SUMS")
    followed = handler.redirect_request(request, io.BytesIO(), 302, "Found", Message(), "https://release-assets.githubusercontent.com/a/b?sig=1")      # type: ignore[arg-type]
    assert followed is not None and followed.full_url == "https://release-assets.githubusercontent.com/a/b?sig=1"


async def test_in_thread_gives_the_result_and_raises_the_exception_of_the_work() -> None:
    assert await in_thread(lambda: threading.current_thread().name, "named") == "named"

    def fail() -> None:
        raise DownloadError("no")
    with pytest.raises(DownloadError, match="no"):
        await in_thread(fail)
    assert asyncio.get_running_loop().is_running()
