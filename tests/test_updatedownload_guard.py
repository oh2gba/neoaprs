"""The guard of Update now's downloads (neoaprs/updatedownload.py) with real requests, to a fake server on the loopback: an answer that is not 200, a redirect to an address that is not allowed (and the one that
is), a server that says nothing or is not HTTP, a body that stops in the middle, a disk that cannot take the file, and a work thread whose loop is gone. The address check is the test's own, which lets the
loopback through; the daemon's (url_allowed) is tested with the stand-ins in test_updatedownload.py."""
import asyncio
import threading
from pathlib import Path

import pytest

from neoaprs import updatedownload
from neoaprs.updatedownload import Cancelled, DownloadError, fetch_bytes, fetch_file, in_thread, open_url
from tests.support.env import until
from tests.support.fakehttp import FakeHttp, http_server
from tests.support.ptyline import posix_only


def loopback_only(server: FakeHttp) -> "updatedownload.Allowed":
    return lambda url: url.startswith(f"http://127.0.0.1:{server.port}/")


async def fetch(url: str, allowed: "updatedownload.Allowed") -> bytes:
    return await asyncio.to_thread(fetch_bytes, url, allowed)


async def test_an_answer_of_200_is_read_to_the_end_and_the_address_asked_is_the_one_given() -> None:
    server = await http_server()
    server.route("/SHA256SUMS", body=b"abc  file\n")
    assert await fetch(server.url("/SHA256SUMS"), loopback_only(server)) == b"abc  file\n"
    assert server.requests == ["/SHA256SUMS"]


async def test_an_answer_that_is_not_200_is_a_download_error_that_names_the_file_and_the_code() -> None:
    server = await http_server()
    server.route("/gone", status=404)
    with pytest.raises(DownloadError, match="gone: the server answered 404"):
        await fetch(server.url("/gone"), loopback_only(server))


async def test_a_redirect_to_an_address_that_is_allowed_is_followed_and_one_to_another_host_is_not() -> None:
    server = await http_server()
    server.route("/to-file", status=302, headers={"Location": server.url("/file")})
    server.route("/file", body=b"the file")
    server.route("/elsewhere", status=302, headers={"Location": "https://evil.example/file?token=1"})
    assert await fetch(server.url("/to-file"), loopback_only(server)) == b"the file"
    with pytest.raises(DownloadError, match=r"sent on to https://evil.example/file, which is not one of GitHub's addresses"):
        await fetch(server.url("/elsewhere"), loopback_only(server))
    assert server.requests == ["/to-file", "/file", "/elsewhere"], "nothing was asked of the other host (and its token is not in the message)"


async def test_a_download_that_ends_somewhere_the_check_does_not_allow_is_closed_and_refused() -> None:
    """Defence in depth: the address the response ends at is checked once more, with the check of each redirect before it."""
    server = await http_server()
    server.route("/to-file", status=302, headers={"Location": server.url("/file")})
    server.route("/file", body=b"the file")
    asked: list[str] = []

    def changes_its_mind(url: str) -> bool:
        asked.append(url)
        return len(asked) < 3                      # the address, the redirect, and then the end of it

    with pytest.raises(DownloadError, match="ended at .*/file, which is not one of GitHub's addresses"):
        await asyncio.to_thread(open_url, server.url("/to-file"), changes_its_mind)
    assert len(asked) == 3


async def test_a_server_that_says_nothing_is_given_up_on_after_the_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(updatedownload, "TIMEOUT_SEC", 0.2)
    server = await http_server()
    server.route("/hang", hang=True)
    with pytest.raises(DownloadError, match="hang could not be fetched: .*timed out"):
        await fetch(server.url("/hang"), loopback_only(server))


