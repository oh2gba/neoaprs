"""The GPS feed (neoaprs/gpsfeed.py): a gpsd on the loopback that is asked to watch and tells TPV and SKY, and a serial receiver (here a TCP serial server, `socket://`) that sends NMEA; the state and the problem the
way the TNC reports them, the reconnection after a loss, and a feed that never raises into the loop."""
import asyncio
import logging

import sys

import pytest

from neoaprs.gpsfeed import NO_ADDRESS, NO_FIX, NO_PORT, GpsFeed, _GpsPort, split_address
from neoaprs.gpsfix import Fix
from neoaprs.source import Backoff, Source
from tests.support.clock import FixedClock
from tests.support.env import remember_stop, until
from tests.support.gps import FakeGpsd, fake_gpsd, gga, rmc, sky, tpv
from tests.support.ptyline import posix_only


def feed_of(kind: str, target: str, baud: int = 4800) -> tuple[GpsFeed, list[Fix], FixedClock]:
    clock = FixedClock()
    feed = GpsFeed(clock, Backoff([0.05]), connect_sec=1.0)
    feed.configure(kind, target, baud)
    fixes: list[Fix] = []
    feed.fixed.connect(fixes.append)
    remember_stop(feed.stop)
    return feed, fixes, clock


async def free_port() -> int:
    server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    port = int(server.sockets[0].getsockname()[1])
    server.close()
    await server.wait_closed()
    return port


@pytest.mark.parametrize(("text", "want"), [("127.0.0.1:2947", ("127.0.0.1", 2947)), ("localhost:1", ("localhost", 1)), ("[::1]:2947", ("::1", 2947)), (" gps.lan:65535 ", ("gps.lan", 65535))])
def test_the_address_of_a_gpsd_is_host_and_port(text: str, want: tuple[str, int]) -> None:
    assert split_address(text) == want


@pytest.mark.parametrize("text", ["", "gps", ":2947", "host:0", "host:65536", "host:x", "[]:2947"])
def test_an_address_that_is_not_host_and_port_is_refused(text: str) -> None:
    with pytest.raises(ValueError):
        split_address(text)


