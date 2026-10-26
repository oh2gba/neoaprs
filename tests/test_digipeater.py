"""The fill-in digipeater (neoaprs/services/digipeater.py) on a Tnc that is a stub and a clock the test holds: WIDE1-1 becomes our call as a used hop, our own call in the path is marked used, and nothing else
is repeated (WIDE2-1, our own packets, duplicates for 30 seconds, packets from the internet, anything while it is off, there is no call or the radio is away); the frame differs from the one heard in its path
only. Then the whole daemon with the radio a fake TCP server: a packet on the line comes back with the new path."""
import logging
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs import ax25
from neoaprs.packet import Packet
from neoaprs.services.digipeater import BURST_MAX, BURST_WINDOW_SEC, DUPLICATE_SEC, Digipeater
from neoaprs.source import Source
from neoaprs.tncmode import packet_of
from neoaprs.tncwatchdog import TncStats
from tests.support.air import on_air, said
from tests.support.env import ON_AIR, Env, until
from tests.support.rig import ServiceRig

INFO = b"!6010.20N/02456.40E-test"


def frame(path: str = "WIDE1-1,WIDE2-1", source: str = "OH2XYZ", info: bytes = INFO, destination: str = "APRS") -> ax25.Frame:
    return ax25.Frame(ax25.Address.parse(destination), ax25.Address.parse(source), tuple(ax25.Address.parse(p) for p in path.split(",") if p), info=info)


class Rig(ServiceRig):
    def __init__(self, **changes: object) -> None:
        super().__init__(digi_enabled=True, **changes)
        self.stats = TncStats()
        self.digi = Digipeater(self.tnc, lambda: self.config, self.clock, self.stats)

    def hear(self, f: ax25.Frame, direction: str = "in") -> Packet:
        packet = packet_of(direction, ax25.encode(f), f, self.clock())     # type: ignore[arg-type]
        self.digi.on_packet(packet)
        return packet


def test_wide1_1_becomes_our_call_marked_as_used_and_the_rest_of_the_path_stays() -> None:
    rig = Rig()
    rig.hear(frame("WIDE1-1,WIDE2-1"))
    assert rig.lines() == [f"OH2XYZ>APRS,OH2GBA*,WIDE2-1:{INFO.decode()}"]
    [sent] = rig.tnc.sent
    assert [(a.call, a.ssid, a.repeated) for a in sent.path] == [("OH2GBA", 0, True), ("WIDE2", 1, False)]
    assert rig.stats.digipeated == 1 and rig.stats.digipeated_at == rig.clock()


def test_wide1_1_alone_and_after_a_used_hop_is_the_first_unused_hop() -> None:
    rig = Rig()
    rig.hear(frame("WIDE1-1", info=b">one"))
    rig.hear(frame("OH2RCH*,WIDE1-1,WIDE2-1", info=b">two"))
    assert rig.lines() == ["OH2XYZ>APRS,OH2GBA*:>one", "OH2XYZ>APRS,OH2RCH,OH2GBA*,WIDE2-1:>two"]


def test_our_own_call_in_the_path_is_marked_used_where_it_stands() -> None:
    rig = Rig(station_call="OH2GBA-7")
    rig.hear(frame("OH2GBA-7,WIDE2-1"))
    rig.hear(frame("OH2GBA-7", info=b">other"))
    assert rig.lines() == [f"OH2XYZ>APRS,OH2GBA-7*,WIDE2-1:{INFO.decode()}", "OH2XYZ>APRS,OH2GBA-7*:>other"]


def test_another_ssid_of_ours_and_another_stations_call_are_not_ours_to_repeat() -> None:
    rig = Rig(station_call="OH2GBA-7")
    rig.hear(frame("OH2GBA,WIDE2-1", info=b">a"))
    rig.hear(frame("OH2GBA-9", info=b">b"))
    rig.hear(frame("OH2RCH-2", info=b">c"))
    assert rig.tnc.sent == []


@pytest.mark.parametrize("path", ["WIDE2-1", "WIDE2-2", "WIDE2-1,WIDE1-1", "WIDE1-2", "WIDE1-1*", "WIDE1-1*,WIDE2-1*", "OH2RCH*,WIDE2-1", "TRACE2-2", ""])
def test_a_path_whose_first_unused_hop_is_not_wide1_1_or_our_call_is_not_repeated(path: str) -> None:
    rig = Rig()
    rig.hear(frame(path))
    assert rig.tnc.sent == [] and rig.stats.digipeated == 0


