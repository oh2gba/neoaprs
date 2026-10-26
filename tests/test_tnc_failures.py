"""The Tnc (neoaprs/tnc.py) on a line in memory (tests/support/fakeport.py) and on a loop whose time is skipped (tests/support/virtualtime.py): what a real line does badly, which a socket does not do on cue.
An open that fails or raises something nobody listed, a write that is refused, a line that is lost while the Tnc is asking, bytes and loss from a port that is no longer the Tnc's, a stop while the retry opens,
and the repeats of the KISS entry that wait longer each time (their waits are the program's own 10 s to 60 s, passed in no time)."""
import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from neoaprs import ax25
from neoaprs.serialport import SerialError
from neoaprs.source import Backoff, Source
from neoaprs.tnc import ENTER_KISS, Tnc
from tests.support.fakeport import FakePorts
from tests.support.virtualtime import virtual_time

MONITOR_LINE = b"OH2FZV-2>VP1R61,WIDE1,OH2RCH-2*:!6010.00N/02456.00E>test\r\n"
SETTLE = 0.15
PATH = "socket://fake-tnc:1"


@pytest.fixture
def ports(monkeypatch: pytest.MonkeyPatch) -> FakePorts:
    return FakePorts().install(monkeypatch)


@asynccontextmanager
async def started(**kwargs: object) -> AsyncIterator[Tnc]:
    """A Tnc on the fake ports, started (when it can be) and stopped at the end; no checks unless asked, and a back-off of 5 s and 10 s."""
    kwargs.setdefault("check_sec", 0.0)
    kwargs.setdefault("settle_sec", SETTLE)
    kwargs.setdefault("backoff", Backoff([5.0, 10.0]))
    kwargs.setdefault("fallback_probe", False)
    tnc = Tnc(PATH, **kwargs)  # type: ignore[arg-type]
    try:
        await tnc.start()
        yield tnc
    finally:
        await tnc.stop()


# ---- the open

async def test_an_open_that_is_refused_waits_and_tries_again_after_the_back_off(ports: FakePorts) -> None:
    ports.open_error = SerialError("socket://fake-tnc:1: connection refused")
    async with virtual_time() as clock, started() as tnc:
        assert tnc.state is Source.State.WAITING and "refused" in tnc.problem
        assert "trying again in 5 s" in tnc.lines[-1]
        assert tnc.describe() == f"{PATH}, waiting"
        ports.open_error = None
        await asyncio.sleep(5.5)
        assert tnc.state is Source.State.CONNECTED and len(ports.opened) == 2
        assert 5 <= clock.skipped < 6, "the retry waited its 5 s, and no more"


@pytest.mark.expects_errors
async def test_an_open_that_raises_something_nobody_listed_is_logged_and_waited_out_like_a_refusal(ports: FakePorts, caplog: pytest.LogCaptureFixture) -> None:
    ports.open_error = RuntimeError("the driver is confused")
    async with virtual_time(), started() as tnc:
        assert tnc.state is Source.State.WAITING and tnc.problem == "RuntimeError: the driver is confused"
        assert "tnc: connecting failed" in caplog.text
        ports.open_error = None
        await asyncio.sleep(5.5)
        assert tnc.state is Source.State.CONNECTED and tnc.problem == ""


async def test_a_stop_while_the_retry_is_opening_leaves_no_port_and_no_task(ports: FakePorts) -> None:
    ports.open_error = SerialError("not there")
    opening = asyncio.Event()
    never = asyncio.Event()

    async def held() -> None:
        opening.set()
        await never.wait()

    async with virtual_time(), started() as tnc:
        ports.open_error = None
        ports.open_gate = held
        await asyncio.sleep(5.5)                                      # (the retry has started its open, which does not end)
        assert opening.is_set() and tnc.state is Source.State.CONNECTING
        await tnc.stop()
        assert tnc.state is Source.State.STOPPED and not ports.port.is_open