@pytest.mark.parametrize(("kind", "problem"), [("serial", NO_PORT), ("gpsd", NO_ADDRESS)])
async def test_a_source_without_its_port_or_address_opens_nothing_and_says_what_to_give(kind: str, problem: str, monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[object] = []

    async def no_connection(*args: object, **kwargs: object) -> None:
        opened.append(args)
        raise AssertionError("nothing may be connected to")

    async def no_open(self: object) -> None:
        opened.append(self)
        raise AssertionError("nothing may be opened")

    monkeypatch.setattr(asyncio, "open_connection", no_connection)
    monkeypatch.setattr("neoaprs.gpsfeed._GpsPort.open", no_open)
    feed, fixes, _ = feed_of(kind, "")
    await feed.start()
    assert feed.state is Source.State.CONNECTING and feed.problem == problem and feed.describe() == ""
    assert not feed._tasks and not opened and not fixes
    feed.configure(kind, "  ", 4800)
    await feed.start()
    assert feed.state is Source.State.CONNECTING and feed.problem == problem and not opened


# ---- gpsd

async def test_a_feed_of_nothing_is_never_started() -> None:
    feed, _, _ = feed_of("off", "")
    await feed.start()
    assert feed.state is Source.State.STOPPED and not feed._tasks


async def test_the_feed_asks_gpsd_to_watch_and_hands_on_the_fixes_with_the_satellites_of_the_sky() -> None:
    gpsd = await fake_gpsd()
    feed, fixes, clock = feed_of("gpsd", gpsd.address)
    await feed.start()
    await until(lambda: feed.state is Source.State.CONNECTED and gpsd.watching)
    assert gpsd.received == ['?WATCH={"enable":true,"json":true}'] and feed.describe() == f"gpsd at {gpsd.address}"
    gpsd.send(sky(used=8))
    gpsd.send(tpv(60.43, 24.145, speed=15.0, track=269.6))
    await until(lambda: fixes)
    assert fixes == [Fix(60.43, 24.145, clock(), pytest.approx(54.0), 270, 31.4, 8)]            # type: ignore[list-item]
    assert feed.fix == fixes[0] and feed.fix_age_sec == 0.0 and feed.stats.packets == 1
    clock.advance(30)
    assert feed.fix_age_sec == 30.0


async def test_a_report_without_a_fix_is_a_problem_to_show_and_the_fix_comes_back_clear() -> None:
    gpsd = await fake_gpsd()
    feed, fixes, _ = feed_of("gpsd", gpsd.address)
    await feed.start()
    await until(lambda: gpsd.watching)
    gpsd.send(tpv(None, None, mode=1))
    await until(lambda: feed.problem == NO_FIX)
    assert feed.state is Source.State.CONNECTED and not fixes
    gpsd.send(tpv(60.43, 24.145))
    await until(lambda: fixes)
    assert feed.problem == ""


async def test_the_latest_fix_is_kept_when_the_receiver_then_says_it_has_none() -> None:
    gpsd = await fake_gpsd()
    feed, fixes, _ = feed_of("gpsd", gpsd.address)
    await feed.start()
    await until(lambda: gpsd.watching)
    gpsd.send(tpv(60.43, 24.145))
    await until(lambda: fixes)
    gpsd.send(tpv(None, None, mode=1))
    await until(lambda: feed.problem == NO_FIX)
    assert feed.fix == fixes[0], "the service that uses it judges how old it is"


async def test_what_is_not_json_is_counted_and_the_feed_goes_on() -> None:
    gpsd = await fake_gpsd()
    feed, fixes, _ = feed_of("gpsd", gpsd.address)
    await feed.start()
    await until(lambda: gpsd.watching)
    gpsd.send_raw(b"this is not json\n[1, 2]\n")
    gpsd.send(tpv(60.43, 24.145))
    await until(lambda: fixes)
    assert feed.stats.rejected == 2


async def test_a_gpsd_that_is_not_there_is_a_problem_and_tried_again_until_it_is() -> None:
    port = await free_port()
    feed, fixes, _ = feed_of("gpsd", f"127.0.0.1:{port}")
    await feed.start()
    why = "no answer in time" if sys.platform == "win32" else "refused"          # (Windows takes about two seconds to refuse a connection: longer than the feed of a test waits)
    await until(lambda: feed.state is Source.State.WAITING and why in feed.problem.lower())
    gpsd = await FakeGpsd().start_on(port)                                 # the gpsd is started at last, on the port the feed has been trying
    await until(lambda: feed.state is Source.State.CONNECTED, 3.0)
    assert feed.problem == ""
    await until(lambda: gpsd.watching)
    gpsd.send(tpv(60.43, 24.145))
    await until(lambda: fixes)


async def test_a_gpsd_that_hangs_up_is_reconnected_with_the_back_off() -> None:
    gpsd = await fake_gpsd()
    feed, fixes, _ = feed_of("gpsd", gpsd.address)
    await feed.start()
    await until(lambda: gpsd.watching)
    gpsd.hang_up()
    await until(lambda: feed.state is Source.State.WAITING)
    assert "hung up" in feed.problem
    await until(lambda: feed.state is Source.State.CONNECTED and gpsd.connections == 2)
    assert feed.problem == ""
    await until(lambda: len([line for line in gpsd.received if line.startswith("?WATCH")]) == 2)
    gpsd.send(tpv(60.43, 24.145))
    await until(lambda: fixes)


async def test_stopping_closes_the_connection_and_forgets_the_fix() -> None:
    gpsd = await fake_gpsd()
    feed, fixes, _ = feed_of("gpsd", gpsd.address)
    await feed.start()
    await until(lambda: gpsd.watching)
    gpsd.send(tpv(60.43, 24.145))
    await until(lambda: fixes)
    await feed.stop()
    assert feed.state is Source.State.STOPPED and feed.fix is None and not feed._tasks


@pytest.mark.expects_errors
async def test_a_handler_that_fails_does_not_stop_the_feed(caplog: pytest.LogCaptureFixture) -> None:
    gpsd = await fake_gpsd()
    feed, fixes, _ = feed_of("gpsd", gpsd.address)

    def bad(fix: Fix) -> None:
        raise RuntimeError("a bug in a handler")
    feed.fixed.connect(bad)
    await feed.start()
    await until(lambda: gpsd.watching)
    with caplog.at_level(logging.ERROR):
        gpsd.send(tpv(60.43, 24.145))
        gpsd.send(tpv(60.44, 24.146))
        await until(lambda: len(fixes) == 2)
    assert feed.state is Source.State.CONNECTED


# ---- a serial receiver

async def test_a_serial_receiver_is_read_as_nmea_lines_cut_from_the_bytes() -> None:
    port = await fake_gpsd(greet=False)
    feed, fixes, clock = feed_of("serial", port.url)
    await feed.start()
    await until(lambda: feed.state is Source.State.CONNECTED and port.connections)
    assert feed.describe() == f"GPS on {port.url}"
    data = (rmc(60.43, 24.145, 27.0, 270.0) + gga(60.43, 24.145)).encode()
    port.send_raw(data[:20])                                                   # (a line arrives in pieces)
    port.send_raw(data[20:75])
    port.send_raw(data[75:] + rmc(60.4301, 24.1451, 27.0, 271.0).encode())
    await until(lambda: len(fixes) == 2)
    assert fixes[0] == Fix(pytest.approx(60.43, abs=1e-6), pytest.approx(24.145, abs=1e-6), clock(), pytest.approx(27.0 * 1.852), 270, None, None)        # type: ignore[arg-type]
    assert fixes[1].altitude_m == 31.4 and fixes[1].satellites == 9 and fixes[1].course_deg == 271


async def test_the_speed_of_a_serial_port_is_part_of_what_it_says_of_itself() -> None:
    feed, _, _ = feed_of("serial", "/dev/ttyUSB1", 9600)
    assert feed.describe() == "GPS on /dev/ttyUSB1 at 9600"


async def test_a_receiver_that_has_no_fix_is_a_problem_and_a_damaged_sentence_is_counted() -> None:
    port = await fake_gpsd(greet=False)
    feed, fixes, _ = feed_of("serial", port.url)
    await feed.start()
    await until(lambda: port.connections)
    port.send_raw(rmc(0, 0, valid=False).encode())
    await until(lambda: feed.problem == NO_FIX)
    port.send_raw(b"$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*00\r\n")
    await until(lambda: feed.stats.rejected == 1)
    assert not fixes
    port.send_raw(rmc(60.43, 24.145, 1.0, 10.0).encode())
    await until(lambda: fixes)
    assert feed.problem == ""


async def test_bytes_that_are_not_nmea_do_not_grow_without_end() -> None:
    port = await fake_gpsd(greet=False)
    feed, fixes, _ = feed_of("serial", port.url)
    await feed.start()
    await until(lambda: port.connections)
    port.send_raw(b"\x00\xff" * 4000)
    await until(lambda: feed.stats.rejected >= 1)
    assert len(feed._pending) < 4096
    port.send_raw(b"\n" + rmc(60.43, 24.145, 1.0, 10.0).encode())
    await until(lambda: fixes)


async def test_a_serial_port_that_hangs_up_is_opened_again() -> None:
    port = await fake_gpsd(greet=False)
    feed, fixes, _ = feed_of("serial", port.url)
    await feed.start()
    await until(lambda: port.connections == 1 and feed.state is Source.State.CONNECTED)
    port.hang_up()
    await until(lambda: feed.state is Source.State.WAITING or port.connections == 2)
    await until(lambda: port.connections == 2 and feed.state is Source.State.CONNECTED, 3.0)
    port.send_raw(rmc(60.43, 24.145, 1.0, 10.0).encode())
    await until(lambda: fixes)


async def test_a_serial_port_that_cannot_be_opened_is_a_problem_in_the_words_of_the_system() -> None:
    port = await free_port()
    feed, _, _ = feed_of("serial", f"socket://127.0.0.1:{port}")
    await feed.start()
    await until(lambda: feed.state is Source.State.WAITING)
    assert "refused" in feed.problem.lower() and feed.last_error == feed.problem


# ---- the edges: an open that ends after the feed was stopped, one that never ends, a report that says nothing twice, and what a stale part may not do

class Gate:
    """An open that waits for the test: `entered` is set when it is under way, `let` ends the wait."""

    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.let = asyncio.Event()

    async def wait(self) -> None:
        self.entered.set()
        await self.let.wait()


class StaleReader:
    """A gpsd's reader that gives one line, or fails."""

    def __init__(self, line: bytes = b"", fail: BaseException | None = None) -> None:
        self.line, self.fail = line, fail

    async def readline(self) -> bytes:
        if self.fail is not None:
            raise self.fail
        return self.line


def test_a_feed_of_a_kind_that_reads_nothing_says_nothing_of_itself() -> None:
    feed, _, _ = feed_of("off", "127.0.0.1:2947")
    assert feed.describe() == ""
    feed.configure("serial", "  ", 4800)
    assert feed.describe() == ""


async def test_a_gpsd_that_does_not_answer_the_connection_in_time_is_a_problem_and_a_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    tried: list[int] = []

    async def hangs(host: str, port: int) -> None:
        tried.append(port)
        await asyncio.sleep(3600)

    monkeypatch.setattr(asyncio, "open_connection", hangs)
    feed, _, _ = feed_of("gpsd", "127.0.0.1:2947")
    feed.connect_sec = 0.1
    await feed.start()
    await until(lambda: len(tried) >= 2)
    assert "no answer in time" in feed.last_error


async def test_a_start_that_is_cancelled_while_it_connects_is_not_turned_into_a_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    gate = Gate()

    async def hangs(host: str, port: int) -> None:
        await gate.wait()

    monkeypatch.setattr(asyncio, "open_connection", hangs)
    feed, _, _ = feed_of("gpsd", "127.0.0.1:2947")
    starting = asyncio.create_task(feed.start())
    await gate.entered.wait()
    starting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await starting
    assert feed.state is Source.State.CONNECTING and feed.problem == ""


async def test_a_gpsd_connection_that_fails_after_the_feed_was_stopped_is_not_a_problem_of_the_stopped_feed(monkeypatch: pytest.MonkeyPatch) -> None:
    gate = Gate()

    async def fails_late(host: str, port: int) -> None:
        await gate.wait()
        raise OSError("connection refused")

    monkeypatch.setattr(asyncio, "open_connection", fails_late)
    feed, _, _ = feed_of("gpsd", "127.0.0.1:2947")
    starting = asyncio.create_task(feed.start())
    await gate.entered.wait()
    await feed.stop()
    gate.let.set()
    await starting
    assert feed.state is Source.State.STOPPED and feed.problem == ""


@posix_only                                                                      # (Windows: see the commit "five new tests are POSIX only for now")
async def test_a_gpsd_connection_that_comes_after_the_feed_was_stopped_is_closed_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    gpsd = await fake_gpsd()
    gate = Gate()
    real = asyncio.open_connection

    async def late(host: str, port: int) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        await gate.wait()
        return await real(host, port)

    monkeypatch.setattr(asyncio, "open_connection", late)
    feed, _, _ = feed_of("gpsd", gpsd.address)
    starting = asyncio.create_task(feed.start())
    await gate.entered.wait()
    await feed.stop()
    gate.let.set()
    await starting
    assert feed.state is Source.State.STOPPED and feed._writer is None
    await until(lambda: gpsd.clients and gpsd.clients[0].is_closing() or not gpsd.clients, 3.0)
    assert not gpsd.watching, "(it was never asked to watch)"


async def test_a_serial_port_that_opens_after_the_feed_was_stopped_is_closed_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    gate = Gate()
    closed: list[str] = []

    async def late(self: object) -> None:
        await gate.wait()

    monkeypatch.setattr("neoaprs.gpsfeed._GpsPort.open", late)
    monkeypatch.setattr("neoaprs.gpsfeed._GpsPort.close", lambda self: closed.append(self.path))                    # type: ignore[attr-defined]
    feed, _, _ = feed_of("serial", "/dev/ttyUSB-fake", 4800)
    starting = asyncio.create_task(feed.start())
    await gate.entered.wait()
    await feed.stop()
    gate.let.set()
    await starting
    assert feed.state is Source.State.STOPPED and feed._port is None and "/dev/ttyUSB-fake" in closed


async def test_the_retry_of_a_feed_that_was_stopped_since_connects_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    feed, _, _ = feed_of("gpsd", "127.0.0.1:1")
    feed._generation = 3
    await feed._retry(0.0, 2)
    assert feed.state is Source.State.STOPPED and feed.stats.opens == 0


async def test_a_reader_of_a_connection_that_is_not_the_feeds_any_more_ends_quietly() -> None:
    feed, fixes, _ = feed_of("gpsd", "127.0.0.1:1")
    feed._generation = 3
    aborted: list[bool] = []

    class Transport:
        def abort(self) -> None:
            aborted.append(True)

    class Writer:
        transport = Transport()

    await feed._read_gpsd(StaleReader(b'{"class":"TPV"}\n'), Writer(), 2)                       # type: ignore[arg-type]
    await feed._read_gpsd(StaleReader(fail=OSError("reset")), Writer(), 2)                      # type: ignore[arg-type]
    assert fixes == [] and aborted == [] and feed.state is Source.State.STOPPED and feed.stats.bytes_in == 0


async def test_bytes_and_a_loss_from_a_port_that_is_not_the_feeds_are_ignored() -> None:
    feed, fixes, _ = feed_of("serial", "/dev/ttyUSB1")
    stranger = _GpsPort("/dev/ttyUSB2", 4800, lambda p, c: None, lambda p, r: None)
    feed._on_data(stranger, rmc(60.43, 24.145).encode())
    feed._on_lost(stranger, "unplugged")
    assert fixes == [] and feed.stats.bytes_in == 0 and feed.state is Source.State.STOPPED


@pytest.mark.expects_errors
async def test_a_fix_whose_signal_fails_is_logged_and_the_feed_goes_on(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    port = await fake_gpsd(greet=False)
    feed, fixes, _ = feed_of("serial", port.url)
    await feed.start()
    await until(lambda: port.connections)
    handled: list[Fix] = []

    def broken(fix: Fix) -> None:
        handled.append(fix)
        raise RuntimeError("the handler is broken")

    monkeypatch.setattr(feed.fixed, "emit", broken)
    port.send_raw(rmc(60.43, 24.145, 1.0, 10.0).encode())
    await until(lambda: handled)
    assert "gps: the fix was not taken" in caplog.text and feed.fix is handled[0] and feed.state is Source.State.CONNECTED


async def test_a_receiver_that_says_it_has_no_fix_twice_is_told_once_and_one_that_is_not_connected_is_not_blamed(monkeypatch: pytest.MonkeyPatch) -> None:
    port = await fake_gpsd(greet=False)
    feed, _, _ = feed_of("serial", port.url)
    await feed.start()
    await until(lambda: port.connections)
    told: list[str] = []
    set_problem = feed._set_problem
    monkeypatch.setattr(feed, "_set_problem", lambda text: (told.append(text), set_problem(text)))
    port.send_raw(rmc(0, 0, valid=False).encode() * 2)
    await until(lambda: feed.problem == NO_FIX and feed.stats.bytes_in >= 2 * len(rmc(0, 0, valid=False)))
    assert told == [NO_FIX]
    idle, _, _ = feed_of("serial", "/dev/ttyUSB1")
    idle._no_fix()
    assert idle.problem == "", "(a feed that is not connected is not blamed for a fix it never waited for)"
