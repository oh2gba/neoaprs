"""The question of the map's layers (neoaprs/updatefetch.py `get_feed`, `fetch_feed`) against a fake server on the loopback: a packed answer asked for and unpacked within its bound, the program's User-Agent and
the headers given and nothing else, the status and the wait of a Retry-After said, a password of the address sent as basic authentication to its host only, and an answer too large, one that does not come in
its time, a server that is not there and an address that is not a web address are None."""
import base64
import gzip
import threading
import time
from datetime import UTC, datetime

import pytest

from neoaprs import nodevices, updatefetch
from neoaprs.updatefetch import FeedAnswer, fetch_feed, retry_after, unpacked, without_password
from tests.support.env import until
from tests.support.fakelayers import layers_server

BODY = b'{"now": 1794812336, "aircraft": []}'


async def test_a_packed_answer_is_asked_for_and_unpacked_and_the_headers_are_the_programs_and_the_ones_given() -> None:
    server = await layers_server()
    server.route("/feed", body=BODY, packed=True)
    answer = await fetch_feed(server.url + "/feed", "0.21.0", "linux", {"Digitraffic-User": "NeoAPRS"}, 1000, 1000)
    assert answer == FeedAnswer(200, BODY, None)
    ((path, headers),) = server.requests
    assert path == "/feed" and headers["accept-encoding"] == "gzip" and headers["user-agent"] == "NeoAPRS/0.21.0 (linux)" and headers["digitraffic-user"] == "NeoAPRS"
    assert set(headers) == {"accept-encoding", "user-agent", "digitraffic-user", "host", "connection"}, "no cookie, no call, nothing else"


async def test_an_answer_that_is_not_packed_is_taken_as_it_is() -> None:
    server = await layers_server()
    server.route("/feed", body=BODY)
    assert await fetch_feed(server.url + "/feed", "0.21.0", "linux", {}, 1000, 1000) == FeedAnswer(200, BODY, None)


async def test_an_answer_larger_than_its_bound_as_it_travels_or_unpacked_is_none() -> None:
    server = await layers_server()
    server.route("/big", body=b"x" * 2000)
    server.route("/bomb", body=b"\0" * 1_000_000, packed=True)
    assert await fetch_feed(server.url + "/big", "0.21.0", "linux", {}, 1000, 10_000) is None
    assert len(gzip.compress(b"\0" * 1_000_000)) < 2000
    assert await fetch_feed(server.url + "/bomb", "0.21.0", "linux", {}, 2000, 100_000) is None, "a small answer that unpacks to too much"


async def test_a_refusal_says_its_status_and_the_wait_its_retry_after_asks_for() -> None:
    server = await layers_server()
    server.route("/busy", status=429, headers={"Retry-After": "120"})
    server.route("/gone", status=404)
    assert await fetch_feed(server.url + "/busy", "0.21.0", "linux", {}, 1000, 1000) == FeedAnswer(429, b"", 120.0)
    assert await fetch_feed(server.url + "/gone", "0.21.0", "linux", {}, 1000, 1000) == FeedAnswer(404, b"", None)


def test_a_retry_after_is_seconds_or_a_date_and_one_that_cannot_be_read_is_none() -> None:
    now = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)
    assert retry_after("30", now) == 30.0
    assert retry_after("Wed, 18 Nov 2026 12:02:00 GMT", now) == 120.0
    assert retry_after("Wed, 18 Nov 2026 11:00:00 GMT", now) == 0.0, "a date gone by: at once"
    assert retry_after("soon", now) is None and retry_after(None, now) is None and retry_after("", now) is None and retry_after("-5", now) is None


def test_a_packed_answer_that_is_cut_short_or_is_not_gzip_is_none() -> None:
    packed = gzip.compress(BODY)
    assert unpacked(packed, "gzip", 1000) == BODY
    assert unpacked(packed[:-6], "gzip", 1000) is None
    assert unpacked(b"not gzip", "gzip", 1000) is None
    assert unpacked(BODY, "br", 1000) is None


