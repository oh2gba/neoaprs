"""The wiring (neoaprs/wiring.py) with the whole daemon around it and a fake loopback radio: the
capture fills the database and station book, a restart finds the stations, the cable pulled and put
back, pruning, port changes.
"""

import asyncio
import logging
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from neoaprs import ax25, kiss, wiring
from neoaprs.claims import Claims
from neoaprs.config import DEFAULTS
from neoaprs.dummyline import DUMMY_PATH
from neoaprs.mercury import Keying
from neoaprs.mercurydriver import MercuryDriver, modem_settings
from neoaprs.mercurymodem import NOT_INSTALLED, Mercury
from neoaprs.packet import Position
from neoaprs.radiodriver import RunOverrides
from neoaprs.radioregistry import changed_words
from neoaprs.radiospec import FM_ID, HF_ID
from neoaprs.source import Backoff, Source
from neoaprs.tnc import Tnc
from neoaprs.tncdriver import TncDriver, line_settings
from neoaprs.tncprofile import DUMMY_HF, KENWOOD_TNC2, KISS, KISS_TCP, MERCURY
from tests.support.air import from_internet
from tests.support.env import Env, idle_for, until
from tests.support.radioconfig import fm_line, hf_line, hf_said
from tests.test_packetlog import from_the_internet

FIXED_ORDER = ["OH2RDG", "OH2RDK-7", "OH2RDS", "OH2PU-9"]  # the calls of the capture, in the order it came


def frame_bytes(source: str, info: bytes = b"!6010.00N/02456.00E>hello") -> bytes:
    return kiss.encode(
        ax25.encode(
            ax25.Frame(ax25.Address("APRS"), ax25.Address.parse(source), (ax25.Address.parse("WIDE1-1"),), info=info)
        )
    )


async def others(e: Env) -> list[str]:
    """The calls of the station rows in the database but ours."""
    return [s.call for s in await e.stations() if s.call != e.ctl.config.station_call]


async def test_the_whole_capture_gives_four_packets_and_four_stations_in_the_database_and_in_the_book(
    tmp_path: Path,
) -> None:
    e = Env(tmp_path)
    await e.start()
    assert await e.play() == 4
    packets = await e.packets()
    assert [p.source for p in reversed(packets)] == FIXED_ORDER and all(
        p.direction == "in" and isinstance(p.decoded, Position) for p in packets
    )
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
    assert (
        book["OH2RDK-7"].has_position
        and book["OH2RDK-7"].packets == 1
        and book["OH2RDK-7"].last_comment == "432.500 MHz"
        and book["OH2RDK-7"].last_path == ("OH2RCH-2*", "TRACE2-1")
    )
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
    e.now.advance(60)  # type: ignore[attr-defined]
    e.feed(frame_bytes("OH2AAA", b"!6011.00N/02457.00E>second"))
    await until(lambda: e.tnc.stats.packets == 2)
    [row] = [s for s in await e.stations() if s.call == "OH2AAA"]
    assert (row.packets, row.last_comment) == (2, "second") and row.last_heard > row.first_heard
    await e.stop()


async def test_what_we_send_is_in_the_packet_log_and_not_in_the_book(tmp_path: Path) -> None:
    e = Env(tmp_path)
    await e.start()
    await e.until_connected()
    # The settle time of entering KISS is not in play: nothing was said in command mode
    await e.until_usable()
    frame = ax25.Frame(ax25.Address("APRS"), ax25.Address.parse("OH2GBA"), (), info=b"!6010.00N/02456.00E-NeoAPRS")
    assert e.tnc.send_frame(frame)
    [sent] = await e.packets()
    assert sent.direction == "out" and sent.source == "OH2GBA"
    assert e.ctl.stationbook.get("OH2GBA").packets == 0  # type: ignore[union-attr]
    await e.stop()


