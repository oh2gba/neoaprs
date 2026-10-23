"""The beacon (neoaprs/services/beacon.py) inside the whole daemon, the radio a pseudo-terminal: the timer and a request put a KISS frame on the line, the packet log has it as a packet we sent, the
station book does not take it as a station we heard, a frame that comes back (the TNC's echo, a digipeater's copy) only moves the time we were last heard, and the controller starts and stops it."""
import asyncio
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from neoaprs import TOCALL, ax25, kiss
from neoaprs.packet import Position
from neoaprs.source import Source
from tests.support.env import Env, until

INFO = b"=6010.20N/02456.40E-mobile"


async def started(tmp_path: Path, **changes: object) -> Env:
    """A daemon whose radio is connected and settled, with the settings changed as asked and the beacon's timer ticking quickly."""
    e = Env(tmp_path)
    e.ctl.beacon.tick_sec, e.ctl.beacon.retry_sec = 0.02, 0.05
    await e.start()
    await asyncio.sleep(0.2)                                                # (the TNC has settled: nothing was said in command mode)
    assert await e.ctl.save_config(replace(e.ctl.config, station_comment="mobile", **changes))      # type: ignore[arg-type]
    return e


async def on_the_line(e: Env) -> ax25.Frame:
    """The frame the radio was sent."""
    [frame] = kiss.KissDecoder().feed(await e.heard(1, 2.0))
    return ax25.decode(frame.payload)


async def test_the_timer_sends_the_beacon_when_the_clock_says_so_and_it_is_a_kiss_frame_of_ours(tmp_path: Path) -> None:
    e = await started(tmp_path, beacon_interval_min=1)
    first = e.ctl.beacon.next_due
    assert first == e.now() + timedelta(seconds=30)
    e.now.advance(29)                                                       # type: ignore[attr-defined]
    await asyncio.sleep(0.1)
    assert e.ctl.beacon.last_sent is None
    e.now.advance(1)                                                        # type: ignore[attr-defined]
    await until(lambda: e.ctl.beacon.last_sent is not None)
    frame = await on_the_line(e)
    assert (str(frame.source), str(frame.destination), frame.path_text, frame.info) == ("OH2GBA", "APZNEO", "WIDE1-1,WIDE2-1", INFO) and frame.is_ui
    assert e.ctl.beacon.last_reason == "interval" and e.ctl.beacon.next_due == e.now() + timedelta(minutes=1)
    await e.stop()


async def test_the_beacon_is_in_the_packet_log_as_a_packet_we_sent_and_the_book_does_not_take_it(tmp_path: Path) -> None:
    e = await started(tmp_path)
    assert e.ctl.beacon.send_now()
    [sent] = await e.packets()
    assert (sent.direction, sent.source, sent.destination, sent.path, sent.info) == ("out", "OH2GBA", "APZNEO", ("WIDE1-1", "WIDE2-1"), INFO)
    assert isinstance(sent.decoded, Position) and (sent.decoded.lat, sent.decoded.lon) == (60.17, 24.94) and sent.decoded.comment == "mobile" and sent.decoded.messaging
    me = e.ctl.stationbook.me
    assert me is not None and me.packets == 0 and me.is_me and (me.symbol_table, me.symbol_code, me.last_comment) == ("/", "-", "mobile")
    [row] = [s for s in await e.stations() if s.call == "OH2GBA"]
    assert (row.symbol_table, row.symbol_code, row.last_comment, row.packets) == ("/", "-", "mobile", 0), "our row carries the symbol and the comment of the settings, in the cache too"
    await e.stop()


async def test_the_beacon_on_the_line_is_to_the_tocall_with_the_plain_position(tmp_path: Path) -> None:
    e = await started(tmp_path)
    assert e.ctl.beacon.send_now()
    frame = await on_the_line(e)
    assert str(frame.destination) == TOCALL and frame.info[:2] == b"=6" and len(frame.info) == 1 + 19 + len("mobile") and b"!W" not in frame.info
    [sent] = await e.packets()
    assert isinstance(sent.decoded, Position) and not sent.decoded.compressed
    await e.stop()


