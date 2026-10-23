"""Network access to the page (neoaprs/web/access.py): the switch `web/network`, the access key, the session cookie and what a device that has not logged in is refused. The tests have no second address, so a request
is made to look as if it came from elsewhere by saying that no address is the loopback (`away`); the loopback tests do without."""
import json
import logging
import re
import socket
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from tornado.httpclient import HTTPClientError, HTTPResponse

from neoaprs.config import DEFAULTS
from neoaprs.web import access as web_access
from neoaprs.web import addresses
from neoaprs.web.access import COOKIE, MAX_WRONG, SESSION_DAYS, Access, Verdict, new_key
from tests.support.clock import FixedClock
from tests.support.env import Env, until
from tests.support.wsclient import WsClient

KEY = "k7m2-x9pq-4hrt"
NETWORK = {"web/network": "true", "web/key": KEY}
LAN = "192.168.1.20"
KEY_FORM = re.compile(r"^[2-9a-hj-km-np-z]{4}(-[2-9a-hj-km-np-z]{4}){2}$")


@pytest.fixture(autouse=True)
def lan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("neoaprs.web.server.lan_addresses", lambda: [LAN])


@pytest.fixture
def away(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every request comes from an address that is not this computer's."""
    monkeypatch.setattr(web_access, "is_loopback", lambda ip: False)


async def served(tmp_path: Path, settings: dict[str, str] | None = None, clock: FixedClock | None = None) -> Env:
    e = Env(tmp_path, web=True, settings=settings, clock=clock)
    await e.start()
    return e


def login_body(key: str) -> str:
    return json.dumps({"key": key})


async def log_in(e: Env, key: str = KEY) -> HTTPResponse:
    return await e.fetch("/access", method="POST", body=login_body(key))


def cookie_of(answer: HTTPResponse) -> str:
    """The Cookie header a browser sends back for the answer's Set-Cookie."""
    return answer.headers["Set-Cookie"].split(";", 1)[0]


async def refused_at_the_socket(e: Env, cookie: str | None = None) -> int:
    with pytest.raises(HTTPClientError) as refused:
        await e.ws(cookie=cookie)
    return refused.value.code


# ---- what a device that has not logged in gets ------------------------------------------------------------------------------------------------------

async def test_a_device_that_has_not_logged_in_gets_the_files_of_the_page_and_nothing_that_carries_data(tmp_path: Path, away: None) -> None:
    e = await served(tmp_path, NETWORK)
    (tmp_path / "basemap.pmtiles").write_bytes(b"0123456789")
    (tmp_path / "basemap-world.pmtiles").write_bytes(b"0123456789")
    assert (await e.fetch("/")).code == 200 and (await e.fetch("/index.html")).code == 200, "the page holds the key screen"
    assert (await e.fetch("/access")).code == 401, "it asks whether it is let in, and is told it is not"
    for path in ("/basemap.pmtiles", "/basemap-world.pmtiles"):
        answer = await e.fetch(path)
        assert answer.code == 401 and b"Log in" in answer.body and len(answer.body) < 100, path
        assert (await e.fetch(path, headers={"Range": "bytes=2-4"})).code == 401
    assert await refused_at_the_socket(e) == 401
    assert await refused_at_the_socket(e, cookie=f"{COOKIE}=nonsense") == 401
    assert await refused_at_the_socket(e, cookie=f"{COOKIE}=9999999999.00.{'0' * 64}") == 401, "a session needs the mac of the key"
    assert e.server is not None and len(e.server.api.clients) == 0


async def test_a_wrong_key_is_refused_and_logged_and_gives_no_cookie(tmp_path: Path, away: None, caplog: pytest.LogCaptureFixture) -> None:
    e = await served(tmp_path, NETWORK)
    for typed in ("k7m2-x9pq-4hrs", "", "k7m2", "x" * 100):
        answer = await log_in(e, typed)
        assert answer.code in (400, 403) and "Set-Cookie" not in answer.headers, typed
    assert (await e.fetch("/access", method="POST", body="not json")).code == 400
    assert (await e.fetch("/access", method="POST", body="[1]")).code == 400
    assert await refused_at_the_socket(e) == 401
    assert any("wrong access key" in r.getMessage() for r in caplog.records)
    assert KEY not in caplog.text, "the key is not in the log"


async def test_five_wrong_keys_in_a_minute_shut_the_address_out_for_a_while_and_the_right_key_does_not_help_then(tmp_path: Path, away: None, caplog: pytest.LogCaptureFixture) -> None:
    clock = FixedClock()
    e = await served(tmp_path, NETWORK, clock)
    codes = [(await log_in(e, "aaaa-aaaa-aaaa")).code for _ in range(MAX_WRONG)]
    assert codes == [403] * MAX_WRONG
    shut = await log_in(e)
    assert shut.code == 429 and int(shut.headers["Retry-After"]) >= 60 and "Set-Cookie" not in shut.headers
    assert any("shut out" in r.getMessage() for r in caplog.records)
    clock.advance(120)
    assert (await log_in(e)).code == 429
    clock.advance(300)
    assert (await log_in(e)).code == 204, "the wait is over"


async def test_the_right_key_gives_a_session_cookie_that_opens_the_socket_and_the_map_and_is_not_the_key(tmp_path: Path, away: None) -> None:
    e = await served(tmp_path, NETWORK)
    (tmp_path / "basemap.pmtiles").write_bytes(b"0123456789")
    answer = await log_in(e, " K7M2 x9pq-4HRT ")
    assert answer.code == 204
    header = answer.headers["Set-Cookie"]
    assert header.startswith(f"{COOKIE}=") and "HttpOnly" in header and "SameSite=Strict" in header and "Path=/" in header
    assert "expires=" in header.lower() or "max-age=" in header.lower()
    assert "k7m2" not in header and "x9pq" not in header and "4hrt" not in header, "the cookie is not the key"
    cookie = cookie_of(answer)
    assert (await e.fetch("/access", headers={"Cookie": cookie})).code == 204
    assert (await e.fetch("/basemap.pmtiles", headers={"Cookie": cookie, "Range": "bytes=2-4"})).code == 206
    page: WsClient = await e.ws(cookie=cookie)
    await page.expect("hello")
    await page.until(lambda: "config" in page.topics)
    assert page.topics["config"]["values"]["web/key"] == KEY, "a page that is let in sees the key"
    assert e.server is not None and len(e.server.api.clients) == 1


async def test_a_session_is_kept_across_a_restart_and_ends_after_a_year_or_with_a_changed_token() -> None:
    clock = FixedClock()
    config = replace(DEFAULTS, web_network=True, web_key=KEY)
    first = Access(lambda: config, clock)
    token = first.session()
    assert KEY not in token and KEY.replace("-", "") not in token

    class Request:
        def __init__(self, value: str) -> None:
            from http.cookies import SimpleCookie
            self.cookies = SimpleCookie()
            self.cookies[COOKIE] = value
            self.remote_ip = "192.168.1.30"
            self.headers: dict[str, str] = {}

    again = Access(lambda: config, clock)
    assert again.allowed(Request(token)) is True, "a session is not stored: another Access with the same key knows it"
    assert again.allowed(Request(token[:-1] + ("0" if token[-1] != "0" else "1"))) is False
    assert again.allowed(Request("x" + token)) is False and again.allowed(Request("")) is False
    assert Access(lambda: replace(config, web_key="aaaa-bbbb-cccc"), clock).allowed(Request(token)) is False, "a new key ends it"
    assert Access(lambda: replace(config, web_network=False), clock).allowed(Request(token)) is False, "and so does switching the network off"
    clock.advance(SESSION_DAYS * 86400 + 1)
    assert again.allowed(Request(token)) is False


def test_wrong_keys_are_counted_for_each_address_and_forgotten_after_the_minute_or_a_right_key() -> None:
    clock = FixedClock()
    access = Access(lambda: replace(DEFAULTS, web_network=True, web_key=KEY), clock)
    for _ in range(MAX_WRONG - 1):
        assert access.try_key("10.0.0.1", "wrong") is Verdict.WRONG
    assert access.try_key("10.0.0.2", KEY) is Verdict.ACCEPTED, "another address is not held up"
    assert access.try_key("10.0.0.1", KEY) is Verdict.ACCEPTED, "the right key counts as right"
    for _ in range(MAX_WRONG - 1):
        assert access.try_key("10.0.0.1", "wrong") is Verdict.WRONG, "and wipes the count"
    clock.advance(61)
    assert access.try_key("10.0.0.1", "wrong") is Verdict.WRONG and access.try_key("10.0.0.1", KEY) is Verdict.ACCEPTED, "wrong keys of an earlier minute do not add up"
    for _ in range(MAX_WRONG):
        access.try_key("10.0.0.3", "wrong")
    assert access.try_key("10.0.0.3", KEY) is Verdict.BLOCKED and access.try_key("10.0.0.2", KEY) is Verdict.ACCEPTED


def test_a_key_is_three_groups_of_four_without_look_alike_characters() -> None:
    keys = {new_key() for _ in range(200)}
    assert len(keys) == 200 and all(KEY_FORM.match(k) for k in keys)
    assert not any(c in "".join(keys) for c in "01ilo")


# ---- a new key -------------------------------------------------------------------------------------------------------------------------------------

async def test_a_new_key_logs_every_device_out_and_leaves_the_one_that_asked_in(tmp_path: Path, away: None) -> None:
    e = await served(tmp_path, NETWORK)
    phone, laptop = cookie_of(await log_in(e)), cookie_of(await log_in(e))
    page = await e.ws(cookie=phone)
    other = await e.ws(cookie=laptop)
    await page.until(lambda: "config" in page.topics)
    assert (await e.fetch("/access/new", method="POST")).code == 401, "not without a login"
    assert KEY == e.ctl.config.web_key
    renewed = await e.fetch("/access/new", method="POST", headers={"Cookie": phone})
    assert renewed.code == 204
    fresh = e.ctl.config.web_key
    assert fresh != KEY and KEY_FORM.match(fresh) and await e.ctl.store.setting("web/key") == fresh
    assert (await e.fetch("/access", headers={"Cookie": phone})).code == 401 and (await e.fetch("/access", headers={"Cookie": laptop})).code == 401
    mine = cookie_of(renewed)
    assert (await e.fetch("/access", headers={"Cookie": mine})).code == 204, "the device that asked is given a session of the new key"
    await other.until(lambda: other.closed_with is not None)
    await page.until(lambda: page.closed_with is not None)
    assert other.closed_with is not None and other.closed_with[0] == 1008, "an open socket of the old key is closed"
    assert await refused_at_the_socket(e, cookie=phone) == 401
    assert (await log_in(e, KEY)).code == 403 and (await log_in(e, fresh)).code == 204
    again = await e.ws(cookie=mine)
    await again.expect("hello")


async def test_a_cross_site_post_is_refused(tmp_path: Path, away: None) -> None:
    e = await served(tmp_path, NETWORK)
    assert (await e.fetch("/access", method="POST", body=login_body(KEY), headers={"Origin": "http://evil.example"})).code == 403
    right = await e.fetch("/access", method="POST", body=login_body(KEY), headers={"Origin": f"http://127.0.0.1:{e.port}"})
    assert right.code == 204
    assert (await e.fetch("/access/new", method="POST", headers={"Cookie": cookie_of(right), "Origin": "http://evil.example"})).code == 403
    assert e.ctl.config.web_key == KEY


# ---- the loopback ----------------------------------------------------------------------------------------------------------------------------------

async def test_this_computer_is_never_asked_for_the_key(tmp_path: Path) -> None:
    e = await served(tmp_path, NETWORK)
    (tmp_path / "basemap.pmtiles").write_bytes(b"0123456789")
    assert (await e.fetch("/access")).code == 204
    assert (await e.fetch("/basemap.pmtiles")).code == 200
    page = await e.ws()
    await page.expect("hello")
    answer = await log_in(e, "wrong")
    assert answer.code == 204 and "Set-Cookie" not in answer.headers, "nothing to log in to"
    renewed = await e.fetch("/access/new", method="POST")
    assert renewed.code == 204 and "Set-Cookie" not in renewed.headers and e.ctl.config.web_key != KEY


async def test_a_request_through_a_proxy_on_this_computer_is_not_this_computer(tmp_path: Path) -> None:
    e = await served(tmp_path, NETWORK)
    for header in ("X-Forwarded-For", "Forwarded", "X-Real-Ip"):
        assert (await e.fetch("/access", headers={header: "203.0.113.9"})).code == 401, header
    assert (await e.fetch("/access")).code == 204, "and without one it is this computer"


async def test_with_the_network_off_a_device_that_is_not_this_computer_cannot_log_in_whatever_it_types(tmp_path: Path, away: None) -> None:
    e = await served(tmp_path, {"web/key": KEY})
    assert e.ctl.config.web_network is False
    assert (await log_in(e)).code == 403 and (await e.fetch("/access")).code == 401 and await refused_at_the_socket(e) == 401


# ---- the switch ------------------------------------------------------------------------------------------------------------------------------------

def listening_on(e: Env) -> set[str]:
    assert e.server is not None and e.server._server is not None
    return {str(sock.getsockname()[0]) for sock in e.server._server._sockets.values()}


async def wait_for_address(e: Env, address: str) -> None:
    assert e.server is not None
    server = e.server
    await until(lambda: server.address == address)


async def test_the_switch_listens_on_every_interface_and_makes_a_key_the_first_time_and_goes_back_to_the_loopback(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="neoaprs.web")
    e = await served(tmp_path)
    assert e.server is not None
    port = e.port
    assert listening_on(e) == {"127.0.0.1"} and e.server.reach() == [] and e.ctl.config.web_key == ""
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == 10)
    assert page.topics["config"]["urls"] == [] and page.topics["config"]["values"]["web/network"] == "false"
    await page.send({"cmd": "set_config", "values": {"web/network": "true"}})
    await wait_for_address(e, "")
    key = e.ctl.config.web_key
    assert KEY_FORM.match(key) and await e.ctl.store.setting("web/key") == key and e.ctl.config.web_network is True
    assert listening_on(e) <= {"0.0.0.0", "::"} and e.port == port, "every interface, on the port the page was on"
    await page.until(lambda: page.topics["config"]["urls"] != [])
    assert page.topics["config"]["urls"] == [f"http://{LAN}:{port}/", f"http://{socket.gethostname().lower()}.local:{port}/"]
    assert page.topics["config"]["values"]["web/key"] == key
    assert any("network access is on" in r.getMessage() and f"http://{LAN}:{port}/" in r.getMessage() for r in caplog.records)
    assert (await e.fetch("/")).code == 200, "the page is still served on the loopback"
    await page.send({"cmd": "set_config", "values": {"web/network": "false"}})
    await wait_for_address(e, "127.0.0.1")
    await page.until(lambda: page.topics["config"]["urls"] == [])
    assert listening_on(e) == {"127.0.0.1"} and e.port == port and e.ctl.config.web_key == key, "the key is kept for the next time"
    await page.send({"cmd": "set_config", "values": {"web/network": "true"}})
    await wait_for_address(e, "")
    assert e.ctl.config.web_key == key, "and it is not made again"
    assert not any("there is no token" in r.getMessage() for r in caplog.records)


