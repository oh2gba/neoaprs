"""The https side of the web server (neoaprs/web/secureside.py) on its own, with the real certificates of the test's folder and servers that do not serve a page: starting, keeping and stopping the listener, what the page is
told when the certificates cannot be made or loaded, a certificate that cannot be renewed while the old one is in use, a port that is picked by the system, and a close that is not clean. The secure page through the whole
daemon is in tests/test_web_https.py."""
import asyncio
import ssl
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import tornado.web

from neoaprs.web import secureside
from neoaprs.web.connections import LimitedHTTPServer
from neoaprs.web.listen import PORT_TRIES
from neoaprs.web.secureside import RECHECK_SEC, RETRY_SEC, SecureSide, SecureState, _bound, ports_after
from neoaprs.web.tls import Certificates, TlsError
from tests.support.clock import FixedClock
from tests.support.env import remember_stop

LAN = "192.168.1.20"
PLAIN_PORT = 7303


def factory(context: ssl.SSLContext) -> LimitedHTTPServer:
    return LimitedHTTPServer(tornado.web.Application(), ssl_options=context)


@pytest.fixture(autouse=True)
def lan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(secureside, "lan_addresses", lambda: [LAN])


def made(tmp_path: Path) -> SecureSide:
    side = SecureSide(tmp_path / "tls", FixedClock(), lambda: [])
    remember_stop(side.close)
    return side


class FakeCertificates:
    """What the certificate store gives, or raises: the side asks it for the certificates and nothing else."""

    def __init__(self, result: Certificates | BaseException) -> None:
        self.result = result

    def ensure(self, host: str, addresses: Any, more: Any = ()) -> Certificates:
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


async def test_a_listener_is_started_kept_and_stopped_as_the_wish_goes_and_the_page_is_told_only_when_something_changed(tmp_path: Path) -> None:
    side = made(tmp_path)
    assert side.port == 0 and side.ca_der is None and side.retry_sec == RECHECK_SEC
    assert await side.follow(True, "127.0.0.1", PLAIN_PORT, factory) is True
    assert side.state.on and PLAIN_PORT < side.port <= PLAIN_PORT + PORT_TRIES and side.ca_der is not None and side.state.fingerprint
    server, before = side.server, side.state
    assert await side.follow(True, "127.0.0.1", PLAIN_PORT, factory) is False, "the same wish changes nothing"
    assert side.server is server and side.state == before, "and the same certificate is not loaded again"
    assert await side.follow(False, "127.0.0.1", PLAIN_PORT, factory) is True
    assert side.state == SecureState() and side.server is None and side.ca_der is None and side.port == 0
    assert await side.follow(False, "127.0.0.1", PLAIN_PORT, factory) is False


@pytest.mark.expects_errors
async def test_a_library_that_fails_in_a_way_nobody_listed_is_a_problem_for_the_page_and_the_plain_page_goes_on(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    side = made(tmp_path)
    side._store = FakeCertificates(RuntimeError("the library broke"))      # type: ignore[assignment]
    assert await side.follow(True, "127.0.0.1", PLAIN_PORT, factory) is True
    assert side.state == SecureState(False, 0, "", "the certificates could not be made: the library broke") and side.server is None and side.retry_sec == RETRY_SEC
    assert any("the secure connection is not working" in r.getMessage() for r in caplog.records) and any(r.exc_info for r in caplog.records)


@pytest.mark.expects_errors
@pytest.mark.parametrize("what, problem", [("missing", "the certificate cannot be loaded"), ("garbage", "the certificate cannot be loaded")])
async def test_a_certificate_that_cannot_be_loaded_is_a_problem_for_the_page_and_nothing_listens(tmp_path: Path, what: str, problem: str) -> None:
    side = made(tmp_path)
    chain, key = tmp_path / "chain.pem", tmp_path / "key.pem"
    if what == "garbage":
        chain.write_text("not a certificate")
        key.write_text("not a key")
    expires = datetime(2030, 1, 1)
    side._store = FakeCertificates(Certificates(b"der", "AB:CD", chain, key, ("localhost",), expires))      # type: ignore[assignment]
    await side.follow(True, "127.0.0.1", PLAIN_PORT, factory)
    assert side.state.on is False and side.state.problem.startswith(problem) and side.server is None


@pytest.mark.expects_errors
async def test_a_certificate_that_cannot_be_renewed_leaves_the_one_in_use_in_use_and_tells_the_page_why(tmp_path: Path) -> None:
    side = made(tmp_path)
    await side.follow(True, "127.0.0.1", PLAIN_PORT, factory)
    port, fingerprint = side.state.port, side.state.fingerprint
    side._store = FakeCertificates(TlsError("the clock of this computer is not set; the secure connection starts when it is"))      # type: ignore[assignment]
    assert await side.follow(True, "127.0.0.1", PLAIN_PORT, factory) is True
    assert side.state == SecureState(True, port, fingerprint, "the clock of this computer is not set; the secure connection starts when it is")
    assert side.server is not None and side.retry_sec == RETRY_SEC, "still served, and looked at again soon"


async def test_with_no_port_to_try_after_the_plain_one_the_system_gives_one_and_it_is_the_one_told(tmp_path: Path) -> None:
    assert ports_after(65535) == [0] and ports_after(7303) == list(range(7304, 7314))
    side = made(tmp_path)
    await side.follow(True, "127.0.0.1", 65535, factory)
    assert side.state.on and side.state.port not in (0, 65535)
    assert side.server is not None and _bound(side.server) == side.state.port


def test_a_server_that_does_not_listen_is_bound_to_no_port() -> None:
    assert _bound(factory(ssl.create_default_context())) == 0


@pytest.mark.parametrize("error", [asyncio.TimeoutError(), RuntimeError("a connection that will not go")])
async def test_a_close_that_does_not_end_cleanly_is_not_the_closers_trouble(tmp_path: Path, error: Exception) -> None:
    side = made(tmp_path)
    await side.follow(True, "127.0.0.1", PLAIN_PORT, factory)
    assert side.server is not None

    async def refuses() -> None:
        raise error

    side.server.close_all_connections = refuses                  # type: ignore[method-assign]
    await side.close()
    assert side.server is None and not side.state.on