async def test_an_answer_that_is_not_http_and_a_port_nobody_listens_on_are_download_errors() -> None:
    server = await http_server()
    server.route("/junk", raw=b"this is not http\r\n\r\n")
    with pytest.raises(DownloadError, match="junk could not be fetched"):
        await fetch(server.url("/junk"), loopback_only(server))
    await server.stop()
    with pytest.raises(DownloadError, match="junk could not be fetched"):
        await fetch(server.url("/junk"), loopback_only(server))
    with pytest.raises(DownloadError, match="could not be fetched"):
        await asyncio.to_thread(open_url, "http://127.0.0.1:1/\x00", lambda url: True)             # (a control character in the address)


async def test_a_small_file_whose_body_stops_in_the_middle_is_a_download_error() -> None:
    server = await http_server()
    server.route("/chunk", chunked_cut=b"x" * 10)
    with pytest.raises(DownloadError, match="chunk could not be read"):
        await fetch(server.url("/chunk"), loopback_only(server))


async def test_a_file_whose_body_stops_in_the_middle_is_cut_short_or_a_download_error(tmp_path: Path) -> None:
    server = await http_server()
    server.route("/cut", body=b"x" * 10, announce=100)
    server.route("/chunk", chunked_cut=b"x" * 10)
    allowed = loopback_only(server)
    with pytest.raises(DownloadError, match="cut short: 10 of 100 bytes"):
        await asyncio.to_thread(fetch_file, server.url("/cut"), tmp_path / "cut", allowed, lambda done, total: None, threading.Event())
    with pytest.raises(DownloadError, match="chunk could not be downloaded"):
        await asyncio.to_thread(fetch_file, server.url("/chunk"), tmp_path / "chunk", allowed, lambda done, total: None, threading.Event())


async def test_a_folder_that_is_not_there_is_a_download_error_and_the_response_is_closed(tmp_path: Path) -> None:
    server = await http_server()
    server.route("/file", body=b"the file")
    with pytest.raises(DownloadError, match="file could not be downloaded"):
        await asyncio.to_thread(fetch_file, server.url("/file"), tmp_path / "no-such-folder" / "file", loopback_only(server), lambda done, total: None, threading.Event())


@posix_only
async def test_a_disk_that_is_full_is_a_download_error_with_the_reason() -> None:
    server = await http_server()
    server.route("/file", body=b"the file")
    with pytest.raises(DownloadError, match="No space left on device"):
        await asyncio.to_thread(fetch_file, server.url("/file"), Path("/dev/full"), loopback_only(server), lambda done, total: None, threading.Event())


async def test_a_cancel_during_a_real_download_is_a_cancel_and_not_a_download_error(tmp_path: Path) -> None:
    server = await http_server()
    server.route("/file", body=b"x" * 1000)
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(Cancelled):
        await asyncio.to_thread(fetch_file, server.url("/file"), tmp_path / "file", loopback_only(server), lambda done, total: None, cancelled)


async def test_a_work_thread_whose_asker_was_cancelled_ends_without_a_word() -> None:
    seen: list[dict[str, object]] = []
    asyncio.get_running_loop().set_exception_handler(lambda loop, context: seen.append(context))
    inside, release = threading.Event(), threading.Event()
    task = asyncio.ensure_future(in_thread(lambda: (inside.set(), release.wait(10))[1], "update-download-cancelled"))
    await until(inside.is_set)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    await until(lambda: not [t for t in threading.enumerate() if t.name == "update-download-cancelled"])
    assert seen == []


def test_a_work_thread_whose_loop_is_gone_ends_without_a_word() -> None:
    loop = asyncio.new_event_loop()
    inside, release = threading.Event(), threading.Event()
    task = loop.create_task(in_thread(lambda: (inside.set(), release.wait(10))[1], "update-download-orphan"))
    loop.run_until_complete(asyncio.sleep(0))                                             # the task has started its thread
    assert inside.wait(5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        loop.run_until_complete(task)
    loop.close()
    release.set()
    [thread] = [t for t in threading.enumerate() if t.name == "update-download-orphan"]
    thread.join(5)
    assert not thread.is_alive()