async def test_every_packet_is_logged_as_the_line_and_what_it_is(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, "neoaprs.packets")
    e = Env(tmp_path)
    await e.start()
    await e.play()
    lines = [r.getMessage() for r in caplog.records if r.name == "neoaprs.packets"]
    assert (
        len(lines) == 4
        and lines[1]
        == "OH2RDK-7>APRX29,OH2RCH-2*,TRACE2-1:!6009.90NT02456.80E&432.500 MHz -> position 60.1650 24.9467 T& 432.500 MHz"
    )
    await e.stop()


def test_the_line_of_a_packet_of_the_internet_is_not_made_while_the_log_does_not_take_it(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    made: list[object] = []
    monkeypatch.setattr(wiring, "tnc2", lambda packet: made.append(packet) or "line")
    caplog.set_level(logging.INFO, "neoaprs.packets")
    wiring._log_packet(from_the_internet())
    assert made == [] and caplog.records == [], "debug only"
    caplog.set_level(logging.DEBUG, "neoaprs.packets")
    wiring._log_packet(from_the_internet())
    assert len(made) == 1 and [r.getMessage() for r in caplog.records if r.name == "neoaprs.packets"][0].startswith(
        "internet line"
    )


async def test_the_cable_pulled_makes_the_tnc_wait_and_the_cable_put_back_makes_it_connected_again(
    tmp_path: Path,
) -> None:
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
    e.now.advance(5 * 86400)  # type: ignore[attr-defined]
    e.feed(frame_bytes("OH2NEW"))
    await until(lambda: e.tnc.stats.packets == 5)
    e.now.advance(4 * 86400)  # type: ignore[attr-defined]
    count, stations = await e.ctl.prune()
    assert count == 4 and sorted(stations) == sorted(FIXED_ORDER)
    assert [p.source for p in await e.packets()] == ["OH2NEW"]
    assert (
        sorted(s.call for s in await e.stations()) == ["OH2GBA", "OH2NEW"]
        and e.ctl.stationbook.get("OH2RDG") is None
        and e.ctl.stationbook.get("OH2GBA") is not None
    )
    assert await e.ctl.prune() == (0, [])
    await e.stop()


async def test_prune_keeps_seven_days_whatever_an_earlier_version_stored(tmp_path: Path) -> None:
    e = Env(tmp_path, settings={"log/keep_days": "400"})
    await e.start()
    await e.play()
    e.now.advance(6 * 86400)  # type: ignore[attr-defined]
    assert await e.ctl.prune() == (0, [])
    e.now.advance(2 * 86400)  # type: ignore[attr-defined]
    count, stations = await e.ctl.prune()
    assert count == 4 and sorted(stations) == sorted(FIXED_ORDER)
    await e.stop()


async def test_prune_removes_the_stations_not_heard_for_the_days_kept_whatever_the_operator_said_of_them_and_their_preferences_stay(
    tmp_path: Path,
) -> None:
    e = Env(tmp_path)
    await e.start()
    await e.play()
    await e.ctl.prefbook.set_path("OH2RDG", "WIDE2-1")
    await e.ctl.prefbook.set_rf_only("OH2RDK-7", True)
    e.now.advance(5 * 86400)  # type: ignore[attr-defined]
    e.feed(frame_bytes("OH2NEW"))
    await until(lambda: e.tnc.stats.packets == 5)
    e.now.advance(4 * 86400)  # type: ignore[attr-defined]
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
    later.now.advance(40 * 86400)  # type: ignore[attr-defined]
    await later.start()
    await until(lambda: later.ctl.stationbook.get("OH2RDG") is None)
    assert await later.packets() == [] and [s.call for s in await later.stations()] == ["OH2GBA"]
    await later.stop()


async def test_a_change_of_the_serial_port_in_the_settings_restarts_the_tnc(tmp_path: Path) -> None:
    e = Env(tmp_path, radio=False, operator=False)
    first_radio, second_radio = await e.new_radio(), await e.new_radio()
    first, second = first_radio.url, second_radio.url
    await e.start()
    # No port: the search finds none and tries again every 50 ms, CONNECTING and WAITING in turn
    await until(lambda: e.tnc.state is Source.State.WAITING)
    assert e.ctl.config.to_data() == DEFAULTS.to_data()
    assert await e.ctl.save_config(replace(e.ctl.config, serial_port=first))
    await until(lambda: e.tnc.state is Source.State.CONNECTED and e.tnc.path == first)
    [fm] = await e.ctl.store.radios()
    assert fm.settings["port"] == first and "serial/port" not in await e.ctl.store.settings() and e.tnc.port == first, (
        "the flat key is radio 1's own row"
    )
    opens = e.tnc.stats.opens
    assert await e.ctl.save_config(replace(e.ctl.config, station_comment="a changed comment"))
    await idle_for(0.2)
    assert e.tnc.stats.opens == opens and e.tnc.state is Source.State.CONNECTED, (
        "a setting the Tnc does not use leaves it alone"
    )
    assert await e.ctl.save_config(replace(e.ctl.config, serial_port=second))
    await until(lambda: e.tnc.state is Source.State.CONNECTED and e.tnc.path == second)
    assert e.tnc.stats.opens == opens + 1
    assert await e.ctl.save_config(replace(e.ctl.config, serial_baud=4800))
    await until(lambda: e.tnc.state is Source.State.CONNECTED and e.tnc.baud == 4800 and e.tnc.stats.opens == opens + 2)
    assert (first_radio.connections, second_radio.connections) == (1, 2)
    await e.stop()
    again = Env(tmp_path, radio=False)
    await again.start(connected=False)
    assert (
        again.ctl.config.serial_port == second
        and again.ctl.config.serial_baud == 4800
        and again.ctl.config.station_comment == "a changed comment"
    )
    await again.stop()


async def test_a_change_of_our_call_and_position_is_put_in_force_at_once(tmp_path: Path) -> None:
    e = Env(tmp_path, radio=False)
    await e.start(connected=False)
    me = e.ctl.stationbook.me
    assert me is not None and (me.call, me.lat, me.lon) == ("OH2GBA", 60.17, 24.94)
    assert await e.ctl.save_config(replace(e.ctl.config, station_call="OH2GBA-9", station_lat=61.0, station_lon=25.0))
    me = e.ctl.stationbook.me
    assert (
        me is not None
        and (me.call, me.lat, me.lon) == ("OH2GBA-9", 61.0, 25.0)
        and not e.ctl.stationbook.get("OH2GBA").is_me
    )  # type: ignore[union-attr]
    await e.stop()


async def test_a_save_before_the_database_is_open_changes_nothing(tmp_path: Path) -> None:
    e = Env(tmp_path, radio=False)
    assert not await e.ctl.save_config(replace(e.ctl.config, station_comment="not stored")) and e.ctl.config == replace(
        DEFAULTS, radios=()
    ), "(no radio before the settings are read)"


async def test_a_port_given_for_this_run_is_used_alone_and_never_stored(tmp_path: Path) -> None:
    # The Env's radio is given as the controller's port, like --port
    e = Env(tmp_path, operator=False)
    await e.start()
    assert e.tnc.path == e.link and e.tnc.port == e.link and not e.tnc.fallback_probe
    await idle_for(0.1)
    assert await e.ctl.store.settings() == {} and e.ctl.config.serial_last_port == ""
    await e.stop()


def test_the_settings_become_the_tncs(search_pattern_from_settings: None) -> None:
    assert fm_line(DEFAULTS) == ("", 9600, KISS, True, (), "/dev/serial/by-id/* /dev/ttyUSB* /dev/ttyACM*")
    assert fm_line(replace(DEFAULTS, serial_last_port="/dev/brainbox_3")).port == "/dev/brainbox_3"
    assert fm_line(
        replace(
            DEFAULTS,
            serial_port="/dev/ttyUSB0",
            serial_last_port="/dev/brainbox_3",
            serial_baud=1200,
            tnc_profile="kenwood-tnc2",
        )
    ) == ("/dev/ttyUSB0", 1200, KENWOOD_TNC2, True, (), DEFAULTS.serial_pattern)
    assert fm_line(replace(DEFAULTS, serial_port="/dev/ttyUSB0"), "/dev/pts/4") == (
        "/dev/pts/4",
        9600,
        KISS,
        False,
        (),
        DEFAULTS.serial_pattern,
    )
    assert fm_line(replace(DEFAULTS, serial_skip="/dev/brainbox_2, /dev/ttyUSB5")).skip == (
        "/dev/brainbox_2",
        "/dev/ttyUSB5",
    )
    assert fm_line(replace(DEFAULTS, serial_pattern="/dev/brainbox_*")).pattern == "/dev/brainbox_*"
    assert fm_line(DEFAULTS, pattern="/tmp/probe_*").pattern == "/tmp/probe_*"


def test_the_settings_of_the_fm_radio_are_the_line_settings_of_radio_1_read_from_its_spec(
    search_pattern_from_settings: None,
) -> None:
    config = replace(
        DEFAULTS,
        serial_port="/dev/ttyUSB0",
        serial_last_port="/dev/brainbox_3",
        serial_baud=1200,
        tnc_profile="kenwood-tnc2",
        serial_skip="/dev/ttyUSB5",
    )
    fm = config.radio(FM_ID)
    assert fm is not None and line_settings(fm, config, RunOverrides()) == fm_line(config) == (
        "/dev/ttyUSB0",
        1200,
        KENWOOD_TNC2,
        True,
        ("/dev/ttyUSB5",),
        DEFAULTS.serial_pattern,
    )
    assert line_settings(fm, config, RunOverrides(port="/dev/pts/4", pattern="/tmp/probe_*")) == fm_line(
        config, "/dev/pts/4", "/tmp/probe_*"
    )
    moved = replace(fm, settings={**fm.settings, "port": "/dev/ttyACM1", "baud": "57600"})
    assert line_settings(moved, config, RunOverrides())[:2] == ("/dev/ttyACM1", 57600), (
        "the port and the speed are the radio's own, whatever the station's flat keys say"
    )
    third = replace(fm, id=3, settings={**fm.settings, "port": ""})
    assert line_settings(third, config, RunOverrides(port="/dev/pts/4")).port == "", (
        "the port of the run and the port the search remembered are radio 1's: another radio searches"
    )
    assert line_settings(third, config, RunOverrides(port="/dev/pts/4")).fallback_probe and line_settings(
        third, config, RunOverrides()
    ).skip == ("/dev/ttyUSB5",), "(by the station's pattern, past the station's ports to skip)"


def test_a_tnc_driver_gives_its_line_the_settings_the_id_and_the_quiet_period_and_its_key_is_the_line_settings() -> (
    None
):
    config = replace(
        DEFAULTS, serial_port="/dev/ttyUSB0", serial_baud=1200, tnc_profile="kenwood-tnc2", serial_skip="/dev/ttyUSB5"
    )
    fm = config.radio(FM_ID)
    assert fm is not None
    third = replace(fm, id=3)
    driver = TncDriver(third, Claims())
    line = driver.line
    assert line.radio_id == 3 and driver.modem is None and driver.held() == []
    driver.configure(third, config, RunOverrides(pattern="/tmp/probe_*", check_sec=0.0))
    assert (line.port, line.baud, line.profile, line.fallback_probe, line.skip, line.pattern) == (
        "/dev/ttyUSB0",
        1200,
        KENWOOD_TNC2,
        True,
        ("/dev/ttyUSB5",),
        "/tmp/probe_*",
    ) and line.watchdog.sec == 0.0
    assert driver.restart_key(third, config, RunOverrides()) == (line_settings(third, config, RunOverrides()),)
    assert driver.restart_key(third, config, RunOverrides()) != driver.restart_key(
        third, replace(config, serial_skip=""), RunOverrides()
    ), "the station's ports to skip restart a serial radio"
    assert driver.restart_key(third, config, RunOverrides()) == driver.restart_key(
        third, replace(config, mercury_keying="vox", station_comment="x"), RunOverrides()
    ), "nothing of another radio or of the station does"
    assert (
        driver.words(third, config, RunOverrides())
        == "Kenwood TH-D7 / TM-D700 / TS-2000, TNC-2,/dev/ttyUSB0 at 1200 baud"
    )
    given = Tnc()
    assert TncDriver(fm, Claims(), line=given).line is given and given.radio_id == FM_ID, (
        "a line made elsewhere is the driver's"
    )


def test_a_tcp_profile_connects_to_the_host_and_port_and_never_searches(search_pattern_from_settings: None) -> None:
    tcp = replace(DEFAULTS, tnc_profile="kiss-tcp")
    assert fm_line(tcp) == ("socket://127.0.0.1:8001", 9600, KISS_TCP, False, (), DEFAULTS.serial_pattern)
    assert (
        fm_line(replace(tcp, tcp_host="pi.local", tcp_port=8100, serial_last_port="/dev/ttyUSB0")).port
        == "socket://pi.local:8100"
    )
    assert fm_line(replace(tcp, tcp_host="::1")).port == "socket://[::1]:8001"
    assert fm_line(replace(tcp, serial_port="tcp://10.0.0.5:8100")).port == "tcp://10.0.0.5:8100", (
        "an address in serial/port is the one used"
    )
    assert fm_line(replace(tcp, serial_port="/dev/ttyUSB0")).port == "socket://127.0.0.1:8001", (
        "(a serial device is refused when saved; a row edited by hand is not followed)"
    )
    assert (
        replace(DEFAULTS, tnc_profile="kenwood-tnc2", serial_port="socket://localhost:7000").profile.transport
        == "serial"
    )
    assert (
        fm_line(replace(DEFAULTS, tnc_profile="kenwood-tnc2", serial_port="socket://localhost:7000")).port
        == "socket://localhost:7000"
    ), "a serial profile on a socket works"


def test_the_hf_radio_is_reached_on_the_port_the_modem_part_chose_and_its_two_settings_go_with_it() -> None:
    hf = replace(DEFAULTS, mercury_sound_card="plughw:1,0", mercury_keying="rts:/dev/ttyUSB0")
    assert hf_line(hf) == ("socket://127.0.0.1:8100", MERCURY, ("plughw:1,0", "rts:/dev/ttyUSB0"))
    assert hf_line(hf, modem_port=8101).port == "socket://127.0.0.1:8101", (
        "the modem part chose other ports because the defaults were taken"
    )
    assert hf_line(hf, "socket://127.0.0.1:18100").port == "socket://127.0.0.1:18100", (
        "a Mercury something else runs (--hf-port): the benches"
    )
    assert hf_line(replace(hf, mercury_keying="vox")) != hf_line(hf), "a change of the keying restarts the modem"
    assert fm_line(replace(DEFAULTS, tnc_profile="kiss-tcp", mercury_keying="rts:/dev/ttyUSB0")) == fm_line(
        replace(DEFAULTS, tnc_profile="kiss-tcp")
    ), "the FM radio knows nothing of the modem's settings"
    assert hf_line(replace(hf, hf_profile="dummy-hf")) == (DUMMY_PATH, DUMMY_HF, ("", "")), (
        "the Dummy HF radio opens nothing, and the modem's two settings are not its own"
    )


def test_a_modem_driver_points_its_line_at_the_modems_port_and_its_key_has_the_gain_only_while_nothing_sets_it_live(
    tmp_path: Path,
) -> None:
    config = replace(
        DEFAULTS,
        hf_enabled=True,
        mercury_sound_card="plughw:1,0",
        mercury_keying="rts:/dev/ttyUSB0",
        mercury_tx_gain_db=3,
    )
    hf = config.radio(HF_ID)
    assert hf is not None
    line, modem = Tnc(profile=MERCURY), Mercury(tmp_path)
    driver = MercuryDriver(hf, Claims(), tmp_path / "radios" / "2", line=line, modem=modem)
    assert (
        driver.line is line
        and driver.modem is modem
        and line.modem is modem
        and line.radio_id == HF_ID
        and driver.held() == []
    )
    run = RunOverrides(hf_port="socket://127.0.0.1:18100", check_sec=0.0)
    driver.configure(hf, config, run)
    assert (line.port, line.baud, line.profile, line.fallback_probe, line.skip, line.pattern) == (
        "socket://127.0.0.1:18100",
        9600,
        MERCURY,
        False,
        (),
        "",
    ), "the Mercury of the run: the benches'"
    assert (
        driver.restart_key(hf, config, run) == (hf_line(config, "socket://127.0.0.1:18100"), 3) and not modem.live_gain
    )
    modem._ui = type("Up", (), {"connected": True})()  # type: ignore[assignment]
    assert modem.live_gain and driver.restart_key(hf, config, run) == (
        hf_line(config, "socket://127.0.0.1:18100"),
        None,
    ), "with the link open the gain is sent and is no reason to restart"
    modem._ui = None
    assert (
        driver.words(hf, config, run)
        == hf_said(config, "socket://127.0.0.1:18100")
        == "the Mercury modem, one something else runs at socket://127.0.0.1:18100"
    )
    fourth = replace(hf, id=4)
    assert modem_settings(fourth, run).port != "socket://127.0.0.1:18100", (
        "the Mercury of the run is radio 2's: another radio's modem is its own"
    )


async def test_a_mercury_radio_whose_program_is_not_in_this_installation_has_no_line_and_says_the_modems_problem(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Whatever listens where a Mercury of ours would be (the test's own listener on the modem's
    port as it stands before any start) is not ours and is never connected to, before a start and
    after one."""
    accepted: list[int] = []
    other = await asyncio.start_server(lambda r, w: accepted.append(1) or w.close(), "127.0.0.1", 0)
    config = replace(DEFAULTS, hf_enabled=True)
    hf = config.radio(HF_ID)
    assert hf is not None
    line, modem = Tnc(profile=MERCURY, backoff=Backoff([0.05])), Mercury(tmp_path, finder=lambda: None)
    modem.broadcast_port = other.sockets[0].getsockname()[1]
    driver, run = (
        MercuryDriver(hf, Claims(), tmp_path / "radios" / "2", line=line, modem=modem),
        RunOverrides(check_sec=0.0),
    )
    driver.configure(hf, config, run)
    try:
        await driver.start()
        assert (
            (modem.state, modem.reason) == ("waiting", "not_installed")
            and line.port == ""
            and modem_settings(hf, run, modem.broadcast_port, True).port == ""
            and not modem.ports_chosen
        )
        await until(lambda: line.state is Source.State.WAITING)
        await idle_for(0.3)
        assert accepted == [] and line.stats.opens == 0 and line.problem == NOT_INSTALLED, (
            "the modem's problem, not a connection's"
        )
        assert [r for r in caplog.records if r.levelno >= logging.ERROR] == [] and sum(
            "trying again" in r.getMessage() for r in caplog.records if r.name == "neoaprs.tnc"
        ) == 0, "said once"
        await driver.stop()
        driver.configure(hf, config, run)
        assert line.port == "" and not modem.ports_chosen, (
            "a stop chose no ports either: the line has a port after a start that chose them"
        )
    finally:
        await driver.stop()
        other.close()
        await other.wait_closed()


def test_storing_what_the_running_modem_chose_for_itself_is_no_change_and_anything_else_is(tmp_path: Path) -> None:
    """MercuryDriver.made_explicit, which the registry asks before it compares the keys
    (tests/test_radio_restart.py has it through a save)."""
    config = replace(DEFAULTS, hf_enabled=True)
    hf = config.radio(HF_ID)
    assert hf is not None
    modem = Mercury(tmp_path)
    driver = MercuryDriver(hf, Claims(), tmp_path, modem=modem)
    chosen = replace(hf, settings={**hf.settings, "sound_card": "plughw:1,0", "keying": "rts:/dev/ttyUSB0"})
    modem.sound_card, modem.keying = "plughw:1,0", Keying("rts", "/dev/ttyUSB0")
    assert driver.made_explicit(hf, chosen) is hf, "a modem that is not running chose nothing"
    modem.state = "running"
    assert driver.made_explicit(hf, chosen) == chosen, "the page stores the daemon's proposal: nothing differs"
    other = replace(hf, settings={**hf.settings, "sound_card": "plughw:9,0", "keying": "rts:/dev/ttyUSB0"})
    assert (
        driver.made_explicit(hf, other).settings["sound_card"] == ""
        and driver.made_explicit(hf, other).settings["keying"] == "rts:/dev/ttyUSB0"
    ), "another card is a change, the keying it chose is none"
    assert driver.made_explicit(chosen, hf) == chosen, (
        "a setting that is cleared is a change: the modem is to choose again"
    )


def test_the_words_of_a_change_name_what_differs_and_the_tickbox() -> None:
    config = replace(DEFAULTS, tnc_profile="kenwood-tnc2", serial_port="/dev/ttyUSB0")
    fm_was, fm_now = (
        (fm_line(config), True),
        (fm_line(replace(config, serial_port="/dev/ttyUSB1", serial_baud=57600, serial_skip="/dev/ttyS0")), True),
    )
    assert (
        changed_words(fm_was, fm_now)
        == "port /dev/ttyUSB0 -> /dev/ttyUSB1, baud 9600 -> 57600, ports to skip none -> /dev/ttyS0"
    )
    assert (
        changed_words(fm_was, (fm_line(replace(config, tnc_profile="kiss")), False))
        == f"profile {KENWOOD_TNC2.name} -> {KISS.name}, switched on or off: on -> off"
    )
    hf = replace(DEFAULTS, hf_enabled=True)
    assert (
        changed_words(
            (hf_line(hf), 0, True),
            (hf_line(replace(hf, mercury_sound_card="plughw:9,0", mercury_keying="vox")), 0, True),
        )
        == "sound card default -> plughw:9,0, keying default -> vox"
    )
    assert changed_words((hf_line(hf), 0, True), (hf_line(hf), 5, True)) == "nothing the radio shows", (
        "(the gain, while nothing sets it live)"
    )
    assert (
        changed_words((hf_line(hf), None, True), (hf_line(replace(hf, hf_profile="dummy-hf")), None, True))
        == f"port socket://127.0.0.1:8100 -> {DUMMY_PATH}, profile {MERCURY.name} -> {DUMMY_HF.name}"
    )
    assert (
        changed_words(("a driver", "of a test", True), ("its key", "says nothing by name", True))
        == "nothing the radio shows"
    )


async def test_every_radios_packets_go_through_the_one_signal_and_a_change_of_a_radio_is_told_with_its_id(
    tmp_path: Path,
) -> None:
    e = Env(tmp_path, radio=False)
    assert e.tnc.packet._handlers == [e.ctl.radio_packet.emit] and e.hf.packet._handlers == [e.ctl.radio_packet.emit], (
        "each line is connected to the station's signal and to nothing else"
    )
    heard: list[str] = []
    changed: list[int] = []
    e.ctl.radio_packet.connect(lambda packet: heard.append(packet.source))
    e.ctl.radio_changed.connect(changed.append)
    e.tnc.packet.emit(replace(from_internet("OH2AAA", b">on FM", e.now()), via="rf", radio_id=FM_ID))
    e.hf.packet.emit(replace(from_internet("OH2BBB", b">on HF", e.now()), via="rf", radio_id=HF_ID))
    assert heard == ["OH2AAA", "OH2BBB"]
    book = {s.call: s for s in e.ctl.stationbook.stations()}
    assert tuple(book[call].heard_on(radio).count for call in ("OH2AAA", "OH2BBB") for radio in (FM_ID, HF_ID)) == (
        1,
        0,
        0,
        1,
    ), "(and the parts took both, each with its radio)"
    e.tnc.changed.emit()
    e.hf._set_state(Source.State.WAITING)
    e.mercury.changed.emit()
    assert changed == [FM_ID, HF_ID, HF_ID, HF_ID], (
        "a line's counters; a line's state, which the line tells as its state and as a change, as the page's topics take it; the modem's state"
    )
    radio = e.ctl.radios.get(HF_ID)
    assert radio is not None
    e.ctl.radios.wire(radio)
    assert (
        len(e.hf.packet._handlers) == 1
        and len(e.mercury.changed._handlers) == 2  # the page's topics and the line that follows its modem
        and len(e.beacon_2.sent._handlers) == 1
    ), "a radio that is wired again (another driver on the same line) is connected once"
    # The iGate takes every radio's beacon: nothing to assert but that it is connected
    e.beacon.sent.emit(ax25.Frame(ax25.Address("APRS"), ax25.Address.parse("OH2GBA"), (), info=b"!6010.00N/02456.00E-"))
    assert e.beacon.sent._handlers == e.beacon_2.sent._handlers == [e.ctl.igate.beacon_sent]


async def test_a_save_of_the_transmit_gain_reaches_the_modem_of_a_radio_that_is_off(tmp_path: Path) -> None:
    e = Env(tmp_path, radio=False, settings={"hf/enabled": "false", "hf/profile": "mercury"})
    await e.start(connected=False)
    config = e.ctl.config
    assert not e.ctl.radios.get(HF_ID).spec.enabled and e.mercury.tx_gain_db != -3  # type: ignore[union-attr]
    assert await e.ctl.save_config(
        replace(
            config,
            radios=tuple(
                replace(s, settings={**s.settings, "tx_gain_db": "-3"}) if s.id == HF_ID else s for s in config.radios
            ),
        )
    )
    assert e.mercury.tx_gain_db == -3, (
        "the radio is off, so nothing restarts: the save itself sets the gain in the modem"
    )
    await e.stop()


async def test_a_modem_on_other_ports_repoints_its_radios_line_only_while_the_radio_is_on(tmp_path: Path) -> None:
    e = Env(tmp_path, radio=False, settings={"hf/enabled": "false"})  # (the HF radio set up, and off)
    await e.start(connected=False)
    repointed: list[int] = []

    async def repoint(id: int) -> None:
        repointed.append(id)

    e.ctl.radios.repoint = repoint  # type: ignore[method-assign]
    e.mercury.ports_changed.emit()
    await idle_for(0.1)
    assert repointed == [] and "hf-tnc" not in {t.get_name() for t in e.ctl.tasks}, (
        "the line of a radio that is off is not started"
    )
    # The radio on, without a save that would start it
    e.ctl.config = replace(e.ctl.config, hf_enabled=True)
    e.mercury.ports_changed.emit()
    await until(lambda: repointed == [HF_ID])
    await e.stop()


async def test_the_start_takes_the_time_the_clock_says(tmp_path: Path) -> None:
    e = Env(tmp_path)
    await e.start()
    await e.play()
    [row] = [s for s in await e.stations() if s.call == "OH2RDG"]
    assert row.first_heard == row.last_heard == e.now() and row.last_position_at == e.now() - timedelta(0)
    await e.stop()
