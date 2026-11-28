"""Tests for the signal of what a LoRa APRS board hears (neoaprs/lorasignal.py, loralist.py) with
the fake board of tests/support/fakelora.py: the heard list, matching frames to entries, giving up
after one failure, DL9SAU's path element, and KISS command 7."""

import asyncio
import logging
import socket
from collections.abc import Iterator
from typing import Any

import pytest

from neoaprs import ax25, loraboard, loralist
from neoaprs.lorasignal import console_line, from_internet, list_key, ninth_element, path_reading, signal_report
from neoaprs.reading import Reading
from neoaprs.tnc2line import frame_of, text_of
from neoaprs.tncprofile import LORA_CONSOLE, LORA_SERIAL, LORA_TCP
from tests.support.env import until
from tests.support.fakelora import Board, ListServer, decapsulate, encode_kiss, q_element
from tests.test_lora_line import Lines, line_on, stops
from tests.support.logs import warnings_in

HEARD = b"OH2ABC-7>APLRT1,WIDE1-1:!6010.00N/02456.00E>tracker"


@pytest.fixture
def lines() -> Lines:
    return Lines()


@pytest.fixture(autouse=True)
def refused_list(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The list is asked of a port that refuses unless a test gives it a server: port 80 of the
    machine is never asked."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    monkeypatch.setattr(loralist, "PORT", sock.getsockname()[1])
    yield
    sock.close()


async def listed(monkeypatch: pytest.MonkeyPatch, board: Board, answer: str = "list") -> ListServer:
    server = await ListServer(board).start()
    server.answer = answer
    monkeypatch.setattr(loralist, "PORT", server.port)
    return server


# ---- pure


def test_dl9sau_elements_are_taken_off_the_path_and_the_first_is_read() -> None:
    frame = frame_of(b"OH2ABC-7>APLOX1,WIDE1-1*,QA7L2,Q2373:>x")
    bare, reading = path_reading(frame)
    assert text_of(bare) == b"OH2ABC-7>APLOX1,WIDE1-1*:>x" and reading == Reading(snr=-7.0, rssi=-112.0)
    assert path_reading(frame_of(b"OH2ABC>APRS,QAC,Q2373-1,QZ7L2:>x")) == (
        frame_of(b"OH2ABC>APRS,QAC,Q2373-1,QZ7L2:>x"),
        None,
    ), "a q-construct, an SSID and a letter past J are no element"


def test_the_element_after_eight_digipeaters_is_found_only_where_it_makes_one_address_too_many() -> None:
    def board_bytes(text: bytes) -> bytes:
        return decapsulate(encode_kiss(text))  # (the AX.25 bytes as the board writes them)

    eight, element = (
        board_bytes(b"A>B,C1,C2,C3,C4,C5,C6,C7,C8:>x"),
        board_bytes(b"A>B,C1,C2,C3,C4,C5,C6,C7,C8,QA7L2:>x"),
    )
    with pytest.raises(ax25.Ax25Error, match="more than 8 digipeaters"):
        ax25.decode(element)
    assert (
        ninth_element(element) == (eight, Reading(snr=-7.0, rssi=-112.0))
        and text_of(ax25.decode(eight)) == b"A>B,C1,C2,C3,C4,C5,C6,C7,C8:>x"
    )
    assert (
        ninth_element(eight) is None and ninth_element(board_bytes(b"A>B,C1,C2,C3,C4,C5,C6,C7,C8,WIDE2:>x")) is None
    ), "an address that is no element is left: the frame is refused as before"
    assert ninth_element(board_bytes(b"A>B,C1,C2,C3,C4,C5,C6,C7,QA7L2:>x")) is None, (
        "within AX.25's eight, path_reading takes it"
    )


def test_the_lists_entries_that_are_none_are_passed_over_and_an_answer_that_is_no_list_is_refused() -> None:
    def answer(body: str) -> bytes:
        return b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n" + body.encode()

    good = '{"rxDate": "2026-11-15", "rxTime": "12:00:01", "packet": "A>B:x", "RSSI": -97, "SNR": 6.25}'
    bad = [
        '{"packet": "A>B:y", "RSSI": NaN, "SNR": 1}',
        '{"packet": "A>B:y", "RSSI": -90, "SNR": 1e999}',
        '{"packet": "A>B:y", "RSSI": 1' + "0" * 400 + ', "SNR": 1}',
        '{"packet": 7, "RSSI": -90, "SNR": 1}',
        '{"RSSI": -90, "SNR": 1}',
        '"text"',
        '{"packet": "A>B:y", "RSSI": "loud", "SNR": 1}',
    ]
    assert loralist.parse(answer(f"[{good}, {', '.join(bad)}]")) == [
        loralist.Heard("A>B:x", "2026-11-15 12:00:01", Reading(snr=6.25, rssi=-97.0))
    ]
    for body in ("[" * 70000, "{}", '"x"', "nothing"):
        with pytest.raises(loralist.ListError):
            loralist.parse(answer(body))
    assert console_line(
        b"<--- LoRa Packet Rx (RSSI:-1" + b"0" * 400 + b" | SNR:3.25 | FreqErr:1) : OH2ABC>APRS:>x"
    ) == (b"OH2ABC>APRS:>x", None), "digits past a float's range are no reading"


async def _answering(host: str, body: bytes, asked: list[bytes]) -> "asyncio.Server":
    """A web server on `host` that answers every request with 200 and `body`, the request's lines
    kept in `asked`."""

    async def answer(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        asked.extend((await reader.readuntil(b"\r\n\r\n")).split(b"\r\n"))
        writer.write(b"HTTP/1.0 200 OK\r\n\r\n" + body)
        await writer.drain()
        writer.close()

    return await asyncio.start_server(answer, host, 0)


async def test_an_answer_longer_than_the_list_is_said_so_and_not_as_a_failed_connection() -> None:
    server = await _answering("127.0.0.1", b"[" + b" " * (3 * loralist.MAX_BODY) + b"]", [])
    try:
        with pytest.raises(loralist.ListError, match="^the answer is longer than a list of heard packets$"):
            await loralist._fetch("127.0.0.1", server.sockets[0].getsockname()[1])
    finally:
        server.close()
        await server.wait_closed()


async def test_a_board_reached_by_an_ipv6_address_is_asked_with_the_address_in_brackets() -> None:
    asked: list[bytes] = []
    try:
        server = await _answering("::1", b"[]", asked)
    except OSError:
        pytest.skip("this machine has no IPv6 loopback")
    try:
        assert await loralist._fetch("::1", server.sockets[0].getsockname()[1]) == []
        assert b"Host: [::1]" in asked, asked
    finally:
        server.close()
        await server.wait_closed()


def test_esp32_loraprs_report_and_the_igates_log_line_and_the_internets_words_in_a_path() -> None:
    assert signal_report(b"\xff\x8a\xfd\x2b") == Reading(snr=-7.25, rssi=-118.0) and signal_report(b"\x01") is None
    assert console_line(b"<--- LoRa Packet Rx (RSSI:-104 | SNR:-3.25 | FreqErr:812.50) : OH2ABC>APRS:>x") == (
        b"OH2ABC>APRS:>x",
        Reading(snr=-3.25, rssi=-104.0),
    )
    assert console_line(b"<--- LoRa Packet Rx : OH2ABC>APRS:>eco") == (b"OH2ABC>APRS:>eco", None), (
        "the eco mode writes no signal"
    )
    assert console_line(b"---> Sent to TNC       : OH2ABC>APRS:>x") is None
    assert (
        from_internet(frame_of(b"A>B,TCPIP*,qAC,T2X:x"))
        and from_internet(frame_of(b"A>B,qAR,OH2LRG-10:x"))
        and not from_internet(frame_of(b"A>B,WIDE1-1:x"))
    )
    assert list_key(b"A>B:x\x01\x7fy") == "A>B:x..y"


# ---- on the line


@stops
async def test_the_igates_list_says_each_packets_signal_even_for_a_repeated_text_and_a_control_byte(
    lines: Lines, monkeypatch: pytest.MonkeyPatch
) -> None:
    board = Board("igate")
    server = await listed(monkeypatch, board)
    try:
        line, _ = await line_on(lines, board, LORA_TCP)
        board.air(HEARD, rssi=-97, snr=6.25)
        await until(lambda: len(line.packets) == 1)
        assert (line.packets[0].snr, line.packets[0].rssi) == (6.25, -97.0)
        # (a digipeater's copy of the same text, a moment later)
        board.air(HEARD, rssi=-120, snr=-11.5)
        board.air(HEARD, rssi=-80, snr=9.0)
        board.air(b"OH2ABC-7>APLRT1:>a control byte\x01 in it", rssi=-101, snr=2.0)
        await until(lambda: len(line.packets) == 4)
        assert [(p.snr, p.rssi) for p in line.packets] == [
            (6.25, -97.0),
            (-11.5, -120.0),
            (9.0, -80.0),
            (2.0, -101.0),
        ], "each frame its own entry, in the order heard"
        assert set(server.requests) == {"/received-packets.json"} and len(server.requests) <= 5, (
            "one at the open, then at most one at a time, and nothing else of the board is asked"
        )
    finally:
        await server.stop()


@stops
async def test_a_frame_whose_lists_answer_already_holds_the_next_copy_of_its_text_takes_its_own_entry(
    lines: Lines, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The list's answer slower than the next packet on the air: the board has heard the
    digipeater's copy and the next packet, and not yet handed them on, when the first copy's answer
    comes."""
    asked, answer = list[str](), asyncio.Event()
    fetch = loralist.fetch

    async def slow(host: str) -> list[loralist.Heard]:
        asked.append(host)
        await answer.wait()
        return await fetch(host)

    board = Board("igate")
    server = await listed(monkeypatch, board)
    try:
        line, _ = await line_on(lines, board, LORA_TCP)
        answer.set()
        monkeypatch.setattr(loralist, "fetch", slow)
        board.air(HEARD, rssi=-97, snr=6.25)
        await until(lambda: len(line.packets) == 1)
        answer.clear()
        board.air(HEARD, rssi=-120, snr=-11.5)
        await until(lambda: len(asked) == 2)
        send, later = board.out, list[bytes]()
        # (in the list at once, on the KISS line only after the answer)
        board.out = later.append
        board.air(HEARD, rssi=-80, snr=9.0)
        board.air(b"OH2ABC-7>APLRT1:>after it", rssi=-101, snr=2.0)
        answer.set()
        await until(lambda: len(line.packets) == 2)
        for data in later:
            send(data)
        await until(lambda: len(line.packets) == 4)
        assert [(p.snr, p.rssi) for p in line.packets] == [
            (6.25, -97.0),
            (-11.5, -120.0),
            (9.0, -80.0),
            (2.0, -101.0),
        ], "the copy the board has not handed on yet keeps its entry"
    finally:
        await server.stop()


class Gate:
    """The list's answers, held where a test says: before the board is asked (`before`, the answer
    is the list when the gate opens) or after it answered (the list as it was when asked). `asked`,
    `made` and `taken` count the requests, the answers the board made and the answers the daemon
    took."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.open, self.before = asyncio.Event(), True
        self.open.set()
        self.asked = self.made = self.taken = 0
        fetch = loralist.fetch

        async def gated(host: str) -> list[loralist.Heard]:
            self.asked += 1
            before = self.before
            if before:
                await self.open.wait()
            entries = await fetch(host)
            self.made += 1
            if not before:
                await self.open.wait()
            self.taken += 1
            return entries

        monkeypatch.setattr(loralist, "fetch", gated)


def board_of(line: Any) -> Any:
    """The board's reader of the line's open (loraboard.LoraBoard)."""
    return line.tnc._reader.board


def held(line: Any) -> int:
    """How many frames the board's reader has held on this open."""
    return int(board_of(line)._serial)


@stops
async def test_a_frame_whose_entry_never_comes_takes_no_entry_of_the_next_copy_of_its_text(
    lines: Lines, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(loraboard, "LIST_WAIT_SEC", 30.0)
    board = Board("igate")
    server = await listed(monkeypatch, board)
    try:
        line, _ = await line_on(lines, board, LORA_TCP)
        board.air(HEARD, rssi=-97, snr=6.25)
        await until(lambda: len(line.packets) == 1)
        # (handed on, and not in the list: it fell out of it, or the list lost it)
        board.out(encode_kiss(HEARD))
        # (at its answer, not at the end of its wait)
        await until(lambda: len(line.packets) == 2)
        board.air(HEARD, rssi=-120, snr=-11.5)
        await until(lambda: len(line.packets) == 3)
        assert [(p.snr, p.rssi) for p in line.packets] == [(6.25, -97.0), (None, None), (-11.5, -120.0)], (
            "the frame without an entry goes on without figures, the next copy with its own"
        )
    finally:
        await server.stop()


@stops
async def test_two_copies_that_come_while_the_list_is_asked_and_the_first_has_no_entry_go_on_without(
    lines: Lines, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = Gate(monkeypatch)
    board = Board("igate")
    server = await listed(monkeypatch, board)
    try:
        line, _ = await line_on(lines, board, LORA_TCP)
        board.air(HEARD, rssi=-97, snr=6.25)
        await until(lambda: len(line.packets) == 1)
        gate.open.clear()
        asked = gate.asked
        board.air(b"OH2ABC-7>APLRT1:>other", rssi=-80, snr=9.0)
        await until(lambda: gate.asked == asked + 1)
        board.out(encode_kiss(HEARD))  # (no entry)
        # (its entry in the answer that is on its way)
        board.air(HEARD, rssi=-120, snr=-11.5)
        await until(lambda: held(line) == 4)
        gate.open.set()
        await until(lambda: len(line.packets) == 4)
        assert [(p.snr, p.rssi) for p in line.packets] == [(6.25, -97.0), (9.0, -80.0), (None, None), (None, None)], (
            "which of the two copies has no entry cannot be told: neither takes one"
        )
    finally:
        await server.stop()


@stops
async def test_without_the_opens_answer_an_answer_asked_before_the_next_copy_came_gives_neither_copy_an_entry_of_it(
    lines: Lines, monkeypatch: pytest.MonkeyPatch
) -> None:
    made, steps, fetch = [0], asyncio.Semaphore(0), loralist.fetch

    async def stepped(host: str) -> list[loralist.Heard]:
        entries = await fetch(host)
        made[0] += 1
        await steps.acquire()
        return entries

    monkeypatch.setattr(loralist, "fetch", stepped)
    board = Board("igate")
    board.air(HEARD, rssi=-90, snr=3.0)
    server = await listed(monkeypatch, board)
    try:
        line, _ = await line_on(lines, board, LORA_TCP)
        await until(lambda: made[0] == 1)
        # (while the open's answer is on its way: no start)
        board.air(HEARD, rssi=-97, snr=6.25)
        await until(lambda: held(line) == 1)
        steps.release()
        await until(lambda: made[0] == 2)  # (the first copy's answer, made)
        board.air(HEARD, rssi=-120, snr=-11.5)
        await until(lambda: held(line) == 2)
        for _ in range(5):
            steps.release()
        await until(lambda: len(line.packets) == 2)
        assert [(p.snr, p.rssi) for p in line.packets] == [(6.25, -97.0), (-11.5, -120.0)]
    finally:
        await server.stop()


@stops
async def test_frames_whose_entries_fell_out_of_the_list_take_none_of_the_later_copies_entries(
    lines: Lines, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The list keeps the last 10 packets: eleven copies of one text heard before the KISS line
    hands the first on push out the entry given last and the first copy's own."""
    board = Board("igate")
    server = await listed(monkeypatch, board)
    try:
        line, _ = await line_on(lines, board, LORA_TCP)
        board.air(HEARD, rssi=-97, snr=6.25)
        await until(lambda: len(line.packets) == 1)
        send, later = board.out, list[bytes]()
        board.out = later.append
        for n in range(11):
            board.air(HEARD, rssi=-100 - n, snr=n)
        board.out = send
        for data in later:
            send(data)
        await until(lambda: len(line.packets) == 12)
        figures = [(p.snr, p.rssi) for p in line.packets[1:]]
        assert not [(n, f) for n, f in enumerate(figures) if f not in ((None, None), (float(n), -100.0 - n))], (
            "a frame with no figures, or its own; never another copy's"
        )
        board.air(b"OH2ABC-7>APLRT1:>after it", rssi=-80, snr=9.0)
        await until(lambda: len(line.packets) == 13)
        assert (line.packets[12].snr, line.packets[12].rssi) == (9.0, -80.0), "the list starts afresh"
    finally:
        await server.stop()


@stops
async def test_the_first_answer_of_an_open_that_already_holds_the_next_copy_gives_each_frame_its_own(
    lines: Lines, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The board is asked at the open what it heard before: an older copy of the text in the list is
    no frame's, and the copy the board has not handed on yet is left for its frame."""
    monkeypatch.setattr(loraboard, "OPENING_SEC", 0.05)
    gate = Gate(monkeypatch)
    board = Board("igate")
    # (heard before the daemon connected: in the list, handed to no one)
    board.air(HEARD, rssi=-90, snr=3.0)
    server = await listed(monkeypatch, board)
    try:
        line, _ = await line_on(lines, board, LORA_TCP)
        await until(lambda: gate.taken == 1)
        # (no frame right after the open's answer: it is what the board heard before)
        await asyncio.sleep(2 * loraboard.OPENING_SEC)
        gate.open.clear()
        board.air(HEARD, rssi=-97, snr=6.25)
        await until(lambda: gate.asked == 2)
        send, later = board.out, list[bytes]()
        board.out = later.append
        # (in the list before the first copy's answer is made, on the KISS line only after it)
        board.air(HEARD, rssi=-120, snr=-11.5)
        gate.open.set()
        await until(lambda: len(line.packets) == 1)
        for data in later:
            send(data)
        await until(lambda: len(line.packets) == 2)
        assert [(p.snr, p.rssi) for p in line.packets] == [(6.25, -97.0), (-11.5, -120.0)]
    finally:
        await server.stop()


@stops
async def test_a_copy_that_comes_after_the_answer_was_made_waits_for_the_next_and_the_older_copy_is_no_ones(
    lines: Lines, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(loraboard, "OPENING_SEC", 0.05)
    gate = Gate(monkeypatch)
    board = Board("igate")
    board.air(HEARD, rssi=-90, snr=3.0)
    server = await listed(monkeypatch, board)
    try:
        line, _ = await line_on(lines, board, LORA_TCP)
        await until(lambda: gate.taken == 1)
        # (no frame right after the open's answer: it is what the board heard before)
        await asyncio.sleep(2 * loraboard.OPENING_SEC)
        gate.before = False
        gate.open.clear()
        board.air(HEARD, rssi=-97, snr=6.25)
        # (the answer for the first copy is made, and on its way)
        await until(lambda: gate.made == 2)
        gate.before = True
        board.air(HEARD, rssi=-120, snr=-11.5)
        await until(lambda: held(line) == 2)
        gate.open.set()
        await until(lambda: len(line.packets) == 2)
        assert [(p.snr, p.rssi) for p in line.packets] == [(6.25, -97.0), (-11.5, -120.0)]
    finally:
        await server.stop()


@stops
async def test_an_answer_asked_before_a_frame_came_gives_it_nothing(
    lines: Lines, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The answer at the open, made before the first frame came, holds only an older copy of its
    text: the frame waits for the next answer."""
    gate = Gate(monkeypatch)
    gate.before = False
    gate.open.clear()
    board = Board("igate")
    board.air(HEARD, rssi=-90, snr=3.0)
    server = await listed(monkeypatch, board)
    try:
        line, _ = await line_on(lines, board, LORA_TCP)
        await until(lambda: gate.made == 1)
        board.air(HEARD, rssi=-97, snr=6.25)
        await until(lambda: held(line) == 1)
        gate.open.set()
        await until(lambda: len(line.packets) == 1)
        assert [(p.snr, p.rssi) for p in line.packets] == [(6.25, -97.0)]
    finally:
        await server.stop()


@stops
async def test_a_frame_that_comes_right_after_the_answer_at_the_open_takes_its_entry_from_that_answer(
    lines: Lines, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The board listed the packet just before it answered, and its bytes come after the answer: the
    answer at the open is not taken as what the board heard before."""
    gate = Gate(monkeypatch)
    gate.open.clear()
    board = Board("igate")
    server = await listed(monkeypatch, board)
    try:
        line, _ = await line_on(lines, board, LORA_TCP)
        await until(lambda: gate.asked == 1)
        send, later = board.out, list[bytes]()
        board.out = later.append
        board.air(HEARD, rssi=-97, snr=6.25)
        gate.open.set()
        await until(lambda: gate.taken == 1)
        board.out = send
        for data in later:
            send(data)
        await until(lambda: len(line.packets) == 1)
        assert [(p.snr, p.rssi) for p in line.packets] == [(6.25, -97.0)]
    finally:
        await server.stop()


@stops
async def test_the_board_keeps_no_timer_of_a_frame_that_has_gone_on(
    lines: Lines, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(loraboard, "LIST_WAIT_SEC", 30.0)
    board = Board("igate")
    server = await listed(monkeypatch, board)
    try:
        line, _ = await line_on(lines, board, LORA_TCP)
        for n in range(12):
            board.air(HEARD.replace(b"tracker", b"n%d" % n), rssi=-100 - n, snr=n)
            await until(lambda count=n + 1: len(line.packets) == count)
        assert [p.rssi for p in line.packets] == [-100.0 - n for n in range(12)]
        assert len(board_of(line)._timers) == 0, "a timer for each frame for the life of the open"
    finally:
        await server.stop()


@pytest.mark.parametrize("answer", ["404", "401", "junk", "hang"])
@stops
async def test_the_first_failure_of_the_list_ends_the_asking_for_the_open_with_one_line_and_the_frames_go_on_without(
    lines: Lines, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, answer: str
) -> None:
    caplog.set_level(logging.INFO, logger="neoaprs")
    monkeypatch.setattr(loralist, "ANSWER_SEC", 0.3)
    monkeypatch.setattr(loraboard, "LIST_WAIT_SEC", 0.5)
    board = Board("igate")
    server = await listed(monkeypatch, board, answer)
    try:
        line, _ = await line_on(lines, board, LORA_TCP)
        board.air(HEARD)
        await until(lambda: len(line.packets) == 1)
        assert line.packets[0].snr is None and line.packets[0].rssi is None
        board.air(HEARD.replace(b"tracker", b"next"))
        await until(lambda: len(line.packets) == 2)
        assert len(server.requests) == 1, "no more asking on this open"
        assert (
            caplog.text.count("the board's list of heard packets did not answer") == 1
            and "packets come without their signal" in caplog.text
        )
        assert not warnings_in(caplog), "the operator can do nothing about it on the page: a line of the log"
    finally:
        await server.stop()


def refused_after(monkeypatch: pytest.MonkeyPatch, delay_sec: float) -> None:
    """The board's list port refuses the connection `delay_sec` after it is asked, on every system:
    a refusal of a closed loopback port is at once on Linux and after about 2 s of the stack's
    retries on Windows, so the real one cannot say which of the two ends a frame's wait. Every other
    connection is the real one."""
    real = asyncio.open_connection

    async def connect(host: str | None = None, port: int | None = None, **kwargs: Any) -> Any:
        if port != loralist.PORT:
            return await real(host, port, **kwargs)
        await asyncio.sleep(delay_sec)
        raise ConnectionRefusedError(10061, "the board refused the connection")

    monkeypatch.setattr(asyncio, "open_connection", connect)


@pytest.mark.parametrize(
    ("refused_sec", "wait_sec"), [(0.2, 30.0), (30.0, 0.3)], ids=["the refusal first", "the wait first"]
)
@stops
async def test_a_board_whose_list_refuses_holds_its_first_frame_no_longer_than_the_refusal_or_the_wait(
    lines: Lines, monkeypatch: pytest.MonkeyPatch, refused_sec: float, wait_sec: float
) -> None:
    """A refusal releases the frame that waits at once, not at the end of its wait; a slow refusal
    (Windows retries, a board that is not there) holds no frame longer than the wait.
    """
    monkeypatch.setattr(loraboard, "LIST_WAIT_SEC", wait_sec)
    # (neither the refusal nor the wait is cut short by the answer's limit)
    monkeypatch.setattr(loralist, "ANSWER_SEC", 60.0)
    refused_after(monkeypatch, refused_sec)
    board = Board("igate")
    line, _ = await line_on(lines, board, LORA_TCP)
    board.air(HEARD)
    await until(lambda: len(line.packets) == 1)
    board.air(HEARD)
    await until(lambda: len(line.packets) == 2)
    assert [(p.snr, p.rssi) for p in line.packets] == [(None, None), (None, None)]


@stops
async def test_dl9sau_tracker_says_the_signal_in_its_path_which_is_taken_off_before_the_packet_is_kept(
    lines: Lines, monkeypatch: pytest.MonkeyPatch
) -> None:
    board = Board("dl9sau")
    server = await listed(monkeypatch, board)
    line, _ = await line_on(lines, board, LORA_SERIAL)
    board.air(HEARD, rssi=-112, snr=-7)
    await until(lambda: len(line.packets) == 1)
    await server.stop()
    assert server.requests == [], "a board on a serial line (here a socket:// one) has no list to ask"
    packet = line.packets[0]
    assert (packet.snr, packet.rssi, packet.path) == (-7.0, -112.0, ("WIDE1-1",)) and text_of(
        ax25.decode(packet.raw)
    ) == HEARD, "no Q element left: no digipeater, nothing for APRS-IS"
    assert q_element(-7, -112) == b"QA7L2"
    eight = b"OH2ABC-7>APLRT1,OH2A,OH2B,OH2C,OH2D,OH2E,OH2F,OH2G,WIDE2-2:>eight digipeaters"
    board.air(eight, rssi=-98, snr=5)
    await until(lambda: len(line.packets) == 2)
    packet = line.packets[1]
    assert (
        (packet.snr, packet.rssi, len(packet.path)) == (5.0, -98.0, 8)
        and text_of(ax25.decode(packet.raw)) == eight
        and line.tnc.stats.rejected == 0
    ), "the element appended after eight digipeaters, one address more than AX.25 holds, is taken off and read"


@stops
async def test_esp32_loraprs_signal_reports_go_with_their_frames_from_the_second_on_and_no_frame_is_handed_on_before_an_earlier_one(
    lines: Lines,
) -> None:
    board = Board("esp32")
    line, _ = await line_on(lines, board, LORA_SERIAL)
    board.air(HEARD, rssi=-118, snr=-7.25)
    await until(lambda: len(line.packets) == 1)
    assert line.packets[0].snr is None, "the first frame of an open went on before the board's first report"
    for n in range(3):
        board.air(HEARD.replace(b"tracker", b"n%d" % n), rssi=-100 - n, snr=n)
    await until(lambda: len(line.packets) == 4)
    assert [(p.snr, p.rssi, p.info[-2:]) for p in line.packets[1:]] == [
        (0.0, -100.0, b"n0"),
        (1.0, -101.0, b"n1"),
        (2.0, -102.0, b"n2"),
    ]
    assert line.tnc.stats.rejected == 0


@stops
async def test_the_igates_log_on_usb_says_each_packet_with_its_signal(lines: Lines) -> None:
    board = Board("console")
    line, _ = await line_on(lines, board, LORA_CONSOLE)
    board.log("<--- LoRa Packet Rx : " + HEARD.decode())
    board.air(HEARD, rssi=-104, snr=-3.25)
    board.log("---> Sent to TNC       : OH2ABC")
    await until(lambda: len(line.packets) == 2)
    assert [(p.snr, p.rssi) for p in line.packets] == [(None, None), (-3.25, -104.0)]
    assert any("Sent to TNC" in text for text in line.tnc.lines)
