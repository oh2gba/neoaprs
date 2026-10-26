"""The connection to APRS-IS (neoaprs/aprsis.py) against a fake server on the loopback: the greeting, the login line, `# logresp` verified and unverified, a server that is not APRS-IS or says nothing, the keep-alive both ways,
the write queue, the reconnection with the back-off, and the password that is in the login line and nowhere else."""
import asyncio
import logging

import pytest

from neoaprs import PROGRAM, VERSION
from neoaprs.aprsis import MAX_LINE, NO_PASSWORD, NO_SERVER, UNVERIFIED, AprsIs, login_line, logresp_of
from neoaprs.source import Backoff, Source
from tests.support.clock import FixedClock
from tests.support.env import idle_for, remember_stop, until
from tests.support.fakeaprsis import FakeAprsIs, fake_aprsis

CALL = "OH2GBA-10"
PASSWORD = "19628"


def link_to(server: FakeAprsIs, call: str = CALL, password: str = PASSWORD, **options: float) -> AprsIs:
    link = AprsIs(FixedClock(), Backoff([0.05]), **{"connect_sec": 1.0, "greeting_sec": 0.4, "login_sec": 0.4, "lost_sec": 5.0, "quiet_sec": 5.0, **options})        # type: ignore[arg-type]
    host, _, port = server.address.rpartition(":")
    link.configure(host, int(port), call, password)
    remember_stop(link.stop)
    return link


# ---- the lines

def test_the_login_line_has_the_call_the_passcode_and_the_program_and_no_filter() -> None:
    assert login_line(CALL, PASSWORD) == f"user {CALL} pass {PASSWORD} vers {PROGRAM} {VERSION}\r\n".encode()
    assert b"filter" not in login_line(CALL, PASSWORD)


@pytest.mark.parametrize(("line", "want"), [
    (b"# logresp OH2GBA-10 verified, server T2FINLAND\r\n", (True, "T2FINLAND")),
    (b"# logresp OH2GBA-10 unverified, server T2FINLAND\r\n", (False, "T2FINLAND")),
    (b"# logresp N0CALL unverified\r\n", (False, "")),
    (b"#logresp oh2gba verified, server t2x\n", (True, "t2x")),
    (b"# aprsc 2.1.19-g730c5c0\r\n", None),
    (b"OH2XYZ>APRS:>status\r\n", None),
    (b"# logresp OH2GBA-10 verifiedish\r\n", None),
])
def test_the_answer_to_the_login(line: bytes, want: tuple[bool, str] | None) -> None:
    assert logresp_of(line) == want


# ---- the login

async def test_a_verified_login_connects_and_the_login_line_is_the_only_thing_the_server_got() -> None:
    server = await fake_aprsis()
    link = link_to(server)
    await link.start()
    await until(lambda: link.verified)
    assert link.state is Source.State.CONNECTED and link.server_name == server.name and not link.unverified
    await until(lambda: server.logins)
    assert server.logins == [f"user {CALL} pass {PASSWORD} vers {PROGRAM} {VERSION}"] and server.received == server.logins
    assert link.describe() == f"APRS-IS at {server.address}"
    await link.stop()
    assert link.state is Source.State.STOPPED and not link.verified


async def test_an_unverified_login_closes_the_connection_sends_nothing_and_is_not_tried_again() -> None:
    server = await fake_aprsis(verified=False)
    link = link_to(server)
    await link.start()
    await until(lambda: link.unverified)
    assert link.state is Source.State.WAITING and link.problem == UNVERIFIED and not link.verified
    assert link.send_line(b"OH2XYZ>APRS:>x") is False
    await idle_for(0.4)                                          # (the back-off is 50 ms: a retry would have come)
    assert server.connections == 1 and server.packets == []


async def test_the_login_is_tried_again_when_the_settings_change_after_an_unverified_one() -> None:
    server = await fake_aprsis(verified=False)
    link = link_to(server)
    await link.start()
    await until(lambda: link.unverified)
    server.verified = True
    link.configure(*server.address.rpartition(":")[::2], CALL, "1")        # type: ignore[arg-type]
    await link.start()
    await until(lambda: link.verified)
    assert server.connections == 2 and not link.unverified


async def test_a_server_that_greets_with_something_else_is_not_logged_in_to_and_is_tried_again() -> None:
    server = await fake_aprsis(greeting=b"SSH-2.0-OpenSSH_9.2\r\n")
    link = link_to(server)
    await link.start()
    await until(lambda: link.last_error and server.connections >= 2)
    assert "not an APRS-IS server" in link.last_error and "SSH-2.0" in link.last_error
    assert server.logins == [] and not link.verified


async def test_a_server_that_says_nothing_is_given_up_and_tried_again() -> None:
    server = await fake_aprsis(silent=True)
    link = link_to(server)
    await link.start()
    await until(lambda: server.connections >= 2)
    assert "said nothing" in link.last_error and server.logins == []


async def test_a_server_that_does_not_answer_the_login_is_given_up_and_tried_again() -> None:
    server = await fake_aprsis(answer=False)
    link = link_to(server)
    await link.start()
    await until(lambda: server.connections >= 2)
    assert "did not answer the login" in link.last_error and not link.verified


async def test_a_server_that_hangs_up_is_logged_in_to_again() -> None:
    server = await fake_aprsis()
    link = link_to(server)
    await link.start()
    await until(lambda: link.verified)
    server.hang_up()
    await until(lambda: not link.verified)
    assert link.state is Source.State.WAITING
    await until(lambda: link.verified and server.connections == 2)
    assert link.state is Source.State.CONNECTED


