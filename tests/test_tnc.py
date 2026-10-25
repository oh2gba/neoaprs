"""The TNC (neoaprs/tnc.py) on a fake radio (a TCP server on the loopback, tests/support/fakeradio.py): the real KISS stream of the TH-D7 decoded to packets, the switch from command mode to KISS, the silence,
damaged frames, a line that dies and comes back, sending, the keep-alive and the mode detector by itself. The search over device files is in tests/test_tnc_pty.py."""
import asyncio
import functools
import logging
from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from neoaprs import ax25, kiss, serialprobe
from neoaprs.packet import Message, Other, Packet, Position, ThirdParty
from neoaprs.source import Backoff, Source
from neoaprs.tnc import ENTER_KISS, KISS_EXIT, Tnc
from neoaprs.tncmode import Mode, ModeDetector
from neoaprs.tncprofile import KENWOOD_TNC2, KISS_TCP
from tests.support.clock import FixedClock
from tests.support.env import idle_for, until
from tests.support.fakeradio import REFUSED, FakeRadio
from tests.support.files import fixture_bytes

NO_DETECT = replace(KENWOOD_TNC2, detect_command_mode=False)       # a TNC that is asked if it is there, but whose text does not make the Tnc enter KISS
MONITOR_LINE = b"OH2FZV-2>VP1R61,WIDE1,OH2RCH-2*:!6010.00N/02456.00E>test\r\n"
SETTLE = 0.15


def tiny_backoff() -> Backoff:
    return Backoff([0.05, 0.05])


def ui_frame(source: str = "OH2GBA-7", info: bytes = b"!6010.00N/02456.00E>hello") -> ax25.Frame:
    return ax25.Frame(ax25.Address("APRS"), ax25.Address.parse(source), (ax25.Address.parse("WIDE1-1"),), info=info)


def kiss_of(frame: ax25.Frame) -> bytes:
    return kiss.encode(ax25.encode(frame))


class Rig:
    """A Tnc on a fake radio with the packets it emitted."""

    def __init__(self, tnc: Tnc, radio: FakeRadio) -> None:
        self.tnc, self.radio = tnc, radio
        self.packets: list[Packet] = []
        tnc.packet.connect(self.packets.append)


class Rigs:
    """Makes a fake radio and a started Tnc on it (keyword arguments go to the Tnc; it may be asked if the radio is there, as a TNC with a command mode may, but `check_sec` is 0 unless given); `stops_rigs` stops every Tnc made and closes every radio when the test ends."""

    def __init__(self) -> None:
        self.started: list[Tnc] = []
        self.radios: list[FakeRadio] = []

    async def __call__(self, **kwargs: object) -> Rig:
        radio = FakeRadio()
        await radio.start()
        self.radios.append(radio)
        kwargs.setdefault("check_sec", 0.0)                       # (no checks unless a test asks: a line is usable as soon as it is open)
        kwargs.setdefault("settle_sec", SETTLE)
        kwargs.setdefault("backoff", tiny_backoff())
        kwargs.setdefault("fallback_probe", False)                # (a test must never listen to the operator's /dev/brainbox_* ports)
        tnc = Tnc(radio.url, **kwargs)  # type: ignore[arg-type]
        self.started.append(tnc)
        await tnc.start()
        assert tnc.state is Source.State.CONNECTED, tnc.problem
        await radio.connected()                                  # (the radio has accepted the connection the Tnc made)
        return Rig(tnc, radio)


@pytest.fixture
def rig() -> Rigs:
    return Rigs()


def stops_rigs(test: Callable[..., Awaitable[None]]) -> Callable[..., Awaitable[None]]:
    """The tasks of a Tnc must be gone before the leak guard looks, which is before a fixture of the test is torn down: the test body is wrapped instead."""
    @functools.wraps(test)
    async def wrapper(*args: object, **kwargs: Rigs) -> None:
        try:
            await test(*args, **kwargs)
        finally:
            for tnc in kwargs["rig"].started:
                await tnc.stop()
            for radio in kwargs["rig"].radios:
                await radio.aclose()
    return wrapper


# ---- the captured stream

