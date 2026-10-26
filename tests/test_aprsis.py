"""The connection to APRS-IS (neoaprs/aprsis.py) against a fake server on the loopback: the greeting, the login line with its filter and the read-only login, `# logresp` verified and unverified, a server that is not APRS-IS or says
nothing, the keep-alive both ways, the lines of the server read as packets of the internet (and the ones that are none counted), the write queue, the reconnection with the back-off, and the password that is in the login line and nowhere else."""
import asyncio
import logging

import pytest

from neoaprs import PROGRAM, VERSION
from neoaprs.aprsis import MAX_LINE, NO_SERVER, UNVERIFIED, AprsIs, login_line, logresp_of, range_filter
from neoaprs.packet import IS, Packet
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

def test_the_login_line_has_the_call_the_passcode_and_the_program_and_the_filter_when_there_is_one() -> None:
    assert login_line(CALL, PASSWORD) == f"user {CALL} pass {PASSWORD} vers {PROGRAM} {VERSION}\r\n".encode()
    assert login_line(CALL, PASSWORD, "r/60.17/24.94/150") == f"user {CALL} pass {PASSWORD} vers {PROGRAM} {VERSION} filter r/60.17/24.94/150\r\n".encode()


def test_no_passcode_is_the_read_only_login() -> None:
    assert login_line(CALL, "") == f"user {CALL} pass -1 vers {PROGRAM} {VERSION}\r\n".encode()


def test_the_filter_is_the_circle_of_the_given_radius_round_the_position_to_a_hundredth_of_a_degree() -> None:
    assert range_filter(60.1699, 24.9384, 150) == "r/60.17/24.94/150" and range_filter(-33.8688, 151.2093, 50) == "r/-33.87/151.21/50"


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


async def test_a_passcode_the_server_does_not_accept_is_told_sends_nothing_is_not_tried_again_and_the_connection_listens() -> None:
    server = await fake_aprsis(verified=False)
    link = link_to(server)
    await link.start()
    await until(lambda: link.unverified)
    assert link.state is Source.State.CONNECTED and link.listening and not link.verified and any(UNVERIFIED in line for line in link.lines)
    assert link.send_line(b"OH2XYZ>APRS:>x") is False
    heard: list[Packet] = []
    link.heard.connect(heard.append)
    server.send(b"OH2ABC>APRS,TCPIP*,qAC,T2TEST:>still read")
    await until(lambda: heard)
    await idle_for(0.4)                                          # (the back-off is 50 ms: a retry would have come)
    assert server.connections == 1 and server.packets == []


async def test_no_passcode_is_the_read_only_login_and_the_unverified_answer_to_it_is_no_fault() -> None:
    server = await fake_aprsis(verified=False)
    link = link_to(server, password="")
    await link.start()
    await until(lambda: link.listening)
    assert not link.unverified and link.read_only and not link.verified and link.state is Source.State.CONNECTED
    assert server.logins == [f"user {CALL} pass -1 vers {PROGRAM} {VERSION}"] and link.send_line(b"OH2XYZ>APRS:>x") is False
    await idle_for(0.2)
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
    ("", PASSWORD, "127.0.0.1", "set your call first"), ("N0CALL", PASSWORD, "127.0.0.1", "placeholder"), (CALL, PASSWORD, "", NO_SERVER)])
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


async def test_what_the_server_sends_keeps_the_connection_comments_are_ignored_and_a_line_is_a_packet_of_the_internet() -> None:
    server = await fake_aprsis()
    link = link_to(server, lost_sec=0.3)
    heard: list[Packet] = []
    link.heard.connect(heard.append)
    await link.start()
    await until(lambda: link.verified)
    for _ in range(8):
        server.send(b"# aprsc keepalive")
        server.send(b"OH2XYZ>APRS,TCPIP*,qAC,T2TEST::OH2GBA-10 :hello{1}")
        await idle_for(0.1)
    assert server.connections == 1 and link.verified
    assert len(heard) == 8 and link.read == 8 and link.unreadable == 0
    assert {(p.via, p.direction, p.source, p.path) for p in heard} == {(IS, "in", "OH2XYZ", ("TCPIP*", "qAC", "T2TEST"))}


async def test_a_line_that_is_no_packet_is_counted_and_never_raised_and_the_connection_goes_on() -> None:
    server = await fake_aprsis()
    link = link_to(server)
    heard: list[Packet] = []
    link.heard.connect(heard.append)
    await link.start()
    await until(lambda: link.verified)
    for junk in (b"no header at all", b"OH2XYZ>:no destination", b"\xff\xfe>APRS:binary", b"OH2XYZ>APRS:", b"X" * 3000):
        server.send(junk)
    server.send(b"OH2XYZ>APRS,qAC,T2TEST:>fine")
    await until(lambda: heard)
    assert link.unreadable == 5 and link.read == 1 and link.verified and server.connections == 1


async def test_a_line_whose_handler_fails_does_not_end_the_connection(caplog: pytest.LogCaptureFixture) -> None:
    server = await fake_aprsis()
    link = link_to(server)

    def fails(packet: Packet) -> None:
        raise RuntimeError("the handler is broken")

    link.heard.connect(fails)
    await link.start()
    await until(lambda: link.verified)
    with caplog.at_level(logging.ERROR):
        server.send(b"OH2XYZ>APRS,qAC,T2TEST:>one")
        server.send(b"OH2XYZ>APRS,qAC,T2TEST:>two")
        await until(lambda: link.read == 2)
    assert link.verified and server.connections == 1 and "handler is broken" in caplog.text


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


