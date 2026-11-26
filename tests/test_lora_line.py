"""Tests for a LoRa APRS board's line read by the Tnc (neoaprs/loraboard.py) with the fake board of
tests/support/fakelora.py: KISS and TNC2 variants, Bluetooth and BLE roles, and the rules that no
KISS ON is ever sent and a board on USB without a port only waits.
"""

import functools
from types import SimpleNamespace
import socket
from collections.abc import Awaitable, Callable

import pytest

from neoaprs import ax25, kiss, loralist
from neoaprs.loraboard import TEXT_LINES, KissText
from neoaprs.packet import Packet
from neoaprs.source import Backoff, Source
from neoaprs.tnc import Tnc
from neoaprs.tnc2line import frame_of, text_of
from neoaprs.tncprofile import LORA_NUDGE, LORA_SERIAL, LORA_TCP, Profile
from neoaprs.claims import Claims
from neoaprs.radiospec import RadioSpec
from neoaprs.radiohealth import radio_health
from neoaprs.web.radioview import problem_row
from tests.support.env import until
from tests.support.fakelora import HEADER, Board, BoardOnTcp, board_on_ble

HEARD = b"OH2ABC-7>APLRT1,WIDE1-1:!6010.00N/02456.00E>tracker"
OURS = frame_of(b"OH2GBA>APZNEO,WIDE1-1:=6010.00N/02456.00E-NeoAPRS")
BLE = "ble://00:11:22:33:44:55"


@pytest.fixture(autouse=True)
def no_list(monkeypatch: pytest.MonkeyPatch) -> object:
    """The iGate's list is asked of a port that refuses (a socket bound and not listening): these
    boards have no list, as a Tracker has none, and port 80 of the machine is never asked."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    monkeypatch.setattr(loralist, "PORT", sock.getsockname()[1])
    yield
    sock.close()


class Line:
    def __init__(self, tnc: Tnc) -> None:
        self.tnc = tnc
        self.packets: list[Packet] = []
        tnc.packet.connect(self.packets.append)

    @property
    def heard(self) -> list[bytes]:
        return [text_of(ax25.decode(p.raw)) for p in self.packets if p.direction == "in"]


class Lines:
    """The Tncs and the boards' ends a test made, stopped and closed when it ends (`stops`)."""

    def __init__(self) -> None:
        self.tncs: list[Tnc] = []
        self.ends: list[BoardOnTcp] = []


@pytest.fixture
def lines() -> Lines:
    return Lines()


def stops(test: Callable[..., Awaitable[None]]) -> Callable[..., Awaitable[None]]:
    """The tasks of a Tnc must be gone before the leak guard looks, which is before a fixture is
    torn down: the test body is wrapped."""

    @functools.wraps(test)
    async def wrapper(*args: object, **kwargs: Lines) -> None:
        try:
            await test(*args, **kwargs)
        finally:
            for tnc in kwargs["lines"].tncs:
                await tnc.stop()
            for end in kwargs["lines"].ends:
                await end.aclose()

    return wrapper


async def board_end(lines: Lines, board: Board) -> BoardOnTcp:
    end = BoardOnTcp(board)
    lines.ends.append(end)
    await end.start()
    return end


async def line_on(lines: Lines, board: Board | None, profile: Profile, url: str = "") -> tuple[Line, BoardOnTcp | None]:
    end = await board_end(lines, board) if board is not None else None
    tnc = Tnc(
        url or (end.url if end is not None else ""),
        profile=profile,
        check_sec=0.0,
        backoff=Backoff([0.05, 0.05, 0.05]),
        fallback_probe=False,
        settle_sec=0.0,
    )
    lines.tncs.append(tnc)
    await tnc.start()
    if end is not None:
        await end.connected()
    return Line(tnc), end


def never_command_mode(tnc: Tnc) -> None:
    assert (
        not any("command mode" in line or "KISS ON" in line for line in tnc.lines) and "command mode" not in tnc.problem
    ), "a board knows no command mode"


@stops
async def test_the_igate_on_the_network_speaks_kiss_both_ways_and_says_no_signal_on_its_kiss_line(lines: Lines) -> None:
    board = Board("igate")
    line, end = await line_on(lines, board, LORA_TCP)
    assert end is not None and line.tnc.usable
    board.air(HEARD)
    await until(lambda: line.heard == [HEARD])
    packet = line.packets[0]
    assert (packet.source, packet.radio_id, packet.snr, packet.rssi) == ("OH2ABC-7", line.tnc.radio_id, None, None), (
        "the iGate's KISS line says no signal (its list does: tests/test_lora_signal.py)"
    )
    assert line.tnc.send_frame(OURS)
    await until(lambda: board.transmitted == [HEADER + text_of(OURS)])
    assert board.writes == [kiss.encode(ax25.encode(OURS))], "only our frame was written: no entry, no probe, no nudge"
    never_command_mode(line.tnc)


