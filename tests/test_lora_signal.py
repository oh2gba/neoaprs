"""The signal of what a LoRa APRS board hears, where its firmware says it (neoaprs/lorasignal.py, neoaprs/loralist.py, reading.Following; aprs-reference/lora-plan.md step L4), each board the fake of
tests/support/fakelora.py: the CA2RXU iGate's list of heard packets asked after each frame, a frame matched to its entry by its text (a repeated text, a control byte), and the asking given up for the open at
the first failure (refused, 404, 401, not the list, no answer in time) with one line of the log, the frames going on without their signal; DL9SAU's element taken off the path and read; esp32_loraprs's KISS
command 7, from its second report on; the iGate's log on USB with each packet's signal; and the board's frames never handed on out of their order."""
import logging
import socket
from collections.abc import Iterator

import pytest

from neoaprs import ax25, loraboard, loralist
from neoaprs.lorasignal import console_line, from_internet, list_key, ninth_element, path_reading, signal_report
from neoaprs.reading import Reading
from neoaprs.tnc2line import frame_of, text_of
from neoaprs.tncprofile import LORA_CONSOLE, LORA_SERIAL, LORA_TCP
from tests.support.env import until
from tests.support.fakelora import Board, ListServer, decapsulate, encode_kiss, q_element
from tests.test_lora_line import Lines, line_on, stops

HEARD = b"OH2ABC-7>APLRT1,WIDE1-1:!6010.00N/02456.00E>tracker"


@pytest.fixture
def lines() -> Lines:
    return Lines()