# ---- the filter

async def test_the_filter_is_in_the_login_and_a_changed_one_is_sent_as_a_comment_line() -> None:
    server = await fake_aprsis()
    link = link_to(server)
    link.set_filter("r/60.17/24.94/150")
    await link.start()
    await until(lambda: link.verified)
    assert server.logins == [f"user {CALL} pass {PASSWORD} vers {PROGRAM} {VERSION} filter r/60.17/24.94/150"]
    link.set_filter("r/60.17/24.94/150")                           # (the same: nothing is sent)
    link.set_filter("r/61.50/23.76/150")
    await until(lambda: "#filter r/61.50/23.76/150" in server.comments)
    assert server.comments.count("#filter r/61.50/23.76/150") == 1 and "#filter r/60.17/24.94/150" not in server.comments and server.packets == []


async def test_a_filter_set_between_the_login_line_and_the_answer_to_it_is_sent_when_the_answer_comes() -> None:
    server = await fake_aprsis(answer=False)
    link = link_to(server, password="", login_sec=2.0)
    await link.start()
    await until(lambda: server.logins)
    assert "filter" not in server.logins[0]
    link.set_filter("r/60.17/24.94/150")                           # (the login line is written, the state is not connected yet: the filter is kept, not queued)
    assert not link._queue
    server.send(f"# logresp {CALL} unverified, server {server.name}".encode())
    await until(lambda: "#filter r/60.17/24.94/150" in server.comments)
    assert link.listening and server.packets == []


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


# ---- the edges: an open that never ends, a socket that cannot be set, a login answer after other lines, a line too long, a run that is not the current one

class OtherSocket:
    """What a stream's writer says its socket is, when it is not the usual one: nothing, or one whose options cannot be set."""

    def __init__(self, sock: object) -> None:
        self.sock = sock

    def wrap(self, writer: asyncio.StreamWriter) -> object:
        sock = self.sock

        class Proxy:
            transport = writer.transport

            def get_extra_info(self, name: str, default: object = None) -> object:
                return sock if name == "socket" else writer.get_extra_info(name, default)

            def __getattr__(self, name: str) -> object:
                return getattr(writer, name)

        return Proxy()


class RefusingSocket:
    def setsockopt(self, *args: object) -> None:
        raise OSError("option not supported")


@pytest.mark.parametrize("sock", [None, RefusingSocket()], ids=["no socket to set", "a socket that refuses the options"])
async def test_a_connection_whose_socket_cannot_be_set_is_still_a_connection(monkeypatch: pytest.MonkeyPatch, sock: object) -> None:
    server = await fake_aprsis()
    real = asyncio.open_connection

    async def open_connection(host: str, port: int, **options: int) -> tuple[asyncio.StreamReader, object]:
        reader, writer = await real(host, port, **options)
        return reader, OtherSocket(sock).wrap(writer)

    monkeypatch.setattr(asyncio, "open_connection", open_connection)
    link = link_to(server)
    await link.start()
    await until(lambda: link.verified)
    assert link.send_line(b"OH2XYZ>APRS:>x")
    await until(lambda: server.packets == ["OH2XYZ>APRS:>x"])


async def test_an_open_that_does_not_end_in_time_is_a_problem_and_a_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[int] = []

    async def hangs(host: str, port: int, **options: int) -> None:
        opened.append(port)
        await asyncio.sleep(3600)

    monkeypatch.setattr(asyncio, "open_connection", hangs)
    link = link_to(await fake_aprsis(), connect_sec=0.1)
    await link.start()
    await until(lambda: len(opened) >= 2)
    assert "no answer in time" in link.last_error


async def test_lines_before_the_answer_to_the_login_are_passed_over() -> None:
    server = await fake_aprsis()
    server.responder = lambda line: b"# some news of the server\r\nOH2XYZ>APRS:>not the answer\r\n# logresp OH2GBA-10 verified, server LATE\r\n" if line.startswith("user ") else b""
    link = link_to(server)
    await link.start()
    await until(lambda: link.verified)
    assert link.server_name == "LATE" and link.read == 0, "(a packet in front of the answer is not a packet of the internet either: the login is not served yet)"


async def test_a_line_longer_than_the_reader_takes_is_a_lost_connection_and_the_next_login_works() -> None:
    server = await fake_aprsis()
    link = link_to(server)
    await link.start()
    await until(lambda: link.verified)
    server.send(b"x" * 9000)
    await until(lambda: "too long" in link.last_error)
    await until(lambda: link.verified and server.connections == 2)


async def test_a_run_that_is_not_the_current_one_ends_without_touching_the_state() -> None:
    link = link_to(await fake_aprsis())
    link._generation = 5
    await link._run(4)                                                   # (a task of a start that a stop has replaced since: it must not connect)
    assert link.state is Source.State.STOPPED and link.stats.opens == 0

    class Replaced(AprsIs):
        async def _attempt(self) -> str | None:
            self._generation += 1                                        # (stopped and started again while the attempt failed)
            return "the connection ended"

    other = Replaced(FixedClock(), Backoff([0.05]))
    await other._run(0)
    assert other.state is Source.State.STOPPED and other.last_error == ""