async def test_start_on_a_tnc_that_runs_stops_it_first_and_opens_the_line_afresh(ports: FakePorts) -> None:
    async with started() as tnc:
        first = ports.port
        await tnc.start()
        assert not first.is_open and first.closes == 1
        assert ports.port is not first and ports.port.is_open and tnc.state is Source.State.CONNECTED


# ---- a line that is lost, and one that is not the Tnc's any more

async def test_bytes_and_a_loss_from_a_port_that_is_not_the_tncs_any_more_are_ignored(ports: FakePorts) -> None:
    async with virtual_time(), started() as tnc:
        old = ports.port
        old.lose("unplugged")
        assert tnc.state is Source.State.WAITING and "unplugged" in tnc.problem
        await asyncio.sleep(5.5)
        assert tnc.state is Source.State.CONNECTED and ports.port is not old
        old.feed(MONITOR_LINE)
        old.lose("again")
        assert tnc.stats.bytes_in == 0 and ports.port.written == [], "nothing the old port says is taken"
        assert tnc.state is Source.State.CONNECTED


async def test_asking_a_tnc_that_has_no_line_is_refused_and_a_reopen_of_nothing_opens_nothing(ports: FakePorts) -> None:
    tnc = Tnc(PATH, check_sec=0.0)
    assert not tnc.look_begin() and not tnc.look_send(b"\r")
    await tnc.reopen_port()
    assert ports.opened == [] and tnc.state is Source.State.STOPPED


# ---- a write that is refused

async def test_a_write_that_fails_is_told_the_line_counts_as_lost_and_the_frame_is_not_sent(ports: FakePorts) -> None:
    frame = ax25.Frame(ax25.Address("APRS"), ax25.Address.parse("OH2GBA-7"), (), info=b"!6010.00N/02456.00E>hello")
    async with virtual_time(), started() as tnc:
        ports.write_error = SerialError("the line is gone")
        assert not tnc.send_frame(frame)
        assert tnc.stats.bytes_out == 0 and tnc.state is Source.State.WAITING and "write failed: the line is gone" in "\n".join(tnc.lines)
        ports.write_error = None
        await asyncio.sleep(5.5)
        assert tnc.state is Source.State.CONNECTED and tnc.send_frame(frame), "the next line takes it"


async def test_text_from_the_radio_when_the_first_step_of_the_entry_cannot_be_written_enters_nothing(ports: FakePorts) -> None:
    async with virtual_time(), started() as tnc:
        ports.write_error = SerialError("no room")
        ports.port.feed(MONITOR_LINE)
        assert ports.port.written == [] and tnc.state is Source.State.WAITING


# ---- the repeats of the entry

async def test_the_repeats_of_the_entry_wait_longer_each_time_and_only_the_first_is_told_above_debug(ports: FakePorts, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    async with virtual_time(), started() as tnc:
        port = ports.port
        port.feed(MONITOR_LINE)
        assert port.written == [ENTER_KISS]
        for repeat, wait in enumerate((10, 20, 40, 60, 60)):                                         # the first repeat, then twice as long each time, up to the cap
            await asyncio.sleep(SETTLE + wait / 2)
            port.feed(MONITOR_LINE)
            assert len(port.written) == 1 + repeat, f"not before {wait} s have passed since the entry settled"
            await asyncio.sleep(wait / 2 + 0.05)
            port.feed(MONITOR_LINE)
            assert len(port.written) == 2 + repeat and port.written[-1] == ENTER_KISS, f"again, {wait} s after the settle"
        told = [rec.levelno for rec in caplog.records if "still in command mode" in rec.getMessage()]
        assert told == [logging.INFO, logging.DEBUG, logging.DEBUG, logging.DEBUG, logging.DEBUG]
        assert sum("still in command mode" in line for line in tnc.lines) == 5, "every repeat is a line in the terminal"
        assert not tnc.usable and "command mode" in tnc.why_unusable()
