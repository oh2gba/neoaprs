"""What one failing round or one hostile request must not do to the web server: end a timer for
good, fill or forge the log, answer 500 to a body that is not JSON."""
import asyncio
import logging
import socket
from pathlib import Path

import pytest

from neoaprs.web import secureside
from tests.support.env import Env, until
from tests.test_web_access import NETWORK, away, cookie_of, lan, log_in, served  # noqa: F401
from tests.test_secureside import PLAIN_PORT, factory, made


@pytest.mark.expects_errors
async def test_the_status_timer_goes_on_after_a_round_that_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("neoaprs.web.api.STATUS_EVERY_SEC", 0.05)
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    await page.until(lambda: len(page.of("status")) >= 1)
    real, calls = e.ctl.packetlog.count, []

    async def count_but_fail_once() -> int:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("the database hiccups")
        return await real()

    e.ctl.packetlog.count = count_but_fail_once                  # type: ignore[method-assign]
    await until(lambda: len(calls) >= 3)
    e.ctl.packetlog.count = real                                 # type: ignore[method-assign]


@pytest.mark.expects_errors
async def test_the_secure_side_check_goes_on_after_a_round_that_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(secureside, "RECHECK_SEC", 0.05)
    e = Env(tmp_path, web=True)
    await e.start()
    assert e.server is not None
    calls: list[int] = []

    async def fail_once(quiet: bool = False) -> None:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("a round that fails")

    e.server._follow_secure = fail_once                          # type: ignore[method-assign]
    await until(lambda: len(calls) >= 3)


@pytest.mark.expects_errors
async def test_a_long_path_and_a_line_separator_in_a_path_are_one_short_line_of_the_log(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    e = await served(tmp_path)
    caplog.set_level(logging.WARNING)
    for raw in (b"/" + b"a" * 60000, b"/x\x85A", b"/x\xe2\x80\xa8A"):
        s = socket.create_connection(("127.0.0.1", e.port))
        s.sendall(b"GET " + raw + b" HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
        await asyncio.get_running_loop().run_in_executor(None, s.recv, 100)
        s.close()
    lines = [r.getMessage() for r in caplog.records if " GET " in r.getMessage()]
    assert len(lines) == 3
    assert all(len(line) < 300 and len(line.splitlines()) == 1 for line in lines)


@pytest.mark.expects_errors
async def test_a_body_nested_too_deep_is_a_bad_request_and_no_error_of_the_log(tmp_path: Path, away: None, caplog: pytest.LogCaptureFixture) -> None:  # noqa: F811
    e = await served(tmp_path, NETWORK)
    assert (await e.fetch("/access", method="POST", body="[" * 30000)).code == 400
    cookie = cookie_of(await log_in(e))
    assert (await e.fetch("/support/bundle", method="POST", body="[" * 100000, headers={"Cookie": cookie})).code == 400
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


async def test_the_connections_of_the_secure_port_end_when_the_secure_side_is_turned_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    side = made(tmp_path)
    monkeypatch.setattr(secureside, "lan_addresses", lambda: ["192.168.1.20"])
    await side.follow(True, "127.0.0.1", PLAIN_PORT, factory)
    assert side.server is not None
    closed: list[int] = []

    async def closes() -> None:
        closed.append(1)

    side.server.close_all_connections = closes                   # type: ignore[method-assign]
    await side.follow(False, "127.0.0.1", PLAIN_PORT, factory)
    assert closed == [1] and side.server is None