@pytest.fixture
def under_the_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    """The no-devices switch is on in this test's own process too (tests/conftest.py lifts it for every test that does not ask for a fixture of this name)."""
    monkeypatch.setenv(nodevices.ENV, "1")


async def test_a_server_that_is_not_there_and_an_address_that_is_not_a_web_one_are_none() -> None:
    server = await layers_server()
    await server.stop()
    assert await fetch_feed(server.url + "/feed", "0.21.0", "linux", {}, 1000, 1000) is None
    assert await fetch_feed("file:///etc/passwd", "0.21.0", "linux", {}, 1000, 1000) is None


async def test_under_the_switch_another_computer_is_not_asked_and_this_one_is(under_the_switch: None, monkeypatch: pytest.MonkeyPatch) -> None:
    tried: list[str] = []
    monkeypatch.setattr(updatefetch.urllib.request.OpenerDirector, "open", lambda self, request, timeout=None: tried.append(request.full_url))
    assert await fetch_feed("http://192.0.2.1/tar1090/data/aircraft.json", "0.21.0", "linux", {}, 1000, 1000) is None and tried == [], "refused before anything is opened"
    server = await layers_server()
    server.route("/feed", body=BODY)
    monkeypatch.undo()
    monkeypatch.setenv(nodevices.ENV, "1")
    assert await fetch_feed(server.url + "/feed", "0.21.0", "linux", {}, 1000, 1000) == FeedAnswer(200, BODY, None)


async def test_a_password_in_the_address_is_sent_as_basic_authentication_and_never_as_a_part_of_the_hosts_name() -> None:
    server = await layers_server()
    server.password = ("user", "s3cret@pw")
    server.route("/tar1090/data/aircraft.json", body=BODY)
    url = f"http://user:s3cret%40pw@127.0.0.1:{server.port}/tar1090/data/aircraft.json"
    assert await fetch_feed(url, "0.21.0", "linux", {}, 1000, 1000) == FeedAnswer(200, BODY, None)
    ((_, headers),) = server.requests
    assert headers["authorization"] == "Basic " + base64.b64encode(b"user:s3cret@pw").decode() and headers["host"] == f"127.0.0.1:{server.port}"
    assert await fetch_feed(server.url + "/tar1090/data/aircraft.json", "0.21.0", "linux", {}, 1000, 1000) == FeedAnswer(401, b"", None), "without it the receiver refuses"
    assert without_password("http://pi.local/a.json") == ("http://pi.local/a.json", None)


async def test_the_password_follows_a_redirect_on_the_same_host_and_never_one_to_another() -> None:
    server = await layers_server()
    server.route("/here", status=302, headers={"Location": f"http://127.0.0.1:{server.port}/feed"})
    server.route("/away", status=302, headers={"Location": f"http://localhost:{server.port}/feed"})
    server.route("/feed", body=BODY)
    for path in ("/here", "/away"):
        await fetch_feed(f"http://user:pw@127.0.0.1:{server.port}{path}", "0.21.0", "linux", {}, 1000, 1000)
    said = [(path, headers.get("authorization")) for path, headers in server.requests]
    token = "Basic " + base64.b64encode(b"user:pw").decode()
    assert said == [("/here", token), ("/feed", token), ("/away", token), ("/feed", None)]


async def test_an_answer_that_drips_is_given_up_when_its_time_is_over_and_its_thread_ends() -> None:
    server = await layers_server()
    server.route("/slow", body=b"x" * 40, drip_sec=0.1)
    before = set(threading.enumerate())
    start = time.monotonic()
    assert await fetch_feed(server.url + "/slow", "0.21.0", "linux", {}, 1000, 1000, timeout_sec=0.5) is None
    assert time.monotonic() - start < 1.5
    await until(lambda: not [thread for thread in threading.enumerate() if thread.name == "layer-fetch" and thread not in before], 3.0)
