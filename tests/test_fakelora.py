"""Tests for the fake LoRa board (tests/support/fakelora.py) against the firmwares' own bytes
(aprs-reference/lora-plan.md): KISS encoding and decoding in both directions, callsign cutting,
input limits, dropped own frames and keying with Tx off.
"""

import struct

from neoaprs import ax25, kiss
from neoaprs.lorasignal import element_reading
from neoaprs.tnc2line import frame_of, text_of
from tests.support.fakelora import HEADER, Board, decode_kiss, encode_kiss, q_element, sanitize

# OH2GBA-7>APLRT1,WIDE1-1:!6010.00N/02456.00E> as the iGate writes it to a KISS client, byte for
# byte (lora-plan.md step L1): the destination APLRT1 first (each letter shifted left, SSID byte
# 0x60), the source OH2GBA-7 (0x6E), WIDE1-1 as the last address (0x62 | 1), control 0x03, PID 0xF0,
# the text.
TEXT = b"OH2GBA-7>APLRT1,WIDE1-1:!6010.00N/02456.00E>"
VECTOR = (
    bytes.fromhex("c0 00 82 a0 98 a4 a8 62 60 9e 90 64 8e 84 82 6e ae 92 88 8a 62 40 63 03 f0")
    + b"!6010.00N/02456.00E>"
    + b"\xc0"
)


def test_the_igates_kiss_of_a_packet_is_the_vector_worked_from_its_code_and_our_decoder_reads_it_back_to_the_same_text() -> (
    None
):
    assert encode_kiss(TEXT) == VECTOR
    frame = ax25.decode(kiss.KissDecoder().feed(VECTOR)[0].payload)
    assert text_of(frame) == TEXT and frame == frame_of(TEXT)


def test_what_we_encode_the_boards_decoder_reads_to_the_same_text() -> None:
    for text in (
        TEXT,
        b"Q9TRK-7>APLRT1,Q9LRG-10*,WIDE2-1:=/0)dITh.'>9O[tracker",
        b"OH2GBA>APZNEO,WIDE1-1::Q9KOT    :Hello{12",
        "Q9BKE-12>APLRT1:>Pyöräilemässä".encode(),
    ):
        assert decode_kiss(kiss.encode(ax25.encode(frame_of(text)))) == (True, text), text


def test_the_igate_cuts_a_call_of_more_than_six_characters_without_a_word() -> None:
    frame = ax25.decode(kiss.KissDecoder().feed(encode_kiss(b"OH2ABCDE-5>APLRG1:>long call"))[0].payload)
    assert str(frame.source) == "OH2ABC-5"


def test_the_igate_keys_what_a_client_writes_with_lora_tx_on_and_drops_its_own_call_and_a_buffer_past_255_bytes() -> (
    None
):
    board = Board("igate")
    board.hear(kiss.encode(ax25.encode(frame_of(b"OH2GBA>APZNEO,WIDE1-1:>hi"))))
    board.hear(kiss.encode(ax25.encode(frame_of(b"OH2LRG-10>APZNEO:>own"))))
    board.hear(kiss.encode(b"\x00", command=5))
    assert board.transmitted == [HEADER + b"OH2GBA>APZNEO,WIDE1-1:>hi"], (
        "its own call is dropped (acceptOwn off), a command frame is no frame"
    )
    board.hear(kiss.encode(ax25.encode(frame_of(b"OH2GBA>APZNEO:>" + b"x" * 250))))
    assert len(board.transmitted) == 1, "a KISS frame past 255 bytes clears the input"
    off = Board("igate", tx_active=False)
    off.hear(kiss.encode(ax25.encode(frame_of(b"OH2GBA>APZNEO:>hi"))))
    assert off.transmitted == [], "with LoRa Tx off the board keys nothing, and says nothing"


def test_the_igates_input_takes_255_bytes_before_the_closing_fend_escapes_counted() -> None:
    def frame(escapes: int) -> bytes:
        # (each Arabic letter's lead byte is 0xDB, which KISS escapes)
        raw = ax25.encode(frame_of(b"OH2GBA>APZNEO:>" + "\u06db".encode() * escapes))
        return ax25.encode(frame_of(b"OH2GBA>APZNEO:>" + "\u06db".encode() * escapes + b"x" * (250 - len(raw))))

    for escapes, keyed in ((3, True), (4, False)):
        board = Board("igate")
        board.hear(kiss.encode(frame(escapes)))
        assert (
            len(frame(escapes)) == 250
            and len(kiss.encode(frame(escapes))) == 253 + escapes
            and bool(board.transmitted) == keyed
        ), escapes


def test_the_tracker_over_ble_keys_every_write_on_its_tnc2_service_and_cuts_kiss_at_fend_in_a_buffer_of_1024() -> None:
    uart = Board("tracker-ble", kiss=False)
    uart.hear(kiss.encode(b"\x00", command=5))
    uart.hear(b"not a packet")
    assert uart.transmitted == [HEADER + b"\xc0\x05", HEADER + b"not a packet"], (
        "onWrite keys any write as it is, cut at its NUL"
    )
    board = Board("tracker-ble")
    one, two = (kiss.encode(ax25.encode(frame_of(b"OH2GBA>APZNEO:>%d" % n))) for n in (1, 2))
    board.hear(b"junk" + one[:9])
    board.hear(one[9:] + two)
    assert board.transmitted == [HEADER + b"OH2GBA>APZNEO:>2"], (
        "bytes before a FEND are thrown away, a frame split over two writes is joined, and of two in a write the latter is keyed"
    )
    board.hear(kiss.encode(b"\x00", command=5))
    board.hear(bytes([0xC0]) + b"x" * 1024)
    board.hear(one)
    assert board.transmitted == [HEADER + b"OH2GBA>APZNEO:>2", HEADER + b"OH2GBA>APZNEO:>1"], (
        "a command frame alone is not keyed; past 1024 bytes the buffer is cleared"
    )


def test_the_igates_list_writes_control_bytes_as_dots_and_keeps_the_last_ten() -> None:
    board = Board("igate")
    for n in range(12):
        board.air(b"OH2ABC>APRS:>n%d\x01" % n, rssi=-100 - n, snr=n / 4)
    assert len(board.received) == 10 and board.received[-1] == {
        "rxDate": "2026-11-15",
        "rxTime": "12:00:12",
        "packet": "OH2ABC>APRS:>n11.",
        "RSSI": -111,
        "SNR": 2.75,
    }
    assert sanitize(b"a\x7fb\x1fc") == "a.b.c"


def test_dl9sau_element_reads_back_over_its_whole_range() -> None:
    for snr in range(-99, 100):
        for rssi in range(-259, 0):
            element = q_element(snr, rssi)
            assert (
                element_reading(element.decode(), 0) is not None
                and element_reading(element.decode(), 0).snr == snr
                and element_reading(element.decode(), 0).rssi == rssi
            ), element  # type: ignore[union-attr]
    assert (q_element(-7, -112), q_element(-12, -73), q_element(23, -7)) == (b"QA7L2", b"QB273", b"Q2307")


def test_esp32_loraprs_sends_command_7_right_after_its_data_frame() -> None:
    board, out = Board("esp32"), []
    board.out = out.append
    board.air(TEXT, rssi=-118, snr=-7.25)
    frames = kiss.KissDecoder().feed(b"".join(out))
    assert [f.command for f in frames] == [0, 7] and struct.unpack(">hh", frames[1].payload) == (-118, -725)
