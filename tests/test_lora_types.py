"""The LoRa APRS boards as types of the round's model (neoaprs/radiotypes/lora.py, neoaprs/tncprofile.py; aprs-reference/lora-plan.md step L2): their fields (where a board is reached, no frequency
and no modem setting), their limits (250 bytes of AX.25 and 252 of text, the beacon's floor of 30 minutes, HF's pauses), what they are allowed (paths and SmartBeaconing, no digipeating), what their box can
(a terminal, no Find), WIDE1-1 when the radio's own path is empty, a comment cut so that the text fits a LoRa packet, the profiles that say the same; and a daemon with a `lora-tcp` radio added from the page on
the fake CA2RXU iGate: a packet heard comes in on it as kind LoRa with the signal of the iGate's list, and our beacon goes out on it, which the board keys as a LoRa packet of text on WIDE1-1."""
from pathlib import Path

import pytest

from neoaprs import TOCALL, ax25, kiss, loralist
from neoaprs.radiotype import FM_ID, Allowed, Can, Limits
from neoaprs.radiotypes import DEFAULT_TYPE, recommended_path, type_of, types_of
from neoaprs.services.radioset import fit_frame
from neoaprs.source import Source
from neoaprs.tnc import Tnc
from neoaprs.tnc2line import MAX_TEXT, text_of
from neoaprs.tncprofile import EVERY_BY_KEY, LORA_CONSOLE, LORA_NUDGE, LORA_SERIAL, LORA_TCP
from tests.support.env import Env, until, until_started
from tests.support.fakelora import HEADER, Board, BoardOnTcp, ListServer
from tests.test_radios_wire import added

BOARDS = ("lora-tcp", "lora-serial", "lora-console")
ME = "OH2GBA"


def test_the_boards_are_types_of_the_kind_lora_on_the_tnc_driver_and_the_one_on_the_network_is_the_default() -> None:
    assert [t.key for t in types_of("lora")] == [*BOARDS, "dummy-lora"] and DEFAULT_TYPE["lora"] == "lora-tcp"
    for key in BOARDS:
        t = type_of(key)
        assert (t.kind, t.driver, t.profile, t.text, t.dummy, t.recommended_path) == ("lora", "tnc", key, f"radio.type.{key}", False, "WIDE1-1")
    assert [type_of(key).transport for key in BOARDS] == ["tcp", "serial", "serial"]
    assert recommended_path("lora") == "WIDE1-1"


def test_where_a_board_is_reached_are_its_only_fields_besides_the_beacon_and_the_path() -> None:
    tcp, serial, console = (type_of(key) for key in BOARDS)
    assert [f.key for f in tcp.fields] == ["tcp_host", "tcp_port", "beacon", "status", "ask", "local_info", "path"] and tcp.field("tcp_port").default == "8001"     # type: ignore[union-attr]
    host = tcp.field("tcp_host")
    assert host is not None and (host.default, host.parse(""), host.parse(" 192.168.1.20 ")) == ("", "", "192.168.1.20"), "a board on the network has no address until the operator types the board's"
    with pytest.raises(ValueError):
        host.parse("two words")
    assert [f.key for f in serial.fields] == ["port", "baud", "beacon", "status", "ask", "local_info", "path"] and [f.key for f in console.fields] == ["port", "baud"], "a radio that only receives has no choice of what goes out"
    assert serial.field("port").claims == "serial", "a board's port is the radio's: no other radio and no search opens it"                    # type: ignore[union-attr]
    assert not any(f.key in ("frequency", "spreading_factor", "bandwidth", "coding_rate") for t in types_of("lora") for f in t.fields), "no firmware takes them from a program safely"