def test_our_own_packets_are_not_repeated_and_neither_is_one_that_shows_our_call_as_used() -> None:
    rig = Rig()
    rig.hear(frame("WIDE1-1,WIDE2-1", source="OH2GBA", info=b">a"))
    rig.hear(frame("OH2GBA*,WIDE1-1", info=b">b"))
    rig.hear(frame("OH2RCH*,OH2GBA*,WIDE1-1", info=b">c"))
    assert rig.tnc.sent == []


def test_the_same_packet_is_repeated_again_only_after_thirty_seconds_whatever_the_path() -> None:
    rig = Rig()
    rig.hear(frame("WIDE1-1,WIDE2-1"))
    rig.clock.advance(DUPLICATE_SEC - 1)
    rig.hear(frame("WIDE1-1"))                                           # (a copy by another path)
    assert len(rig.tnc.sent) == 1
    rig.clock.advance(DUPLICATE_SEC + 1)                                 # (more than 30 s after the copy that was heard last)
    rig.hear(frame("WIDE1-1"))
    assert len(rig.tnc.sent) == 2 and rig.stats.digipeated == 2


def test_a_packet_that_differs_in_source_destination_or_text_is_another_packet() -> None:
    rig = Rig()
    rig.hear(frame())
    rig.hear(frame(source="OH2ABC"))
    rig.hear(frame(destination="APZNEO"))
    rig.hear(frame(info=INFO + b"!"))
    assert len(rig.tnc.sent) == 4


def test_a_packet_we_sent_lately_is_a_duplicate_of_one_heard_after_it() -> None:
    rig = Rig()
    rig.hear(frame("OH2GBA*,WIDE2-1", source="OH2XYZ", info=b">x"), "out")        # (the digipeater's own copy, as the Tnc reports it)
    rig.clock.advance(5)
    rig.hear(frame("OH2RCH*,WIDE1-1", source="OH2XYZ", info=b">x"))              # (the same packet heard again by another digipeater)
    assert rig.tnc.sent == []


def test_a_packet_that_came_from_the_internet_is_not_repeated() -> None:
    rig = Rig()
    rig.hear(frame("TCPIP*,WIDE1-1", info=b">a"))
    rig.hear(frame("WIDE1-1,TCPXX*", info=b">b"))
    assert rig.tnc.sent == []


def test_a_third_party_packet_an_igate_puts_on_the_air_is_repeated_the_tcpip_inside_it_does_not_count() -> None:
    rig = Rig()
    info = b"}OH2XYZ>APRS,TCPIP,OH7JHF-1*::OH2GBA-7 :hi{12"
    rig.hear(frame("WIDE1-1", source="OH7JHF-1", info=info))
    assert rig.lines() == [f"OH7JHF-1>APRS,OH2GBA*:{info.decode()}"]


def test_nogate_and_rfonly_keep_a_packet_off_the_internet_not_off_the_radio() -> None:
    rig = Rig()
    rig.hear(frame("WIDE1-1,NOGATE", info=b">a"))
    rig.hear(frame("WIDE1-1,RFONLY", info=b">b"))
    assert rig.lines() == ["OH2XYZ>APRS,OH2GBA*,NOGATE:>a", "OH2XYZ>APRS,OH2GBA*,RFONLY:>b"]


def test_nothing_is_repeated_while_the_digipeater_is_off() -> None:
    rig = Rig()
    rig.config = replace(rig.config, digi_enabled=False)
    rig.hear(frame())
    assert rig.tnc.sent == [] and rig.stats.digipeated == 0
    rig.config = replace(rig.config, digi_enabled=True)
    rig.hear(frame())
    assert len(rig.tnc.sent) == 1, "(a packet heard while it was off is not held against the next copy)"


def test_the_default_settings_digipeat_nothing() -> None:
    rig = Rig()
    rig.config = ON_AIR
    rig.hear(frame())
    assert rig.tnc.sent == []


@pytest.mark.parametrize("call", ["", "N0CALL", "not a call"])
def test_nothing_is_repeated_without_a_call_and_the_log_says_so_once(call: str, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, "neoaprs.interlock")
    rig = Rig(station_call=call)
    rig.hear(frame(info=b">a"))
    rig.hear(frame(info=b">b"))
    assert rig.tnc.sent == [] and len([r for r in caplog.records if r.getMessage().startswith("no digipeat sent")]) == 1


@pytest.mark.parametrize("state", [Source.State.SILENT, Source.State.WAITING, Source.State.CONNECTING, Source.State.STOPPED])
def test_nothing_is_repeated_while_the_radio_is_not_usable(state: Source.State) -> None:
    rig = Rig()
    rig.tnc.state = state
    rig.hear(frame())
    assert rig.tnc.sent == [] and rig.stats.digipeated == 0