@stops_rigs
async def test_the_captured_stream_of_the_thd7_comes_out_as_its_four_packets(rig: Rigs) -> None:
    r = await rig()
    data = fixture_bytes("kiss/thd7-2026-10-21.bin")
    pos, size = 0, 1
    while pos < len(data):
        r.radio.feed(data[pos:pos + size])
        pos, size = pos + size, size % 13 + 6                # odd-sized chunks
        await asyncio.sleep(0.002)
    await until(lambda: len(r.packets) == 4)
    assert [(p.source, p.kind) for p in r.packets] == [("OH2RDG", "position"), ("OH2RDK-7", "position"), ("OH2RDS", "position"), ("OH2PU-9", "position")]
    assert all(p.direction == "in" and p.path[0] == "OH2RCH-2*" for p in r.packets)
    assert [p.destination for p in r.packets] == ["APN391", "APRX29", "APN391", "APOTC1"]
    assert [isinstance(p.decoded, Position) and p.decoded.compressed for p in r.packets] == [False, False, False, True]
    assert r.packets[0].raw == kiss.KissDecoder().feed(data)[0].payload
    s = r.tnc.stats
    assert (s.packets, s.frames_in, s.rejected, s.opens, s.bytes_in) == (4, 4, 0, 1, len(data))
    assert s.last_packet == r.packets[-1].heard_at
    assert any("OH2RDG>APN391,OH2RCH-2*,TRACE2-1:" in line for line in r.tnc.lines)
    assert r.tnc.describe() == f"{r.tnc.path}, KISS, 4 packets"


@stops_rigs
async def test_packets_are_stamped_with_the_clock(rig: Rigs) -> None:
    from tests.support.clock import FixedClock
    clock = FixedClock()
    r = await rig(clock=clock)
    r.radio.feed(kiss_of(ui_frame()))
    await until(lambda: r.packets)
    assert r.packets[0].heard_at == clock.now and r.tnc.stats.last_packet == clock.now


@stops_rigs
async def test_the_third_party_frames_an_igate_put_on_the_air_come_out_as_the_packets_inside_them(rig: Rigs) -> None:
    r = await rig()
    ack = ax25.Frame(ax25.Address.parse("APRS"), ax25.Address.parse("OH7JHF-1"), (ax25.Address.parse("OH2RCH-3*"),), info=b"}OH2DPN>APJYC1,TCPIP,OH7JHF-1*::OH2GBA   :ack10")
    text = ax25.Frame(ax25.Address.parse("APRS"), ax25.Address.parse("OH7JHF-1"), (ax25.Address.parse("OH2RCH-3*"),), info=b"}OH2BEA-9>APY300,TCPIP,OH7JHF-1*::OH2GBA   :Test ok{06")
    inside = ax25.Frame(ax25.Address.parse("APRS"), ax25.Address.parse("OH7JHF-1"), (), info=b"}OH2DPN>APRS,TCPIP:}OH2BEA-9>APRS:>x")
    for frame in (ack, text, inside):
        r.radio.feed(kiss.encode(ax25.encode(frame)))
    await until(lambda: len(r.packets) == 3)
    first, second, third = r.packets
    assert (first.source, first.path, first.sender, first.via) == ("OH7JHF-1", ("OH2RCH-3*",), "OH2DPN", "OH7JHF-1")
    assert first.third_party == ThirdParty("OH2DPN", "APJYC1", ("TCPIP", "OH7JHF-1*")) and first.info == ack.info and first.raw == ax25.encode(ack)
    assert first.decoded == Message("OH2GBA", "", ack_id="10") and first.summary == "ack 10 to OH2GBA via OH7JHF-1 (third-party)"
    assert second.decoded == Message("OH2GBA", "Test ok", "06") and second.sender == "OH2BEA-9"
    assert third.decoded == Other("third-party", "}OH2BEA-9>APRS:>x") and third.sender == "OH2DPN", "a third-party packet inside a third-party packet is not opened again"
    assert any("OH7JHF-1>APRS,OH2RCH-3*:}OH2DPN>APJYC1,TCPIP,OH7JHF-1*::OH2GBA   :ack10  ->  ack 10 to OH2GBA via OH7JHF-1 (third-party)" in line for line in r.tnc.lines)


# ---- command mode

@stops_rigs
async def test_a_tnc_in_command_mode_is_switched_to_kiss_once(rig: Rigs) -> None:
    r = await rig()
    r.radio.feed(MONITOR_LINE)
    assert await r.radio.said(len(ENTER_KISS)) == b"\rKISS ON\rRESTART\r"
    r.radio.feed(b"KISS ON\r\nKISS     was OFF\r\ncmd:\x11\x11")           # what the TNC says while it restarts
    r.radio.feed(kiss_of(ui_frame("OH2AAA")))                                # a frame that arrives inside the settling time is thrown away
    await idle_for(SETTLE + 0.1)
    r.radio.feed(MONITOR_LINE)                                                # text again after KISS ON: left alone, said in the problem
    r.radio.feed(kiss_of(ui_frame("OH2BBB")))
    await until(lambda: r.packets)
    assert [p.source for p in r.packets] == ["OH2BBB"]
    assert await r.radio.said(1, 0.3) == b"", "KISS ON is sent once per open"
    assert r.tnc.state is Source.State.CONNECTED
    assert any("entering KISS mode" in line for line in r.tnc.lines)