def test_the_limits_and_what_a_board_is_allowed_and_can() -> None:
    for key in BOARDS:
        t = type_of(key)
        assert (t.limits.max_frame, t.limits.max_text, t.limits.max_kiss, t.limits.beacon_min_min, t.limits.beacon_jitter_sec, t.limits.retry_jitter_sec) == (250, 252, 256, 30, 300, 20)
        assert t.allowed == (Allowed(paths=False, digipeat=False, smart_beacon=False, gateway_heard=False, shared_channel=False) if key == "lora-console" else
                             Allowed(paths=True, digipeat=False, smart_beacon=True, gateway_heard=True, shared_channel=False)), "a radio that only receives has no path, beacon or gateway of ours"
        assert t.can == Can(find=False, terminal=True, tune=False, key_test=False, scope=False, tx_gain=False, frequencies=False, transmit=key != "lora-console"), "no Find: an open may restart a board"
    assert type_of("lora-console").limits == type_of("lora-tcp").limits == Limits(250, 30, 300, 20, 252, max_kiss=256), "a radio that only receives keeps its kind's limits; it sends nothing (`Can.transmit`)"


def test_each_profile_says_what_its_type_says_and_reads_a_board() -> None:
    for profile in (LORA_TCP, LORA_SERIAL, LORA_CONSOLE):
        t = type_of(profile.key)
        assert EVERY_BY_KEY[profile.key] is profile and t.profile == profile.key and Tnc("", profile=profile).rtype is t and t.limits.max_text == MAX_TEXT, "a line of the profile reads its type's limits"
        assert profile.receive_only == profile.writes_nothing == (not t.can.transmit) and t.limits.max_kiss == 256 and profile.readings == ("snr", "rssi") and profile.board
        assert not profile.search and not profile.can_probe and not profile.detect_command_mode and profile.enter == () and profile.exit_kiss is None
    assert (LORA_TCP.baud, LORA_SERIAL.baud, LORA_CONSOLE.baud) == (None, 115200, 115200)
    assert LORA_TCP.nudge == LORA_SERIAL.nudge == LORA_NUDGE == b"\xc0\x05\x00\xc0" and LORA_CONSOLE.nudge == b""
    assert (LORA_TCP.text_lines, LORA_SERIAL.text_lines, LORA_CONSOLE.text_lines) == ("tnc2", "tnc2", "console")
    assert LORA_TCP.drop_internet and LORA_SERIAL.drop_internet and LORA_TCP.board_readings and LORA_SERIAL.board_readings


def test_fit_cuts_the_comment_for_the_text_with_a_long_path() -> None:
    frame = ax25.Frame(ax25.Address.parse(TOCALL), ax25.Address.parse("OH2GBA-15"), tuple(ax25.Address.parse(c) for c in ("WIDE1-1", "WIDE2-2", "OH2RDK-10", "OH2LRG-10")),
                       info=b"=6010.00N/02456.00E-" + "Pyöräily ".encode() * 20)
    assert len(ax25.encode(frame)) > 250 and len(text_of(frame)) > MAX_TEXT
    fitted = fit_frame(frame, 250, MAX_TEXT)
    assert len(text_of(fitted)) <= MAX_TEXT and len(ax25.encode(fitted)) <= 250 and fitted.info.startswith(b"=6010.00N/02456.00E-")


def test_fit_cuts_the_comment_so_that_its_kiss_fits_the_boards_input() -> None:
    frame = ax25.Frame(ax25.Address.parse(TOCALL), ax25.Address.parse("OH2GBA"), (ax25.Address.parse("WIDE1-1"),), info=b"!6010.00N/02456.00E-" + "\u06db".encode() * 100)
    assert len(ax25.encode(frame)) <= 250 and len(text_of(frame)) <= MAX_TEXT and len(kiss.encode(ax25.encode(frame))) > 256, "only its KISS is too long"
    fitted = fit_frame(frame, 250, MAX_TEXT, 256)
    assert len(kiss.encode(ax25.encode(fitted))) <= 256 and len(ax25.encode(fitted)) <= 250 and fitted.info.startswith(b"!6010.00N/02456.00E-")
    assert fit_frame(fitted, 250, MAX_TEXT, 256) is fitted
    with pytest.raises(ValueError, match="in KISS"):
        fit_frame(ax25.Frame(frame.destination, frame.source, info=b"<" + b"\xdb" * 200), None, None, 256)      # (a kind of report that is never cut)


