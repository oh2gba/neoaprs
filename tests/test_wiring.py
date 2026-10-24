"""The wiring (neoaprs/wiring.py) with the whole daemon around it, the radio a fake one on the loopback: the capture of the TH-D7 fills the database and the station book, a restart finds the stations
again, the cable pulled and put back, pruning and a change of the port in the settings. The port the search found being remembered is in tests/test_wiring_pty.py."""
import logging
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from neoaprs import ax25, kiss
from neoaprs.config import DEFAULTS
from neoaprs.packet import Position
from neoaprs.source import Source
from neoaprs.tncprofile import KENWOOD_TNC2, KISS, KISS_TCP
from neoaprs.wiring import tnc_settings
from tests.support.env import Env, idle_for, until

FIXED_ORDER = ["OH2RDG", "OH2RDK-7", "OH2RDS", "OH2PU-9"]         # the calls of the capture, in the order it came


def frame_bytes(source: str, info: bytes = b"!6010.00N/02456.00E>hello") -> bytes:
    return kiss.encode(ax25.encode(ax25.Frame(ax25.Address("APRS"), ax25.Address.parse(source), (ax25.Address.parse("WIDE1-1"),), info=info)))


async def others(e: Env) -> list[str]:
    """The calls of the station rows in the database but ours."""
    return [s.call for s in await e.stations() if s.call != e.ctl.config.station_call]


async def test_the_whole_capture_gives_four_packets_and_four_stations_in_the_database_and_in_the_book(tmp_path: Path) -> None:
    e = Env(tmp_path)
    await e.start()
    assert await e.play() == 4
    packets = await e.packets()
    assert [p.source for p in reversed(packets)] == FIXED_ORDER and all(p.direction == "in" and isinstance(p.decoded, Position) for p in packets)
    rows = [s for s in await e.stations() if not s.is_me and s.call != "OH2GBA"]
    assert sorted(s.call for s in rows) == sorted(FIXED_ORDER) and all(s.has_position and s.packets == 1 for s in rows)
    book = [s for s in e.ctl.stationbook.stations() if not s.is_me]
    assert sorted(s.call for s in book) == sorted(FIXED_ORDER) and all(s.has_position for s in book)
    assert e.ctl.packetlog.dropped == 0
    await e.stop()


async def test_a_new_controller_on_the_same_folder_shows_the_stations_again(tmp_path: Path) -> None:
    first = Env(tmp_path)
    await first.start()
    await first.play()
    await first.stop()
    second = Env(tmp_path)
    await second.start()
    book = {s.call: s for s in second.ctl.stationbook.stations()}
    assert sorted(book) == sorted(["OH2GBA", *FIXED_ORDER])
    assert book["OH2RDK-7"].has_position and book["OH2RDK-7"].packets == 1 and book["OH2RDK-7"].last_comment == "432.500 MHz" and book["OH2RDK-7"].last_path == ("OH2RCH-2*", "TRACE2-1")
    assert book["OH2GBA"].is_me and not book["OH2RDG"].is_me
    assert len(await second.packets()) == 4
    await second.play()
    assert len(await second.packets()) == 8 and second.ctl.stationbook.get("OH2RDK-7").packets == 2  # type: ignore[union-attr]
    await second.stop()


async def test_a_packet_from_a_station_we_know_updates_its_row(tmp_path: Path) -> None:
    e = Env(tmp_path)
    await e.start()
    e.feed(frame_bytes("OH2AAA", b"!6010.00N/02456.00E>first"))
    await until(lambda: e.tnc.stats.packets == 1)
    e.now.advance(60)                                              # type: ignore[attr-defined]
    e.feed(frame_bytes("OH2AAA", b"!6011.00N/02457.00E>second"))
    await until(lambda: e.tnc.stats.packets == 2)
    [row] = [s for s in await e.stations() if s.call == "OH2AAA"]
    assert (row.packets, row.last_comment) == (2, "second") and row.last_heard > row.first_heard
    await e.stop()