@pytest.fixture(autouse=True)
def refused_list(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The list is asked of a port that refuses unless a test gives it a server: port 80 of the machine is never asked."""
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
    assert path_reading(frame_of(b"OH2ABC>APRS,QAC,Q2373-1,QZ7L2:>x")) == (frame_of(b"OH2ABC>APRS,QAC,Q2373-1,QZ7L2:>x"), None), "a q-construct, an SSID and a letter past J are no element"


def test_the_element_after_eight_digipeaters_is_found_only_where_it_makes_one_address_too_many() -> None:
    def board_bytes(text: bytes) -> bytes:
        return decapsulate(encode_kiss(text))                         # (the AX.25 bytes as the board writes them)
    eight, element = board_bytes(b"A>B,C1,C2,C3,C4,C5,C6,C7,C8:>x"), board_bytes(b"A>B,C1,C2,C3,C4,C5,C6,C7,C8,QA7L2:>x")
    with pytest.raises(ax25.Ax25Error, match="more than 8 digipeaters"):
        ax25.decode(element)
    assert ninth_element(element) == (eight, Reading(snr=-7.0, rssi=-112.0)) and text_of(ax25.decode(eight)) == b"A>B,C1,C2,C3,C4,C5,C6,C7,C8:>x"
    assert ninth_element(eight) is None and ninth_element(board_bytes(b"A>B,C1,C2,C3,C4,C5,C6,C7,C8,WIDE2:>x")) is None, "an address that is no element is left: the frame is refused as before"
    assert ninth_element(board_bytes(b"A>B,C1,C2,C3,C4,C5,C6,C7,QA7L2:>x")) is None, "within AX.25's eight, path_reading takes it"


def test_the_lists_entries_that_are_none_are_passed_over_and_an_answer_that_is_no_list_is_refused() -> None:
    def answer(body: str) -> bytes:
        return b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n" + body.encode()
    good = '{"rxDate": "2026-11-15", "rxTime": "12:00:01", "packet": "A>B:x", "RSSI": -97, "SNR": 6.25}'
    bad = ['{"packet": "A>B:y", "RSSI": NaN, "SNR": 1}', '{"packet": "A>B:y", "RSSI": -90, "SNR": 1e999}', '{"packet": "A>B:y", "RSSI": 1' + "0" * 400 + ', "SNR": 1}',
           '{"packet": 7, "RSSI": -90, "SNR": 1}', '{"RSSI": -90, "SNR": 1}', '"text"', '{"packet": "A>B:y", "RSSI": "loud", "SNR": 1}']
    assert loralist.parse(answer(f"[{good}, {', '.join(bad)}]")) == [loralist.Heard("A>B:x", "2026-11-15 12:00:01", Reading(snr=6.25, rssi=-97.0))]
    for body in ("[" * 70000, "{}", '"x"', "nothing"):
        with pytest.raises(loralist.ListError):
            loralist.parse(answer(body))
    assert console_line(b"<--- LoRa Packet Rx (RSSI:-1" + b"0" * 400 + b" | SNR:3.25 | FreqErr:1) : OH2ABC>APRS:>x") == (b"OH2ABC>APRS:>x", None), "digits past a float's range are no reading"


def test_esp32_loraprs_report_and_the_igates_log_line_and_the_internets_words_in_a_path() -> None:
    assert signal_report(b"\xff\x8a\xfd\x2b") == Reading(snr=-7.25, rssi=-118.0) and signal_report(b"\x01") is None
    assert console_line(b"<--- LoRa Packet Rx (RSSI:-104 | SNR:-3.25 | FreqErr:812.50) : OH2ABC>APRS:>x") == (b"OH2ABC>APRS:>x", Reading(snr=-3.25, rssi=-104.0))
    assert console_line(b"<--- LoRa Packet Rx : OH2ABC>APRS:>eco") == (b"OH2ABC>APRS:>eco", None), "the eco mode writes no signal"
    assert console_line(b"---> Sent to TNC       : OH2ABC>APRS:>x") is None
    assert from_internet(frame_of(b"A>B,TCPIP*,qAC,T2X:x")) and from_internet(frame_of(b"A>B,qAR,OH2LRG-10:x")) and not from_internet(frame_of(b"A>B,WIDE1-1:x"))
    assert list_key(b"A>B:x\x01\x7fy") == "A>B:x..y"


# ---- on the line

@stops
async def test_the_igates_list_says_each_packets_signal_even_for_a_repeated_text_and_a_control_byte(lines: Lines, monkeypatch: pytest.MonkeyPatch) -> None:
    board = Board("igate")
    server = await listed(monkeypatch, board)
    try:
        line, _ = await line_on(lines, board, LORA_TCP)
        board.air(HEARD, rssi=-97, snr=6.25)
        await until(lambda: len(line.packets) == 1)
        assert (line.packets[0].snr, line.packets[0].rssi) == (6.25, -97.0)
        board.air(HEARD, rssi=-120, snr=-11.5)                              # (a digipeater's copy of the same text, a moment later)
        board.air(HEARD, rssi=-80, snr=9.0)
        board.air(b"OH2ABC-7>APLRT1:>a control byte\x01 in it", rssi=-101, snr=2.0)
        await until(lambda: len(line.packets) == 4)
        assert [(p.snr, p.rssi) for p in line.packets] == [(6.25, -97.0), (-11.5, -120.0), (9.0, -80.0), (2.0, -101.0)], "each frame its own entry, in the order heard"
        assert set(server.requests) == {"/received-packets.json"} and len(server.requests) <= 4, "at most one request at a time, and nothing else of the board is asked"
    finally:
        await server.stop()


@pytest.mark.parametrize("answer", ["404", "401", "junk", "hang"])
@stops
async def test_the_first_failure_of_the_list_ends_the_asking_for_the_open_with_one_line_and_the_frames_go_on_without(lines: Lines, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
                                                                                                                   answer: str) -> None:
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
        assert caplog.text.count("the board's list of heard packets did not answer") == 1 and "packets come without their signal" in caplog.text
        assert not any(r.levelno >= logging.WARNING for r in caplog.records), "the operator can do nothing about it on the page: a line of the log"
    finally:
        await server.stop()


@stops
async def test_a_board_whose_list_refuses_holds_its_first_frame_no_longer_than_the_refusal(lines: Lines) -> None:
    board = Board("igate")
    line, _ = await line_on(lines, board, LORA_TCP)
    board.air(HEARD)
    await until(lambda: len(line.packets) == 1, 1.0)
    board.air(HEARD)
    await until(lambda: len(line.packets) == 2, 0.5)


@stops
async def test_dl9sau_tracker_says_the_signal_in_its_path_which_is_taken_off_before_the_packet_is_kept(lines: Lines, monkeypatch: pytest.MonkeyPatch) -> None:
    board = Board("dl9sau")
    server = await listed(monkeypatch, board)
    line, _ = await line_on(lines, board, LORA_SERIAL)
    board.air(HEARD, rssi=-112, snr=-7)
    await until(lambda: len(line.packets) == 1)
    await server.stop()
    assert server.requests == [], "a board on a serial line (here a socket:// one) has no list to ask"
    packet = line.packets[0]
    assert (packet.snr, packet.rssi, packet.path) == (-7.0, -112.0, ("WIDE1-1",)) and text_of(ax25.decode(packet.raw)) == HEARD, "no Q element left: no digipeater, nothing for APRS-IS"
    assert q_element(-7, -112) == b"QA7L2"
    eight = b"OH2ABC-7>APLRT1,OH2A,OH2B,OH2C,OH2D,OH2E,OH2F,OH2G,WIDE2-2:>eight digipeaters"
    board.air(eight, rssi=-98, snr=5)
    await until(lambda: len(line.packets) == 2)
    packet = line.packets[1]
    assert (packet.snr, packet.rssi, len(packet.path)) == (5.0, -98.0, 8) and text_of(ax25.decode(packet.raw)) == eight and line.tnc.stats.rejected == 0, \
        "the element appended after eight digipeaters, one address more than AX.25 holds, is taken off and read"


@stops
async def test_esp32_loraprs_signal_reports_go_with_their_frames_from_the_second_on_and_no_frame_is_handed_on_before_an_earlier_one(lines: Lines) -> None:
    board = Board("esp32")
    line, _ = await line_on(lines, board, LORA_SERIAL)
    board.air(HEARD, rssi=-118, snr=-7.25)
    await until(lambda: len(line.packets) == 1)
    assert line.packets[0].snr is None, "the first frame of an open went on before the board's first report"
    for n in range(3):
        board.air(HEARD.replace(b"tracker", b"n%d" % n), rssi=-100 - n, snr=n)
    await until(lambda: len(line.packets) == 4)
    assert [(p.snr, p.rssi, p.info[-2:]) for p in line.packets[1:]] == [(0.0, -100.0, b"n0"), (1.0, -101.0, b"n1"), (2.0, -102.0, b"n2")]
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