def escaped(escapes: int) -> ax25.Frame:
    """A frame of 250 bytes, the most a LoRa radio carries, whose text has this many bytes that KISS
    escapes (0xDB, the lead byte of an Arabic letter)."""
    info = b">" + "\u06db".encode() * escapes
    return frame_of(b"OH2GBA>APZNEO:" + info + b"x" * (250 - len(ax25.encode(frame_of(b"OH2GBA>APZNEO:" + info)))))


@stops
async def test_a_frame_whose_kiss_the_board_cannot_take_is_refused_with_its_reason_and_not_reported_as_sent(
    lines: Lines,
) -> None:
    board = Board("igate")
    line, _ = await line_on(lines, board, LORA_TCP)
    assert line.tnc.usable and len(ax25.encode(escaped(4))) == len(ax25.encode(escaped(3))) == 250
    assert not line.tnc.send_frame(escaped(4)), (
        "four escapes make 257 bytes of KISS, and the iGate clears its input past 255 before the closing FEND"
    )
    assert any("not sent: 257 bytes in KISS, the radio takes 256" in text for text in line.tnc.lines) and not [
        p for p in line.packets if p.direction == "out"
    ]
    assert line.tnc.send_frame(escaped(3))
    await until(lambda: board.transmitted == [HEADER + text_of(escaped(3))])
    assert board.writes == [kiss.encode(ax25.encode(escaped(3)))], "the frame refused was never written"


@stops
async def test_the_igate_on_usb_speaks_kiss_and_its_log_lines_go_to_the_terminal_only(lines: Lines) -> None:
    board = Board("igate")
    end = await board_end(lines, board)
    line, _ = await line_on(lines, None, LORA_SERIAL, end.url)
    await end.connected()
    board.log("init : TNC Serial  ...     done!")
    board.air(HEARD)
    await until(lambda: line.heard == [HEARD])
    assert (
        any("init : TNC Serial" in text for text in line.tnc.lines) and line.tnc.stats.rejected == 0 and line.tnc.usable
    ), "a line of its log is no packet, no fault and no text mode"
    assert line.tnc.send_frame(OURS)
    await until(lambda: board.transmitted == [HEADER + text_of(OURS)])
    never_command_mode(line.tnc)


@stops
async def test_the_igate_left_in_tnc2_text_is_received_and_sends_nothing_until_it_is_set_to_kiss(lines: Lines) -> None:
    board = Board("igate", kiss=False)
    line, end = await line_on(lines, board, LORA_TCP)
    assert end is not None
    board.air(HEARD)
    await until(lambda: line.heard == [HEARD])
    assert not line.tnc.usable and line.tnc.why_unusable() == TEXT_LINES and line.tnc.problem == TEXT_LINES
    assert not line.tnc.send_frame(OURS) and board.transmitted == []
    spec = RadioSpec(3, "lora", LORA_TCP.key, "", True, 3)
    assert problem_row(radio_health(spec, (spec,), SimpleNamespace(line=line.tnc, driver_key="tnc"), Claims())) == {
        "code": "radio.text_lines",
        "params": {},
    }, "the radio's row says it in the page's words: set the board to KISS"
    assert any(f"not sent: {TEXT_LINES}" in text for text in line.tnc.lines)
    assert board.writes == [LORA_NUDGE], "the nudge alone, once: the iGate in TNC2 reads it as no line"
    board.air(HEARD.replace(b"tracker", b"again"))
    await until(lambda: len(line.heard) == 2)
    assert board.writes == [LORA_NUDGE], "once an open"
    # (the operator sets it to KISS on the board's page, and the board restarts: its clients are
    # dropped)
    board.restart(kiss=True)
    end.drop()
    await until(lambda: line.tnc.stats.opens == 2 and line.tnc.state is Source.State.CONNECTED and end.clients == 1)
    assert line.tnc.usable and line.tnc.problem == "", "a fresh open: the text of the last one holds nothing back"
    assert problem_row(radio_health(spec, (spec,), SimpleNamespace(line=line.tnc, driver_key="tnc"), Claims())) is None
    board.air(HEARD)
    await until(lambda: len(line.heard) == 3 and line.tnc.usable)
    assert line.tnc.problem == "" and line.tnc.send_frame(OURS)
    await until(lambda: board.transmitted == [HEADER + text_of(OURS)])
    never_command_mode(line.tnc)


@stops
async def test_the_tracker_on_classic_bluetooth_sends_text_until_the_nudge_turns_it_to_kiss(lines: Lines) -> None:
    board = Board("tracker")
    line, end = await line_on(lines, board, LORA_SERIAL)
    assert end is not None and not board.kiss
    board.air(HEARD)
    await until(lambda: line.heard == [HEARD] and board.writes == [LORA_NUDGE])
    assert board.kiss and board.transmitted == [], (
        "any KISS frame turns the Tracker's answers to KISS; a command frame is not keyed"
    )
    assert line.tnc.why_unusable() == TEXT_LINES
    board.air(HEARD.replace(b"tracker", b"in KISS"))
    await until(lambda: len(line.heard) == 2 and line.tnc.usable)
    assert line.tnc.problem == "" and any("the board sends KISS" in text for text in line.tnc.lines)
    assert line.tnc.send_frame(OURS)
    await until(lambda: board.transmitted == [HEADER + text_of(OURS)])
    never_command_mode(line.tnc)