async def test_switching_the_network_off_cuts_off_the_devices_that_came_in_by_it(tmp_path: Path, away: None) -> None:
    e = await served(tmp_path, NETWORK)
    cookie = cookie_of(await log_in(e))
    remote = await e.ws(cookie=cookie)
    await remote.until(lambda: len(remote.of("state")) == 10)
    await remote.send({"cmd": "set_config", "values": {"web/network": "false"}})
    await remote.until(lambda: remote.closed_with is not None)
    assert remote.closed_with is not None and remote.closed_with[0] == 1008
    assert (await e.fetch("/access", headers={"Cookie": cookie})).code == 401 and await refused_at_the_socket(e, cookie=cookie) == 401
    assert e.ctl.config.web_network is False


async def test_a_database_with_a_web_bind_that_was_open_comes_up_on_the_network_with_a_key(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    e = await served(tmp_path, {"web/bind": "*"})
    assert e.ctl.config.web_network is True and KEY_FORM.match(e.ctl.config.web_key)
    assert listening_on(e) <= {"0.0.0.0", "::"}
    assert await e.ctl.store.setting("web/network") == "true" and await e.ctl.store.setting("web/key") == e.ctl.config.web_key


async def test_the_address_the_page_listens_on_that_is_taken_leaves_the_old_one_listening(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    e = await served(tmp_path)
    assert e.server is not None and e.server._server is not None
    real = e.server._bind

    def refuse_all_interfaces(server: object, port: int) -> OSError | None:
        return OSError(98, "Address already in use") if e.server is not None and e.server.address == "" else real(server, port)  # type: ignore[arg-type]

    monkeypatch.setattr(e.server, "_bind", refuse_all_interfaces)
    page = await e.ws()
    await page.until(lambda: len(page.of("state")) == 10)
    await page.send({"cmd": "set_config", "values": {"web/network": "true"}})
    await until(lambda: any("cannot listen" in r.getMessage() for r in caplog.records))
    assert e.server.address == "127.0.0.1" and (await e.fetch("/")).code == 200 and listening_on(e) == {"127.0.0.1"}


# ---- names -----------------------------------------------------------------------------------------------------------------------------------------

async def test_with_the_network_on_the_page_opens_by_the_address_and_the_name_of_this_computer_and_not_by_a_foreign_name(tmp_path: Path) -> None:
    e = await served(tmp_path, NETWORK)
    name = socket.gethostname().lower()
    for host in (f"{LAN}:{e.port}", LAN, name, f"{name}:{e.port}", f"{name}.local", f"{name}.local:{e.port}", "[fe80::1]:7303"):
        assert (await e.fetch("/", headers={"Host": host})).code == 200, host
    for host in ("evil.example", f"{name}.evil.example", "pi.example"):
        assert (await e.fetch("/", headers={"Host": host})).code == 403, host


# ---- what the addresses are ------------------------------------------------------------------------------------------------------------------------

def test_the_address_of_this_computer_on_the_network_is_the_one_the_system_would_send_from(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(answer: str, status: int = 0) -> Callable[..., object]:
        class Sock:
            def __init__(self, *args: object) -> None:
                pass

            def __enter__(self) -> "Sock":
                return self

            def __exit__(self, *exc: object) -> None:
                return None

            def connect_ex(self, address: tuple[str, int]) -> int:
                return status

            def getsockname(self) -> tuple[str, int]:
                return answer, 0
        return Sock

    monkeypatch.setattr(addresses.socket, "socket", fake("192.168.1.20"))
    assert addresses.lan_addresses() == ["192.168.1.20"]
    monkeypatch.setattr(addresses.socket, "socket", fake("192.168.1.20", status=101))
    assert addresses.lan_addresses() == [], "no route"
    monkeypatch.setattr(addresses.socket, "socket", fake("127.0.0.1"))
    assert addresses.lan_addresses() == []