async def test_what_we_send_is_in_the_packet_log_and_not_in_the_book(tmp_path: Path) -> None:
    e = Env(tmp_path)
    await e.start()
    await e.until_connected()
    await e.until_usable()                                       # (the settle time of entering KISS is not in play: nothing was said in command mode)
    frame = ax25.Frame(ax25.Address("APRS"), ax25.Address.parse("OH2GBA"), (), info=b"!6010.00N/02456.00E-NeoAPRS")
    assert e.tnc.send_frame(frame)
    [sent] = await e.packets()
    assert sent.direction == "out" and sent.source == "OH2GBA"
    assert e.ctl.stationbook.get("OH2GBA").packets == 0  # type: ignore[union-attr]
    await e.stop()


async def test_every_packet_is_logged_as_the_line_and_what_it_is(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.packets")
    e = Env(tmp_path)
    await e.start()
    await e.play()
    lines = [r.getMessage() for r in caplog.records if r.name == "neoaprs.packets"]
    assert len(lines) == 4 and lines[1] == "OH2RDK-7>APRX29,OH2RCH-2*,TRACE2-1:!6009.90NT02456.80E&432.500 MHz -> position 60.1650 24.9467 T& 432.500 MHz"
    await e.stop()


async def test_the_cable_pulled_makes_the_tnc_wait_and_the_cable_put_back_makes_it_connected_again(tmp_path: Path) -> None:
    e = Env(tmp_path)
    await e.start()
    await e.play()
    e.unplug()
    await until(lambda: e.tnc.state is Source.State.WAITING)
    assert any("lost" in line for line in e.tnc.lines)
    assert len(await e.packets()) == 4 and e.ctl.running
    await e.plug()
    await e.until_connected()
    assert e.tnc.stats.opens == 2
    e.feed(frame_bytes("OH2NEW"))
    await until(lambda: e.tnc.stats.packets == 5)
    assert len(await e.packets()) == 5 and "OH2NEW" in await others(e)
    await e.stop()


async def test_prune_removes_the_old_packets_and_stations_and_keeps_the_new_and_ours(tmp_path: Path) -> None:
    e = Env(tmp_path)
    await e.start()
    await e.play()
    e.now.advance(5 * 86400)                                      # type: ignore[attr-defined]
    e.feed(frame_bytes("OH2NEW"))
    await until(lambda: e.tnc.stats.packets == 5)
    e.now.advance(4 * 86400)                                       # type: ignore[attr-defined]
    count, stations = await e.ctl.prune()
    assert count == 4 and sorted(stations) == sorted(FIXED_ORDER)
    assert [p.source for p in await e.packets()] == ["OH2NEW"]
    assert sorted(s.call for s in await e.stations()) == ["OH2GBA", "OH2NEW"] and e.ctl.stationbook.get("OH2RDG") is None and e.ctl.stationbook.get("OH2GBA") is not None
    assert await e.ctl.prune() == (0, [])
    await e.stop()


async def test_prune_keeps_seven_days_whatever_an_earlier_version_stored(tmp_path: Path) -> None:
    e = Env(tmp_path, settings={"log/keep_days": "400"})
    await e.start()
    await e.play()
    e.now.advance(6 * 86400)                                       # type: ignore[attr-defined]
    assert await e.ctl.prune() == (0, [])
    e.now.advance(2 * 86400)                                       # type: ignore[attr-defined]
    count, stations = await e.ctl.prune()
    assert count == 4 and sorted(stations) == sorted(FIXED_ORDER)
    await e.stop()


async def test_prune_removes_the_stations_not_heard_for_the_days_kept_whatever_the_operator_said_of_them_and_their_preferences_stay(tmp_path: Path) -> None:
    e = Env(tmp_path)
    await e.start()
    await e.play()
    await e.ctl.prefbook.set_path("OH2RDG", "WIDE2-1")
    await e.ctl.prefbook.set_rf_only("OH2RDK-7", True)
    e.now.advance(5 * 86400)                                       # type: ignore[attr-defined]
    e.feed(frame_bytes("OH2NEW"))
    await until(lambda: e.tnc.stats.packets == 5)
    e.now.advance(4 * 86400)                                       # type: ignore[attr-defined]
    count, stations = await e.ctl.prune()
    assert count == 4 and sorted(stations) == sorted(["OH2RDG", "OH2RDK-7", "OH2RDS", "OH2PU-9"])
    assert [p.source for p in await e.packets()] == ["OH2NEW"]
    assert sorted(s.call for s in await e.stations()) == ["OH2GBA", "OH2NEW"]
    assert sorted(e.ctl.prefbook.all()) == ["OH2RDG", "OH2RDK-7"], "what the operator said stays when the station goes"
    await e.stop()


async def test_the_daily_task_prunes_once_at_the_start(tmp_path: Path) -> None:
    first = Env(tmp_path)
    await first.start()
    await first.play()
    await first.stop()
    later = Env(tmp_path)
    later.now.advance(40 * 86400)                                  # type: ignore[attr-defined]
    await later.start()
    await until(lambda: later.ctl.stationbook.get("OH2RDG") is None)
    assert await later.packets() == [] and [s.call for s in await later.stations()] == ["OH2GBA"]
    await later.stop()


async def test_a_change_of_the_serial_port_in_the_settings_restarts_the_tnc(tmp_path: Path) -> None:
    e = Env(tmp_path, radio=False, operator=False)
    first_radio, second_radio = await e.new_radio(), await e.new_radio()
    first, second = first_radio.url, second_radio.url
    await e.start()
    assert e.tnc.state is Source.State.WAITING and e.ctl.config == DEFAULTS
    assert await e.ctl.save_config(replace(e.ctl.config, serial_port=first))
    await until(lambda: e.tnc.state is Source.State.CONNECTED and e.tnc.path == first)
    assert (await e.ctl.store.settings())["serial/port"] == first and e.tnc.port == first
    opens = e.tnc.stats.opens
    assert await e.ctl.save_config(replace(e.ctl.config, station_comment="a changed comment"))
    await idle_for(0.2)
    assert e.tnc.stats.opens == opens and e.tnc.state is Source.State.CONNECTED, "a setting the Tnc does not use leaves it alone"
    assert await e.ctl.save_config(replace(e.ctl.config, serial_port=second))
    await until(lambda: e.tnc.state is Source.State.CONNECTED and e.tnc.path == second)
    assert e.tnc.stats.opens == opens + 1
    assert await e.ctl.save_config(replace(e.ctl.config, serial_baud=4800))
    await until(lambda: e.tnc.state is Source.State.CONNECTED and e.tnc.baud == 4800 and e.tnc.stats.opens == opens + 2)
    assert (first_radio.connections, second_radio.connections) == (1, 2)
    await e.stop()
    again = Env(tmp_path, radio=False)
    await again.start(connected=False)
    assert again.ctl.config.serial_port == second and again.ctl.config.serial_baud == 4800 and again.ctl.config.station_comment == "a changed comment"
    await again.stop()


async def test_a_change_of_our_call_and_position_is_put_in_force_at_once(tmp_path: Path) -> None:
    e = Env(tmp_path, radio=False)
    await e.start(connected=False)
    me = e.ctl.stationbook.me
    assert me is not None and (me.call, me.lat, me.lon) == ("OH2GBA", 60.17, 24.94)
    assert await e.ctl.save_config(replace(e.ctl.config, station_call="OH2GBA-9", station_lat=61.0, station_lon=25.0))
    me = e.ctl.stationbook.me
    assert me is not None and (me.call, me.lat, me.lon) == ("OH2GBA-9", 61.0, 25.0) and not e.ctl.stationbook.get("OH2GBA").is_me  # type: ignore[union-attr]
    await e.stop()


async def test_a_save_before_the_database_is_open_changes_nothing(tmp_path: Path) -> None:
    e = Env(tmp_path, radio=False)
    assert not await e.ctl.save_config(replace(e.ctl.config, serial_baud=4800)) and e.ctl.config == DEFAULTS


async def test_a_port_given_for_this_run_is_used_alone_and_never_stored(tmp_path: Path) -> None:
    e = Env(tmp_path, operator=False)                              # the Env's radio is given as the controller's port, like --port
    await e.start()
    assert e.tnc.path == e.link and e.tnc.port == e.link and not e.tnc.fallback_probe
    await idle_for(0.1)
    assert await e.ctl.store.settings() == {} and e.ctl.config.serial_last_port == ""
    await e.stop()


def test_the_settings_become_the_tncs(search_pattern_from_settings: None) -> None:
    assert tnc_settings(DEFAULTS) == ("", 9600, KISS, True, (), "/dev/serial/by-id/* /dev/ttyUSB* /dev/ttyACM*")
    assert tnc_settings(replace(DEFAULTS, serial_last_port="/dev/brainbox_3")).port == "/dev/brainbox_3"
    assert tnc_settings(replace(DEFAULTS, serial_port="/dev/ttyUSB0", serial_last_port="/dev/brainbox_3", serial_baud=1200, tnc_profile="kenwood-tnc2")) == ("/dev/ttyUSB0", 1200, KENWOOD_TNC2, True, (), DEFAULTS.serial_pattern)
    assert tnc_settings(replace(DEFAULTS, serial_port="/dev/ttyUSB0"), "/dev/pts/4") == ("/dev/pts/4", 9600, KISS, False, (), DEFAULTS.serial_pattern)
    assert tnc_settings(replace(DEFAULTS, serial_skip="/dev/brainbox_2, /dev/ttyUSB5")).skip == ("/dev/brainbox_2", "/dev/ttyUSB5")
    assert tnc_settings(replace(DEFAULTS, serial_pattern="/dev/brainbox_*")).pattern == "/dev/brainbox_*"
    assert tnc_settings(DEFAULTS, pattern_override="/tmp/probe_*").pattern == "/tmp/probe_*"


def test_a_tcp_profile_connects_to_the_host_and_port_and_never_searches(search_pattern_from_settings: None) -> None:
    tcp = replace(DEFAULTS, tnc_profile="kiss-tcp")
    assert tnc_settings(tcp) == ("socket://127.0.0.1:8001", 9600, KISS_TCP, False, (), DEFAULTS.serial_pattern)
    assert tnc_settings(replace(tcp, tcp_host="pi.local", tcp_port=8100, serial_last_port="/dev/ttyUSB0")).port == "socket://pi.local:8100"
    assert tnc_settings(replace(tcp, tcp_host="::1")).port == "socket://[::1]:8001"
    assert tnc_settings(replace(tcp, serial_port="tcp://10.0.0.5:8100")).port == "tcp://10.0.0.5:8100", "an address in serial/port is the one used"
    assert tnc_settings(replace(tcp, serial_port="/dev/ttyUSB0")).port == "socket://127.0.0.1:8001", "(a serial device is refused when saved; a row edited by hand is not followed)"
    assert replace(DEFAULTS, tnc_profile="kenwood-tnc2", serial_port="socket://localhost:7000").profile.transport == "serial"
    assert tnc_settings(replace(DEFAULTS, tnc_profile="kenwood-tnc2", serial_port="socket://localhost:7000")).port == "socket://localhost:7000", "a serial profile on a socket works"


async def test_the_start_takes_the_time_the_clock_says(tmp_path: Path) -> None:
    e = Env(tmp_path)
    await e.start()
    await e.play()
    [row] = [s for s in await e.stations() if s.call == "OH2RDG"]
    assert row.first_heard == row.last_heard == e.now() and row.last_position_at == e.now() - timedelta(0)
    await e.stop()