async def test_a_refused_connection_is_a_problem_and_a_retry() -> None:
    server = await fake_aprsis()
    link = link_to(server)
    await server.stop()
    await link.start()
    await until(lambda: link.last_error)
    assert link.last_error.startswith(server.address) and not link.verified
    await link.stop()


@pytest.mark.parametrize(("call", "password", "host", "problem"), [
    ("", PASSWORD, "127.0.0.1", "set your call first"), ("N0CALL", PASSWORD, "127.0.0.1", "placeholder"), (CALL, "", "127.0.0.1", NO_PASSWORD), (CALL, PASSWORD, "", NO_SERVER)])
async def test_what_is_missing_is_said_and_nothing_is_opened(call: str, password: str, host: str, problem: str) -> None:
    server = await fake_aprsis()
    link = link_to(server, call, password)
    link.host = host
    await link.start()
    assert link.state is Source.State.CONNECTING and problem in link.problem and not link._tasks
    await idle_for(0.1)
    assert server.connections == 0 and link.send_line(b"x") is False


# ---- the keep-alive

async def test_a_connection_that_has_written_nothing_for_two_minutes_sends_a_comment() -> None:
    server = await fake_aprsis()
    link = link_to(server, quiet_sec=0.15)
    await link.start()
    await until(lambda: len(server.comments) >= 2)
    assert server.comments[0] == f"# {PROGRAM} {VERSION}" and server.packets == [] and link.verified
    assert link.stats.packets == 0, "(a comment is no packet)"


async def test_a_connection_the_server_has_said_nothing_on_for_three_minutes_is_lost_and_opened_again() -> None:
    server = await fake_aprsis()
    link = link_to(server, lost_sec=0.3)
    await link.start()
    await until(lambda: server.connections >= 2)
    assert "nothing from the server" in link.last_error


async def test_what_the_server_sends_keeps_the_connection_and_is_thrown_away() -> None:
    server = await fake_aprsis()
    link = link_to(server, lost_sec=0.3)
    await link.start()
    await until(lambda: link.verified)
    for _ in range(8):
        server.send(b"# aprsc keepalive")
        server.send(b"OH2XYZ>APRS::OH2GBA-10 :hello{1}")
        await idle_for(0.1)
    assert server.connections == 1 and link.verified


async def test_a_write_the_server_does_not_take_is_a_lost_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    server = await fake_aprsis()
    link = link_to(server, write_sec=0.2)
    await link.start()
    await until(lambda: link.verified)

    async def never(self: asyncio.StreamWriter) -> None:
        await asyncio.sleep(3600)

    monkeypatch.setattr(asyncio.StreamWriter, "drain", never)
    assert link.send_line(b"OH2XYZ>APRS:>x")
    await until(lambda: not link.verified)
    assert "does not take" in link.last_error


# ---- writing

async def test_a_line_reaches_the_server_with_a_line_end_and_in_order() -> None:
    server = await fake_aprsis()
    link = link_to(server)
    await link.start()
    await until(lambda: link.verified)
    lines = [f"OH2XYZ>APRS,qAO,{CALL}:>status {n}".encode() for n in range(5)]
    assert all(link.send_line(line) for line in lines)
    await until(lambda: len(server.packets) == 5)
    assert server.packets == [line.decode() for line in lines] and link.stats.packets == 5 and link.stats.bytes_out > 5 * 30


async def test_a_line_that_cannot_be_a_line_of_aprs_is_is_refused() -> None:
    server = await fake_aprsis()
    link = link_to(server)
    await link.start()
    await until(lambda: link.verified)
    assert not link.send_line(b"OH2XYZ>APRS:one\r\ntwo") and not link.send_line(b"OH2XYZ>APRS:one\ntwo") and not link.send_line(b"x" * (MAX_LINE - 1))
    assert link.send_line(b"x" * (MAX_LINE - 2))
    await until(lambda: server.packets)


def test_a_slow_server_costs_the_oldest_lines_and_never_more_than_the_queue_holds() -> None:
    link = AprsIs(FixedClock(), queue_max=3)
    link.verified = True                                        # (no connection: the lines stay where they are queued)
    for n in range(5):
        assert link.send_line(f"line {n}".encode())
    assert list(link._queue) == [b"line 2", b"line 3", b"line 4"] and link.slow_dropped == 2


async def test_lines_queued_before_a_loss_are_not_sent_after_the_next_login() -> None:
    server = await fake_aprsis()
    link = link_to(server)
    await link.start()
    await until(lambda: link.verified)
    server.hang_up()
    await until(lambda: not link.verified)
    assert not link.send_line(b"OH2XYZ>APRS:>late") and not link._queue


# ---- the password

async def test_the_password_is_in_the_login_line_and_in_no_log_line_note_or_error(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    server = await fake_aprsis()
    link = link_to(server, password="31415")
    await link.start()
    await until(lambda: link.verified)
    server.hang_up()
    await until(lambda: not link.verified)
    await until(lambda: link.verified)
    bad = await fake_aprsis(verified=False)
    other = link_to(bad, password="27182")
    await other.start()
    await until(lambda: other.unverified)
    await link.stop()
    await other.stop()
    for secret in ("31415", "27182"):
        assert secret not in caplog.text
        assert all(secret not in line for line in (*link.lines, *other.lines, link.problem, link.last_error, other.problem, other.last_error, link.describe()))
    assert any("31415" in login for login in server.logins)