@stops_rigs
async def test_a_radio_restarted_while_in_kiss_is_switched_to_kiss_again_at_once(rig: Rigs) -> None:
    r = await rig()
    r.radio.feed(MONITOR_LINE)
    assert await r.radio.said(len(ENTER_KISS)) == ENTER_KISS
    await idle_for(SETTLE + 0.1)
    r.radio.feed(kiss_of(ui_frame("OH2AAA")))                                # KISS frames flow
    await until(lambda: r.packets)
    r.radio.feed(MONITOR_LINE)                                                # the radio was switched off and on: its TNC types text again
    assert await r.radio.said(len(ENTER_KISS)) == ENTER_KISS, "entered again, not left until the next check"
    await idle_for(SETTLE + 0.1)
    r.radio.feed(MONITOR_LINE)                                                # text that goes on with no KISS frame in between: not entered a third time
    assert await r.radio.said(1, 0.3) == b""
    r.radio.feed(kiss_of(ui_frame("OH2BBB")))
    await until(lambda: len(r.packets) == 2)
    assert sum("restarted" in line for line in r.tnc.lines) == 1


@stops_rigs
async def test_a_tnc_that_still_types_text_after_kiss_on_is_sent_nothing_and_kiss_on_again_until_it_takes(rig: Rigs, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("neoaprs.tnc.ENTRY_AGAIN_SEC", 0.3)                   # (10 s in the program)
    r = await rig()
    r.radio.feed(MONITOR_LINE)
    assert await r.radio.said(len(ENTER_KISS)) == ENTER_KISS
    await idle_for(SETTLE + 0.1)
    r.radio.feed(MONITOR_LINE)                                                # a radio that was just switched on missed it: it still types text
    await until(lambda: r.tnc.problem != "")
    assert not r.tnc.usable and "command mode" in r.tnc.why_unusable(), "no frame is typed into a TNC in command mode"
    assert await r.radio.said(1, 0.1) == b"", "not again at once"
    await idle_for(0.3)
    r.radio.feed(MONITOR_LINE)
    assert await r.radio.said(len(ENTER_KISS)) == ENTER_KISS, "KISS ON again, a while after the first"
    await idle_for(SETTLE + 0.1)
    r.radio.feed(kiss_of(ui_frame("OH2AAA")))
    await until(lambda: r.packets)
    assert r.tnc.problem == "" and r.tnc.usable


@stops_rigs
async def test_text_that_goes_on_after_kiss_on_is_told_in_the_problem(rig: Rigs) -> None:
    r = await rig()
    r.radio.feed(b"cmd:")
    assert await r.radio.said(len(ENTER_KISS)) == ENTER_KISS
    await idle_for(SETTLE + 0.1)
    r.radio.feed(MONITOR_LINE)
    await until(lambda: r.tnc.problem)
    assert "command mode" in r.tnc.problem and r.tnc.state is Source.State.CONNECTED
    assert await r.radio.said(1, 0.3) == b""


@stops_rigs
async def test_nothing_is_sent_when_entering_kiss_is_off(rig: Rigs) -> None:
    r = await rig(profile=NO_DETECT)
    r.radio.feed(MONITOR_LINE + b"\n\r\ncmd:")
    await until(lambda: r.tnc.problem)
    assert await r.radio.said(1, 0.3) == b""
    assert r.tnc.state is Source.State.CONNECTED and r.packets == []
    r.radio.feed(kiss_of(ui_frame()))                          # if it does start talking KISS, that is decoded
    await until(lambda: r.packets)


@stops_rigs
async def test_a_tnc_in_kiss_mode_is_left_alone(rig: Rigs) -> None:
    r = await rig()
    r.radio.feed(fixture_bytes("kiss/thd7-2026-10-21.bin"))
    await until(lambda: len(r.packets) == 4)
    assert await r.radio.said(1, 0.2) == b""


# ---- damaged input

@stops_rigs
async def test_frames_that_are_not_packets_are_counted_and_the_next_one_still_decodes(rig: Rigs) -> None:
    r = await rig()
    not_ui = ax25.encode(ax25.Frame(ax25.Address("APRS"), ax25.Address("OH2GBA"), control=0x3F))      # an unnumbered frame that is not UI
    r.radio.feed(kiss.encode(b"this is not an AX.25 frame at all") + kiss.encode(not_ui) + kiss.encode(b"x", command=1) + kiss_of(ui_frame("OH2CCC")))
    await until(lambda: r.packets)
    s = r.tnc.stats
    assert (s.rejected, s.packets, s.frames_in) == (3, 1, 4)
    assert r.packets[0].source == "OH2CCC"
    assert sum("rejected" in line for line in r.tnc.lines) == 3


@stops_rigs
async def test_a_frame_the_kiss_decoder_threw_away_counts_as_rejected(rig: Rigs) -> None:
    r = await rig()
    r.radio.feed(b"\xc0\x00abc\xdb\x01def\xc0" + kiss_of(ui_frame()))
    await until(lambda: r.packets)
    assert r.tnc.stats.rejected == 1


# ---- the line dies and comes back

async def test_the_line_dropping_is_waiting_with_a_reason_and_the_port_is_reopened() -> None:
    radio = FakeRadio()
    await radio.start()
    radio.refuse()                                               # nobody is listening yet
    tnc = Tnc(radio.url, backoff=tiny_backoff(), fallback_probe=False)
    await tnc.start()
    try:
        assert tnc.state is Source.State.WAITING and REFUSED in tnc.problem
        await radio.accept()                                     # the radio is up
        await until(lambda: tnc.state is Source.State.CONNECTED)
        await radio.connected()
        assert tnc.stats.opens == 1 and tnc.problem == ""
        radio.drop()                                             # and gone
        await until(lambda: tnc.state is Source.State.WAITING)
        assert tnc.problem and tnc.last_error and "lost" in tnc.last_error
        await until(lambda: tnc.state is Source.State.CONNECTED)       # it listens still: the next attempt connects
        assert tnc.stats.opens == 2
        radio.feed(kiss_of(ui_frame()))
        await until(lambda: tnc.stats.packets == 1)
    finally:
        await tnc.stop()
        await radio.aclose()
    assert tnc.state is Source.State.STOPPED


async def test_stop_closes_the_port_and_cancels_the_retry() -> None:
    radio = FakeRadio()
    await radio.start()
    radio.refuse()
    tnc = Tnc(radio.url, backoff=Backoff([30.0]), fallback_probe=False)
    await tnc.start()
    assert tnc.state is Source.State.WAITING
    await tnc.stop()
    assert tnc.state is Source.State.STOPPED and len(tnc._tasks) == 0
    await radio.accept()
    tnc = Tnc(radio.url, fallback_probe=False)
    await tnc.start()
    await tnc.stop()
    try:
        await tnc.start()                                        # the port was closed, so it opens again
        assert tnc.state is Source.State.CONNECTED and tnc.stats.opens == 2
        await until(lambda: radio.connections == 2)
    finally:
        await tnc.stop()
        await radio.aclose()


async def test_a_tcp_port_is_a_socket_port_and_a_tnc_on_it_says_no_speed() -> None:
    radio = FakeRadio()
    await radio.start()
    tnc = Tnc(radio.url.replace("socket://", "tcp://"), fallback_probe=False)
    try:
        await tnc.start()
        assert tnc.state is Source.State.CONNECTED and tnc.describe() == f"{radio.url.replace('socket://', 'tcp://')}, listening, 0 packets"
        assert any(line.endswith(f"opened tcp://127.0.0.1:{radio.port}") for line in tnc.lines)
    finally:
        await tnc.stop()
        await radio.aclose()


async def test_a_tnc_on_a_socket_is_never_asked_whether_the_radio_is_there() -> None:
    """A TCP KISS TNC has no command mode: no keep-alive check, no carriage return after silence; a profile of a command-mode TNC says otherwise."""
    radio = FakeRadio()
    await radio.start()
    tnc = Tnc(radio.url, profile=KISS_TCP, fallback_probe=False, check_sec=0.1, check_pause_sec=0.02, reply_sec=0.02, answer_sec=0.05)
    try:
        await tnc.start()
        await idle_for(0.5)
        assert await radio.said(1, 0.1) == b"" and tnc.stats.keepalive_checks == 0 and tnc._watchdog_task is None
        assert tnc.state is Source.State.CONNECTED
        tnc.profile = KENWOOD_TNC2                               # a profile that says the TNC can be asked
        tnc.set_check(0.1)
        assert KISS_EXIT in await radio.said(3, 2.0)
    finally:
        await tnc.stop()
        await radio.aclose()


async def test_a_radio_that_is_not_there_is_waiting_and_a_later_one_is_found() -> None:
    radio = FakeRadio()
    await radio.start()
    radio.refuse()
    tnc = Tnc(radio.url, fallback_probe=False, backoff=tiny_backoff())
    try:
        await tnc.start()
        await until(lambda: tnc.state is Source.State.WAITING, 10.0)          # (Windows takes about two seconds to refuse a connection)
        assert tnc.stats.opens == 0 and tnc.problem == f"{radio.url}: {REFUSED}"
        await radio.accept()
        await until(lambda: tnc.state is Source.State.CONNECTED)
    finally:
        await tnc.stop()
        await radio.aclose()


# ---- where the radio is not looked for

async def test_where_the_ports_are_not_searched_a_tnc_with_no_port_says_to_choose_one(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(serialprobe, "sys", SimpleNamespace(platform="win32"))
    tnc = Tnc(pattern=str(tmp_path / "*"), backoff=tiny_backoff())
    try:
        await tnc.start()
        assert tnc.state is Source.State.WAITING and tnc.problem.startswith("no port is chosen") and "settings" in tnc.problem
    finally:
        await tnc.stop()


async def test_where_the_ports_are_not_searched_a_named_port_that_fails_is_tried_again_not_replaced_by_a_search(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(serialprobe, "sys", SimpleNamespace(platform="darwin"))
    radio = FakeRadio()
    await radio.start()
    radio.refuse()
    tnc = Tnc(radio.url, backoff=tiny_backoff(), fallback_probe=True)
    try:
        await tnc.start()
        problems: set[str] = set()
        for _ in range(8):
            await asyncio.sleep(0.03)
            problems.add(tnc.problem)
        assert problems - {""} == {f"{radio.url}: {REFUSED}"}, "the problem is always the named port's, never the search's"
        await radio.accept()
        await until(lambda: tnc.state is Source.State.CONNECTED)
    finally:
        await tnc.stop()
        await radio.aclose()


# ---- sending

@stops_rigs
async def test_send_frame_writes_the_kiss_framed_bytes_and_emits_an_out_packet(rig: Rigs) -> None:
    r = await rig()
    frame = ui_frame("OH2GBA-9", b"!6010.00N/02456.00E>\xc0\xdb mice")      # an information field that needs both escapes
    assert r.tnc.send_frame(frame) is True
    wire = kiss_of(frame)
    assert await r.radio.said(len(wire)) == wire
    assert kiss.KissDecoder().feed(wire)[0].payload == ax25.encode(frame)
    assert [(p.direction, p.source, p.raw, p.kind) for p in r.packets] == [("out", "OH2GBA-9", ax25.encode(frame), "position")]
    assert r.packets[0].path == ("WIDE1-1",) and r.tnc.stats.bytes_out == len(wire) and r.tnc.stats.packets == 0


@stops_rigs
async def test_send_takes_raw_ax25_bytes(rig: Rigs) -> None:
    r = await rig()
    raw = ax25.encode(ui_frame())
    assert await r.tnc.send(raw) is True
    assert await r.radio.said(len(raw) + 3) == kiss.encode(raw)
    assert await r.tnc.send(b"junk") is False and len(r.packets) == 1


@stops_rigs
async def test_nothing_is_sent_when_stopped_or_waiting_or_restarting(rig: Rigs, tmp_path: Path) -> None:
    waiting = Tnc(str(tmp_path / "nothing"), backoff=Backoff([30.0]), fallback_probe=False)
    assert waiting.send_frame(ui_frame()) is False
    await waiting.start()
    assert waiting.send_frame(ui_frame()) is False
    await waiting.stop()
    r = await rig()
    r.radio.feed(b"cmd:")
    assert await r.radio.said(len(ENTER_KISS)) == ENTER_KISS
    assert r.tnc.send_frame(ui_frame()) is False, "the TNC is restarting"
    await idle_for(SETTLE + 0.1)
    assert r.tnc.send_frame(ui_frame()) is True
    await r.tnc.stop()
    assert r.tnc.send_frame(ui_frame()) is False and len(r.packets) == 1


@stops_rigs
async def test_a_line_that_is_gone_is_lost_and_nothing_is_sent_on_it(rig: Rigs) -> None:
    r = await rig()
    r.radio.refuse()
    r.radio.drop()
    await until(lambda: r.tnc.state is Source.State.WAITING)           # (the reader finds the line gone)
    assert any("lost" in line for line in r.tnc.lines)
    assert r.tnc.send_frame(ui_frame()) is False
    assert r.packets == [] and r.tnc.stats.bytes_out == 0


# ---- the mode detector

KISS_PACKET = kiss_of(ui_frame(info=b"cmd: this frame happens to say cmd: in its text"))


def test_the_monitor_line_and_the_prompt_are_command_mode() -> None:
    assert ModeDetector().feed(MONITOR_LINE) is Mode.MONITOR
    assert ModeDetector().feed(b"OH2FZV-2>VP1R61,WIDE1,OH2RCH-2*:...\r\n") is Mode.MONITOR
    assert ModeDetector().feed(b"\n\r\ncmd:") is Mode.MONITOR
    assert ModeDetector().feed(b"KISS ON\r\nKISS     was OFF\r\ncmd:\x11\x11") is Mode.MONITOR
    assert ModeDetector().feed(b"OH2RDG>APN391:!6007.47NN02429.82E#") is Mode.MONITOR
    assert ModeDetector().feed(b"OH2AAA>APRS:text") is Mode.MONITOR


def test_a_line_that_arrives_in_pieces_is_found_when_its_colon_comes() -> None:
    d = ModeDetector()
    assert [d.feed(chunk) for chunk in (b"OH2FZV-2>VP1R", b"61,WIDE1,OH2RC", b"H-2*", b":!60")] == [Mode.UNKNOWN, Mode.UNKNOWN, Mode.UNKNOWN, Mode.MONITOR]


@pytest.mark.parametrize("text", [b"", b"hello world\r\n", b"\r", b"cmd", b"OH2FZV-2>:", b"OH2FZV-2 > VP1R61:x", b"$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47\r\n", b"\x00\x01\x02\xff"])
def test_other_bytes_are_not_taken_for_command_mode(text: bytes) -> None:
    assert ModeDetector().feed(text) is Mode.UNKNOWN


def test_a_kiss_stream_is_kiss_and_the_whole_fixture_never_looks_like_command_mode() -> None:
    d = ModeDetector()
    data = fixture_bytes("kiss/thd7-2026-10-21.bin")
    seen = {d.feed(data[i:i + 1]) for i in range(len(data))}
    assert Mode.MONITOR not in seen and d.mode is Mode.KISS


def test_the_letters_cmd_inside_a_frame_are_not_the_prompt_at_any_point_of_the_frame() -> None:
    d = ModeDetector()
    seen = [d.feed(bytes([b])) for b in KISS_PACKET]
    assert Mode.MONITOR not in seen and seen[-1] is Mode.KISS
    assert ModeDetector().feed(kiss.encode(b"cmd:")) is Mode.UNKNOWN, "a frame that is not AX.25 is not KISS, and not text either"
    assert ModeDetector().feed(kiss.encode(b"OH2FZV-2>VP1R61:text")) is Mode.UNKNOWN


def test_kiss_stays_kiss_and_a_frame_that_is_not_ui_or_not_command_zero_does_not_count() -> None:
    d = ModeDetector()
    assert d.feed(KISS_PACKET) is Mode.KISS
    assert d.feed(b"cmd:") is Mode.KISS
    not_ui = ax25.encode(ax25.Frame(ax25.Address("APRS"), ax25.Address("OH2GBA"), control=0x3F))
    assert ModeDetector().feed(kiss.encode(not_ui)) is Mode.UNKNOWN
    assert ModeDetector().feed(kiss.encode(ax25.encode(ui_frame()), command=1)) is Mode.UNKNOWN


def test_text_then_a_kiss_frame_ends_as_kiss() -> None:
    d = ModeDetector()
    assert d.feed(MONITOR_LINE) is Mode.MONITOR
    assert d.feed(KISS_PACKET) is Mode.KISS


def test_rearming_the_detector_forgets_kiss_and_what_was_half_read() -> None:
    d = ModeDetector()
    assert d.feed(KISS_PACKET) is Mode.KISS
    d.rearm()
    assert d.mode is Mode.UNKNOWN
    assert d.feed(b"\n\r\ncmd:") is Mode.MONITOR, "the prompt is read again"
    d.rearm()
    assert d.feed(KISS_PACKET[:-1]) is Mode.UNKNOWN
    d.rearm()
    assert d.feed(KISS_PACKET[-1:]) is Mode.UNKNOWN, "the bytes before the rearm are not part of the next frame"
    assert d.feed(KISS_PACKET) is Mode.KISS


# ---- the keep-alive

QUICK = {"check_sec": 0.3, "check_pause_sec": 0.05, "reply_sec": 0.2, "answer_sec": 0.3}
NUDGE_BYTE = b"\r"


async def hear_until(radio: FakeRadio, wanted: bytes, timeout_sec: float = 3.0) -> bytes:
    """Everything the port wrote up to and including `wanted`; fails if it does not come."""
    out = b""
    deadline = asyncio.get_running_loop().time() + timeout_sec
    while wanted not in out:
        assert asyncio.get_running_loop().time() < deadline, f"{wanted!r} did not come, only {out!r}"
        out += await radio.said(1, 0.05)
    end = out.index(wanted) + len(wanted)
    radio.put_back(out[end:])                       # (what came after it in the same read is for the next look)
    return out[:end]


def nothing_runs(tnc: Tnc) -> None:
    assert tnc.state is Source.State.STOPPED and len(tnc._tasks) == 0 and tnc._port is None


def news(caplog: pytest.LogCaptureFixture, level: int = logging.INFO) -> list[str]:
    """What the daemon told at this level or above."""
    return [rec.getMessage() for rec in caplog.records if rec.levelno >= level and rec.name.startswith("neoaprs")]


async def confirmed_rig(rig: Rigs, **kwargs: object) -> Rig:
    """A Tnc whose line has shown that the radio is there (a packet came), with the keep-alive on from now: its quiet period is `check_sec`."""
    r = await rig(**{**QUICK, "check_sec": 0.0, **kwargs})
    r.radio.feed(kiss_of(ui_frame()))
    await until(lambda: r.packets)
    r.tnc.set_check(float(kwargs.get("check_sec", QUICK["check_sec"])))             # type: ignore[arg-type]
    return r


@stops_rigs
async def test_a_quiet_line_gets_the_check_after_check_sec_the_radio_sees_exit_return_and_kiss_on_in_order_and_nothing_is_sent_meanwhile(rig: Rigs) -> None:
    r = await confirmed_rig(rig)
    begun = asyncio.get_running_loop().time()
    assert await hear_until(r.radio, KISS_EXIT + NUDGE_BYTE + ENTER_KISS) == KISS_EXIT + NUDGE_BYTE + ENTER_KISS, "nothing else, and in this order"
    assert asyncio.get_running_loop().time() - begun >= 0.25
    assert (r.tnc.stats.keepalive_checks, r.tnc.last_watchdog_action) == (1, "check")
    assert r.tnc.state is Source.State.CONNECTED and r.tnc.usable is False, "the check is under way"
    assert r.tnc.send_frame(ui_frame()) is False and await r.radio.said(1, 0.05) == b""
    assert any("not sent: the TNC is restarting into KISS mode" in line for line in r.tnc.lines)


@stops_rigs
async def test_a_cmd_prompt_in_answer_keeps_the_radio_connected_and_the_clock_restarts_from_it_and_nothing_is_told(rig: Rigs, caplog: pytest.LogCaptureFixture) -> None:
    r = await rig(clock=FixedClock(), **QUICK)
    caplog.set_level(logging.INFO)
    caplog.clear()
    await hear_until(r.radio, KISS_EXIT + NUDGE_BYTE)
    r.radio.feed(b"\r\ncmd:")
    answered = asyncio.get_running_loop().time()
    assert await hear_until(r.radio, ENTER_KISS)
    assert r.tnc.state is Source.State.CONNECTED and r.tnc.usable is False, "settling"
    await until(lambda: r.tnc.usable, 2.0)
    assert r.tnc.state is Source.State.CONNECTED and r.tnc.silent_since is None
    await until(lambda: r.tnc.stats.keepalive_checks == 2, 3.0)
    assert asyncio.get_running_loop().time() - answered >= 0.25, "the next check is a period after the answer"
    assert news(caplog) == [] and r.tnc.problem == ""


@stops_rigs
async def test_a_check_that_nothing_answers_makes_the_radio_silent_with_one_warning(rig: Rigs, caplog: pytest.LogCaptureFixture) -> None:
    r = await rig(clock=FixedClock(), **QUICK)
    caplog.set_level(logging.INFO)
    caplog.clear()
    await until(lambda: r.tnc.state is Source.State.SILENT, 3.0)
    assert news(caplog) == ["tnc: the radio is silent: nothing heard since 12:00 UTC, no answer to a check; probing every 30 s"]
    assert [rec.levelno for rec in caplog.records if rec.name.startswith("neoaprs")] == [logging.WARNING]
    assert r.tnc.usable is False and r.tnc.stats.keepalive_checks == 1 and r.tnc.stats.watchdog_probes == 0


@stops_rigs
async def test_no_check_is_made_while_packets_flow(rig: Rigs) -> None:
    r = await confirmed_rig(rig)
    for _ in range(10):
        r.radio.feed(kiss_of(ui_frame()))                          # (twice as often as check_sec)
        await idle_for(0.15)
    assert r.tnc.stats.keepalive_checks == 0 and len(r.packets) == 11 and r.tnc.usable          # (the one that confirmed the line, and ten)
    assert await r.radio.said(1, 0.05) == b""
    assert await hear_until(r.radio, KISS_EXIT)                     # and when they stop, the check comes


@stops_rigs
async def test_bytes_that_are_not_a_packet_count_as_heard(rig: Rigs) -> None:
    r = await confirmed_rig(rig)
    for _ in range(10):
        r.radio.feed(b"\x00noise")
        await idle_for(0.1)
    assert r.tnc.stats.keepalive_checks == 0 and await r.radio.said(1, 0.05) == b""


@stops_rigs
async def test_check_sec_zero_does_nothing_and_a_new_period_counts_at_once(rig: Rigs) -> None:
    r = await rig(**{**QUICK, "check_sec": 0.0})
    await idle_for(0.4)
    assert await r.radio.said(1, 0.1) == b"" and r.tnc._watchdog_task is None and r.tnc.stats.keepalive_checks == 0
    r.tnc.set_check(0.1)                                             # the operator saved a period
    assert await hear_until(r.radio, KISS_EXIT, 2.0)
    r.tnc.set_check(0.0)                                             # and took it away again, in the middle of a check
    await idle_for(0.1)
    assert r.tnc._watchdog_task is None and r.tnc._looking is False
    await r.radio.said(4096, 0.05)
    await idle_for(0.4)
    assert await r.radio.said(1, 0.1) == b"" and r.tnc.stats.keepalive_checks == 1


@stops_rigs
async def test_a_tnc_that_is_not_to_enter_kiss_is_not_checked(rig: Rigs) -> None:
    r = await rig(profile=NO_DETECT, **QUICK)
    await idle_for(0.6)
    assert await r.radio.said(1, 0.05) == b"" and r.tnc._watchdog_task is None and r.tnc.state is Source.State.CONNECTED


@stops_rigs
async def test_stop_in_the_pause_of_a_check_leaves_nothing_running_and_never_sends_kiss_on(rig: Rigs) -> None:
    r = await rig(**{**QUICK, "check_pause_sec": 30.0})
    assert await hear_until(r.radio, KISS_EXIT) == KISS_EXIT
    await r.tnc.stop()
    nothing_runs(r.tnc)
    assert r.tnc.stats.keepalive_checks == 1 and r.tnc._looking is False and await r.radio.said(1, 0.3) == b""


@stops_rigs
async def test_stop_while_the_check_waits_for_an_answer_leaves_nothing_running(rig: Rigs) -> None:
    r = await rig(**{**QUICK, "answer_sec": 30.0})
    assert await hear_until(r.radio, ENTER_KISS)
    await r.tnc.stop()
    nothing_runs(r.tnc)
    assert r.tnc.state is Source.State.STOPPED and r.tnc._looking is False


async def test_a_line_that_is_lost_and_opened_again_starts_the_quiet_period_over() -> None:
    radio = FakeRadio()
    await radio.start()
    tnc = Tnc(radio.url, backoff=tiny_backoff(), fallback_probe=False, settle_sec=SETTLE, **QUICK)
    await tnc.start()
    try:
        assert await hear_until(radio, KISS_EXIT) == KISS_EXIT     # (so the radio has accepted the connection)
        radio.refuse()
        radio.drop()
        await until(lambda: tnc.state is Source.State.WAITING)
        assert tnc._watchdog_task is None and tnc._looking is False
        await radio.accept()
        await until(lambda: tnc.state is Source.State.CONNECTED)
        assert await hear_until(radio, KISS_EXIT) == KISS_EXIT and tnc.stats.keepalive_checks == 2
    finally:
        await tnc.stop()
        await radio.aclose()
    nothing_runs(tnc)