async def test_a_lora_tcp_radio_on_the_igate_hears_as_kind_lora_with_the_lists_signal_and_its_beacon_goes_out_in_text_on_wide1_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    board = Board("igate")
    end, server = BoardOnTcp(board), await ListServer(board).start()
    await end.start()
    monkeypatch.setattr(loralist, "PORT", server.port)
    e = Env(tmp_path, radio=False, web=True, settings={"tnc/profile": "dummy", "station/call": ME, "station/lat": "60.17", "station/lon": "24.94", "messages/alert": "false"})
    try:
        await e.start(connected=False)
        page = await e.ws()
        await page.until(lambda: "radios" in page.topics)
        id = await added(page, "lora-tcp")
        await page.send({"cmd": "set_config", "values": {f"radio/{id}/tcp_host": "127.0.0.1", f"radio/{id}/tcp_port": str(end.port)}})
        radio = e.ctl.radios.get(id)
        assert radio is not None
        await until_started(lambda: radio.state is Source.State.CONNECTED and end.clients == 1)
        row = page.topics["radios"][str(id)]
        assert (row["kind"], row["type"], row["dummy"]) == ("lora", "lora-tcp", False) and row["limits"] == {"max_frame": 250, "beacon_min_min": 30}
        board.air(b"OH2ABC-7>APLRT1,WIDE1-1:!6010.00N/02456.00E>tracker", rssi=-97, snr=6.25)
        await until(lambda: any(s.call == "OH2ABC-7" for s in e.ctl.stationbook.stations()))
        station = next(s for s in e.ctl.stationbook.stations() if s.call == "OH2ABC-7")
        assert station.heard_on(id).count == 1 and station.heard_on(FM_ID).count == 0 and (station.snr, station.rssi) == (6.25, -97.0)
        packet = next(p for p in await e.packets() if p.source == "OH2ABC-7")
        assert (packet.radio_id, packet.via, packet.snr, packet.rssi) == (id, "rf", 6.25, -97.0)
        assert radio.beacon.send_now(), radio.beacon.problem
        await until(lambda: len(board.transmitted) == 1)
        sent = board.transmitted[0]
        assert sent.startswith(HEADER + f"{ME}>{TOCALL},WIDE1-1:".encode()) and sent[len(HEADER) + len(f"{ME}>{TOCALL},WIDE1-1:"):][:1] in (b"=", b"!"), sent
        assert server.requests and set(server.requests) == {"/received-packets.json"}
    finally:
        await e.stop()
        await server.stop()
        await end.aclose()


async def test_a_lora_tcp_radio_just_added_opens_nothing_until_the_boards_address_is_typed(tmp_path: Path) -> None:
    e = Env(tmp_path, radio=False, web=True, settings={"tnc/profile": "dummy", "station/call": ME, "station/lat": "60.17", "station/lon": "24.94", "messages/alert": "false"})
    try:
        await e.start(connected=False)
        page = await e.ws()
        await page.until(lambda: "radios" in page.topics)
        id = await added(page, "lora-tcp")
        radio = e.ctl.radios.get(id)
        assert radio is not None
        await until(lambda: radio.state is Source.State.WAITING)
        assert (radio.line.port, radio.line.path, radio.line.stats.opens) == ("", "", 0), "no board is on this computer: nothing is opened, Direwolf's port on it least of all"
        assert radio.line.problem.startswith("no address is chosen") and not radio.line.usable
        await page.until(lambda: (page.topics["radios"][str(id)]["problem"] or {}).get("code") == "radio.not_connected")
    finally:
        await e.stop()