def test_a_tnc_that_does_not_take_the_frame_counts_nothing(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, "neoaprs.digipeater")
    rig = Rig()
    rig.tnc.takes = False
    rig.hear(frame())
    assert rig.stats.digipeated == 0 and any("not sent" in r.getMessage() for r in caplog.records)


def test_only_the_path_differs_from_the_frame_that_was_heard() -> None:
    rig = Rig()
    heard = ax25.Frame(ax25.Address.parse("APZ123"), ax25.Address.parse("OH2XYZ-9"), (ax25.Address.parse("WIDE1-1"), ax25.Address.parse("WIDE2-1")), info=bytes(range(32, 256)) + b"\x00\xff")
    raw = ax25.encode(heard)
    rig.hear(heard)
    [sent] = rig.tnc.sent
    out = ax25.encode(sent)
    assert (sent.source, sent.destination, sent.info, sent.control, sent.pid) == (heard.source, heard.destination, heard.info, heard.control, heard.pid)
    assert out[:14] == raw[:14] and out[-len(heard.info) - 2:] == raw[-len(heard.info) - 2:], "destination, source, control, PID and information field are the bytes that came"
    assert len(out) == len(raw) and out != raw
    assert ax25.decode(out) == sent


def _address(call: str, ssid: int, flags: int) -> bytes:
    return bytes(ord(c) << 1 for c in call.ljust(6)) + bytes([flags | (ssid << 1)])


def test_the_address_flag_bits_of_the_destination_and_the_source_go_out_as_they_came() -> None:
    rig = Rig()
    info = b">test"
    raw = _address("APRS", 0, 0x00) + _address("OH2XYZ", 0, 0x80) + _address("WIDE1", 1, 0x01) + b"\x03\xf0" + info     # (C bits of a response, reserved bits clear)
    heard = ax25.decode(raw)
    rig.digi.on_packet(packet_of("in", raw, heard, rig.clock()))
    [out] = rig.tnc.raw
    assert out[:14] == raw[:14], "the destination and the source are the bytes that came, not those encode() would write"
    assert out[14:21] == _address("OH2GBA", 0, 0xE1), "only the path is encoded again: our call, used, last"
    assert out[21:] == raw[21:]


def test_the_duplicate_check_counts_the_destination_without_its_ssid() -> None:
    rig = Rig()
    rig.hear(frame("WIDE1-1", destination="APRS"))
    rig.clock.advance(5)
    rig.hear(frame("WIDE1-1", destination="APRS-1"))
    assert len(rig.tnc.sent) == 1, "the same source, destination call and information field is the same packet (WB2OSZ's digipeater algorithm)"


def test_not_more_than_a_few_frames_go_out_in_a_burst_and_it_goes_on_when_the_window_has_passed() -> None:
    rig = Rig()
    for n in range(BURST_MAX + 3):
        rig.hear(frame(info=f">{n}".encode()))
    assert len(rig.tnc.sent) == BURST_MAX and rig.stats.digipeat_held == 3
    rig.clock.advance(BURST_WINDOW_SEC)
    rig.hear(frame(info=b">later"))
    assert len(rig.tnc.sent) == BURST_MAX + 1 and rig.stats.digipeated == BURST_MAX + 1


def test_a_digipeated_frame_is_told_in_the_log_at_info(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.digipeater")
    rig = Rig()
    rig.hear(frame("WIDE1-1,WIDE2-1"))
    assert [r.getMessage() for r in caplog.records] == ["digipeated OH2XYZ>APRS: the path WIDE1-1,WIDE2-1 is sent as OH2GBA*,WIDE2-1"]


# ---- the whole daemon: a fake radio on the loopback

async def test_a_packet_that_asks_for_wide1_1_comes_back_on_the_line_with_our_call_used(tmp_path: Path) -> None:
    e = Env(tmp_path, settings={"digi/enabled": "true"})
    await e.start()
    e.feed(on_air("OH2XYZ", INFO, path="WIDE1-1,WIDE2-1"))
    [out] = await said(e)
    assert out.tnc2() == f"OH2XYZ>APRS,OH2GBA*,WIDE2-1:{INFO.decode()}"
    await until(lambda: e.tnc.stats.digipeated == 1)
    sent = [p for p in await e.packets() if p.direction == "out"]
    assert [p.path for p in sent] == [("OH2GBA*", "WIDE2-1")]
    await e.stop()


async def test_the_daemon_digipeats_nothing_with_the_default_settings(tmp_path: Path) -> None:
    e = Env(tmp_path)
    await e.start()
    e.feed(on_air("OH2XYZ", INFO, path="WIDE1-1,WIDE2-1"))
    await until(lambda: e.tnc.stats.packets == 1)
    assert await said(e, 1, 0.3) == [] and e.tnc.stats.digipeated == 0
    await e.stop()