async def test_our_own_beacon_coming_back_in_moves_only_the_time_we_were_last_heard(tmp_path: Path) -> None:
    e = await started(tmp_path)
    assert e.ctl.beacon.send_now()
    wire = await e.heard(1, 2.0)
    me = e.ctl.stationbook.me
    assert me is not None
    sent_at = me.last_heard
    e.now.advance(45)                                                       # type: ignore[attr-defined]
    e.feed(wire)                                                            # (the TNC echoes what it transmits, or a digipeater repeats it)
    await until(lambda: e.tnc.stats.packets == 1)
    assert me.last_heard == e.now() > sent_at
    assert (me.lat, me.lon, me.packets, me.last_path, me.track, me.last_comment) == (60.17, 24.94, 0, (), [], "mobile")
    both = await e.packets()
    assert sorted(p.direction for p in both) == ["in", "out"]
    await e.stop()


async def test_a_beacon_that_falls_due_with_the_cable_pulled_waits_and_is_sent_when_it_is_back(tmp_path: Path) -> None:
    e = await started(tmp_path, beacon_interval_min=1)
    e.unplug()
    await until(lambda: e.tnc.state is Source.State.WAITING)
    started_at = e.now()
    e.now.advance(30)                                                       # type: ignore[attr-defined]
    await asyncio.sleep(0.2)
    assert e.ctl.beacon.next_due == started_at + timedelta(seconds=30), "left where it was"
    assert e.ctl.beacon.last_sent is None and not e.ctl.beacon.send_now() and "not connected" in e.ctl.beacon.problem
    await e.plug()
    await until(lambda: e.ctl.beacon.last_sent is not None)                 # (the Tnc refuses the frame while it settles: tried again)
    assert (await on_the_line(e)).info == INFO and e.ctl.beacon.next_due == e.now() + timedelta(minutes=1)
    await e.stop()


async def test_saving_the_settings_puts_a_new_interval_in_force_and_zero_stops_it(tmp_path: Path) -> None:
    e = await started(tmp_path, beacon_interval_min=10)
    assert e.ctl.beacon.next_due == e.now() + timedelta(seconds=30)
    assert await e.ctl.save_config(replace(e.ctl.config, beacon_interval_min=0))
    assert e.ctl.beacon.next_due is None
    e.now.advance(7200)                                                     # type: ignore[attr-defined]
    await asyncio.sleep(0.15)
    assert e.ctl.beacon.last_sent is None and await e.packets() == []
    assert await e.ctl.save_config(replace(e.ctl.config, beacon_interval_min=5))
    await until(lambda: e.ctl.beacon.last_sent is not None)                 # (the first beacon was due long ago)
    assert e.ctl.beacon.next_due == e.now() + timedelta(minutes=5)
    await e.stop()


async def test_reconnecting_the_tnc_leaves_the_beacon_alone(tmp_path: Path) -> None:
    e = await started(tmp_path, beacon_interval_min=10)
    before = (e.ctl.beacon.last_sent, e.ctl.beacon.next_due)
    e.ctl.start_tnc()
    await until(lambda: e.tnc.stats.opens == 2 and e.tnc.state is Source.State.CONNECTED)
    assert (e.ctl.beacon.last_sent, e.ctl.beacon.next_due) == before
    await e.stop()


async def test_the_controller_stops_the_timer(tmp_path: Path) -> None:
    e = await started(tmp_path, beacon_interval_min=10)
    assert e.ctl.beacon.next_due is not None
    await e.stop()
    assert e.ctl.beacon.next_due is None
    e.now.advance(7200)                                                     # type: ignore[attr-defined]
    await asyncio.sleep(0.1)
    assert e.ctl.beacon.last_sent is None