@stops
async def test_the_igates_bridge_hands_on_the_internet_which_is_passed_over_and_counted(lines: Lines) -> None:
    board = Board("igate")
    line, end = await line_on(lines, board, LORA_TCP)
    assert end is not None
    board.internet(b"OH2XYZ>APRS,TCPIP*,qAC,T2FINLAND:>from the internet")
    board.internet(b"OH2XYZ-9>APRS,qAR,OH2LRG-10:>gated elsewhere")
    board.air(HEARD)
    await until(lambda: line.heard == [HEARD])
    assert line.tnc.stats.frames_in == 3 and line.tnc.stats.packets == 1 and line.tnc.stats.rejected == 0
    assert sum("from the internet, not heard on the air: passed over" in text for text in line.tnc.lines) == 2


@stops
async def test_the_tracker_over_bluetooth_le_on_its_kiss_service(lines: Lines, monkeypatch: pytest.MonkeyPatch) -> None:
    board = Board("tracker-ble")
    ble = board_on_ble(monkeypatch, board)
    line, _ = await line_on(lines, None, LORA_SERIAL, BLE)
    assert line.tnc.state is Source.State.CONNECTED and ble.notifying == "00000003-ba2a-46c9-ae49-01b0961f68bb"
    board.air(HEARD)
    await until(lambda: line.heard == [HEARD])
    assert line.tnc.send_frame(OURS)
    await until(lambda: board.transmitted == [HEADER + text_of(OURS)])
    never_command_mode(line.tnc)


@stops
async def test_the_tracker_over_bluetooth_le_on_its_nordic_uart_has_the_roles_the_other_way_round_and_sends_text(
    lines: Lines, monkeypatch: pytest.MonkeyPatch
) -> None:
    uart = Board("tracker-ble", kiss=False)
    ble = board_on_ble(monkeypatch, uart)
    line, _ = await line_on(lines, None, LORA_SERIAL, BLE + "/nus")
    assert ble.notifying == "6e400002-b5a3-f393-e0a9-e50e24dcca9e", (
        "the Tracker notifies on 6E400002, which Nordic's own service writes to"
    )
    uart.air(HEARD)
    await until(lambda: line.heard == [HEARD])
    assert line.tnc.why_unusable() == TEXT_LINES, (
        "TNC2 over its Nordic UART: received, and nothing sent; KISS is its other service, set on the Tracker"
    )
    assert not line.tnc.send_frame(OURS)
    uart.air(HEARD)
    await until(lambda: len(line.heard) == 2)
    assert uart.writes == [] and uart.transmitted == [], (
        "the Tracker keys every write on its TNC2 service: no nudge and no frame is written to it"
    )
    never_command_mode(line.tnc)


@stops
async def test_esp32_loraprs_says_its_battery_in_a_command_that_is_a_line_of_the_terminal_and_no_fault(
    lines: Lines,
) -> None:
    board = Board("esp32")
    line, end = await line_on(lines, board, LORA_SERIAL)
    assert end is not None
    board.battery(4.12)
    board.air(HEARD)
    await until(lambda: line.heard == [HEARD])
    assert line.tnc.stats.rejected == 0 and any(
        "KISS command 9 from the board: passed over" in text for text in line.tnc.lines
    )
    assert not any(text.startswith("rejected") or " rejected," in text for text in line.tnc.lines)


@stops
async def test_a_board_on_usb_without_its_port_waits_for_it_and_is_never_searched_for(lines: Lines) -> None:
    tnc = Tnc("", profile=LORA_SERIAL, check_sec=0.0, backoff=Backoff([5.0]), fallback_probe=False)
    lines.tncs.append(tnc)
    await tnc.start()
    assert tnc.state is Source.State.WAITING and "choose the radio's port" in tnc.problem and tnc.searching == []


def test_the_line_is_cut_into_kiss_frames_and_the_text_between_them() -> None:
    split = KissText()
    data = (
        b"log line\r\n"
        + kiss.encode(b"\x01\x02")
        + b"OH2ABC>APRS:>text\r\n"
        + kiss.encode(b"\x03", command=7)[:-1]
        + b"\x00\x04"
        + b"\xc0"
    )
    items = split.feed(data[:7]) + split.feed(data[7:])
    assert items == [
        b"log lin",
        b"e\r\n",
        kiss.KissFrame(0, 0, b"\x01\x02"),
        b"OH2ABC>APRS:>text\r\n",
        kiss.KissFrame(0, 7, b"\x03\x00\x04"),
    ]
    assert split.feed(b"\xc0\x09\x01\x02\xc0\x09\x05\xc0") == [
        kiss.KissFrame(0, 9, b"\x01\x02"),
        kiss.KissFrame(0, 9, b"\x05"),
    ], "a frame that shares its FEND with the one before"
    assert split.feed(b"\xc0OH2ABC>APRS:>after a FEND alone\n") == [b"OH2ABC>APRS:>after a FEND alone\n"]
