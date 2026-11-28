"""The TNC's bytes (neoaprs/tncmode.py): KISS or command-mode text, text after KISS, and the packet in
a KISS frame."""

from datetime import UTC, datetime

import pytest

from neoaprs import ax25, kiss
from neoaprs.packet import Position
from neoaprs.radiotype import FM_ID, HF_ID
from neoaprs.reading import Reading
from neoaprs.tncmode import (
    Mode,
    ModeDetector,
    TextAfterKiss,
    TextWatch,
    is_ui,
    looks_valid,
    packet_of,
    printable,
    read_frame,
    typed_text,
)

T = datetime(2026, 11, 28, 12, 0, tzinfo=UTC)
FRAME = ax25.Frame(
    ax25.Address.parse("APRS"), ax25.Address.parse("OH2XYZ-9"), (ax25.Address.parse("WIDE1-1"),), info=b">hi"
)
UI = kiss.encode(ax25.encode(FRAME))
NOT_UI = kiss.encode(ax25.encode(ax25.Frame(FRAME.destination, FRAME.source, control=0x3F)))
# A TNC's own command: TXDELAY (command 1) with a value, and data on port 1 that is a command too
TXDELAY = kiss.encode(b"\x32", command=1)
PROMPT = b"cmd:"
HEADER = b"OH2XYZ-9>APRS,WIDE1-1*:>hi\r\n"


def kiss_frame(data: bytes) -> kiss.KissFrame:
    [frame] = kiss.KissDecoder().feed(data)
    return frame


# ---- the mode of the bytes


def test_a_whole_ui_frame_is_kiss_and_stays_kiss_whatever_follows_until_rearmed() -> None:
    detector = ModeDetector()
    assert detector.mode is Mode.UNKNOWN
    assert detector.feed(UI) is Mode.KISS
    assert detector.feed(PROMPT + b"\r\n") is Mode.KISS, "text after KISS is TextAfterKiss's, not a change of mode"
    detector.rearm()
    assert detector.mode is Mode.UNKNOWN and detector.feed(PROMPT) is Mode.MONITOR


def test_a_ui_frame_in_pieces_is_kiss_when_its_closing_fend_comes() -> None:
    detector = ModeDetector()
    for piece in (UI[:1], UI[1:9], UI[9:-1]):
        assert detector.feed(piece) is Mode.UNKNOWN
    assert detector.feed(UI[-1:]) is Mode.KISS


@pytest.mark.parametrize(
    "frame",
    [TXDELAY, NOT_UI, kiss.encode(b"\x01\x02\x03"), kiss.encode(ax25.encode(FRAME), port=0, command=6)],
    ids=["a command of the tnc", "a frame that is not ui", "bytes that are no ax25", "the set-hardware command"],
)
def test_a_kiss_frame_that_is_no_packet_does_not_make_the_line_kiss(frame: bytes) -> None:
    assert ModeDetector().feed(frame * 3) is Mode.UNKNOWN
    assert not looks_valid(frame, True)


@pytest.mark.parametrize(
    "text",
    [PROMPT, b"\r\n" + PROMPT + b"\x11", HEADER, b"OH2XYZ>APRS:hello\r", b"OH2XYZ-9>APRS,WIDE1 <UI>:>hi\r"],
    ids=["the prompt", "the th-d7 prompt with xon", "a monitored header", "a header with no path", "kantronics"],
)
def test_command_mode_text_is_monitor(text: bytes) -> None:
    assert ModeDetector().feed(text) is Mode.MONITOR


def test_text_in_pieces_is_monitor_once_its_evidence_is_whole() -> None:
    detector = ModeDetector()
    assert detector.feed(b"\r\ncm") is Mode.UNKNOWN
    assert detector.feed(b"d:") is Mode.MONITOR


@pytest.mark.parametrize(
    "noise",
    [b"", b"hello world\r\n", b"ABCDEFG>APRS:x\r", b"\x00\x01\x02\xff" * 40, b"cm\x80d:", b"\x80cmd:"],
    ids=["nothing", "plain words", "a call too long", "binary", "a non-text byte inside", "a non-text byte first"],
)
def test_noise_and_plain_words_are_neither(noise: bytes) -> None:
    assert ModeDetector().feed(noise) is Mode.UNKNOWN
    assert not looks_valid(noise, True)


def test_a_tnc_in_command_mode_that_is_put_into_kiss_is_kiss() -> None:
    detector = ModeDetector()
    assert detector.feed(PROMPT) is Mode.MONITOR
    assert detector.feed(UI) is Mode.KISS


def test_text_and_a_frame_in_one_chunk_are_told_apart_by_their_fends() -> None:
    assert ModeDetector().feed(TXDELAY + PROMPT) is Mode.MONITOR, "the text after the frame's FEND is text"
    assert ModeDetector().feed(kiss.encode(PROMPT)) is Mode.UNKNOWN, (
        "a frame whose data reads cmd: starts with its command byte 0x00: no text"
    )


def test_rearm_forgets_the_half_frame_and_the_half_line() -> None:
    detector = ModeDetector()
    detector.feed(UI[:-1])
    detector.feed(b"cm")
    detector.rearm()
    assert detector.feed(UI[-1:]) is Mode.UNKNOWN, "the frame's first half was forgotten"
    assert detector.feed(b"d:") is Mode.UNKNOWN, "and so was the line's"


def test_looks_valid_takes_kiss_always_and_command_mode_only_when_the_radio_can_be_put_into_kiss() -> None:
    assert looks_valid(UI, False) and looks_valid(UI, True)
    assert looks_valid(PROMPT, True) and not looks_valid(PROMPT, False)


# ---- the stretch between FENDs


@pytest.mark.parametrize(
    "segment",
    [PROMPT, b"\x13" + PROMPT, b"\x11" + PROMPT, b"\t" + PROMPT, b"\r" + PROMPT, b"\n" + PROMPT, b"junk\x13cmd:"],
    ids=["plain", "xoff first", "xon first", "tab first", "cr first", "lf first", "xoff ends a line"],
)
def test_xon_xoff_tab_and_line_ends_are_text_and_end_a_line(segment: bytes) -> None:
    assert typed_text(segment)


def test_a_stretch_that_starts_with_a_byte_that_is_no_text_is_a_frame() -> None:
    assert not typed_text(b"")
    assert not typed_text(b"\x00" + PROMPT)
    assert not typed_text(b"\x7f" + PROMPT) and not typed_text(b"\x12" + PROMPT)
    assert not typed_text(b"\x00\r" + PROMPT), "a frame whose data has a line that reads cmd:"


def test_a_line_is_judged_by_its_text_up_to_the_first_byte_that_is_none() -> None:
    assert typed_text(b"cmd:\x80\x81")
    assert not typed_text(b"cm\x80d:")


# ---- text after KISS


def test_text_after_the_last_fend_of_a_chunk_is_seen() -> None:
    watch = TextAfterKiss()
    assert not watch.feed(UI)
    assert watch.feed(UI + PROMPT)


def test_a_chunk_that_starts_with_a_fend_counts_from_it() -> None:
    watch = TextAfterKiss()
    assert not watch.feed(b"\x00\x01")
    assert watch.feed(b"\xc0" + PROMPT), "the FEND at the chunk's first byte starts the stretch"
    assert not TextAfterKiss().feed(b"\xc0\x00" + PROMPT), "a frame's command byte after the FEND"


def test_the_stretch_since_the_last_fend_goes_on_over_chunks_and_a_new_fend_starts_it_again() -> None:
    watch = TextAfterKiss()
    assert not watch.feed(b"\xc0\r\ncm")
    assert watch.feed(b"d:\r\n")
    assert not watch.feed(b"\xc0\x00\x01"), "a frame began: the text before its FEND is over"


def test_text_after_kiss_is_judged_by_the_last_bytes_alone() -> None:
    """The stretch kept is the latest TAIL_BYTES: a prompt that long ago does not count."""
    watch = TextAfterKiss()
    assert watch.feed(b"\xc0" + PROMPT)
    assert not watch.feed(b"\x01" * TextAfterKiss.TAIL_BYTES)


# ---- lines of text and no frame

LINE = b"A" * TextWatch.MIN_LINE


def test_two_lines_of_text_hold_sec_apart_raise_the_watch_and_a_frame_clears_it() -> None:
    watch = TextWatch()
    assert watch.alarm is False and watch.feed(b"", 100.0) is False
    assert watch.feed(LINE + b"\r\n", 100.0) is False and watch.alarm is False
    assert watch.feed(LINE + b"\r\n", 100.0 + TextWatch.HOLD_SEC / 2) is False, "half the hold is not enough"
    assert watch.feed(LINE + b"\r", 100.0 + TextWatch.HOLD_SEC) is True and watch.alarm is True
    assert watch.feed(LINE + b"\r", 200.0) is False, "it went on once"
    assert watch.frame() is True and watch.alarm is False and watch.frame() is False


def test_a_line_shorter_than_min_line_is_not_counted() -> None:
    watch = TextWatch()
    watch.feed(LINE[1:] + b"\r\n", 0.0)
    assert not watch.feed(LINE + b"\r\n", TextWatch.HOLD_SEC), "the first line was too short to start the hold"
    assert watch.feed(LINE + b"\r\n", 2 * TextWatch.HOLD_SEC)


def test_a_run_of_text_max_run_long_with_no_line_end_is_a_line() -> None:
    watch = TextWatch()
    run = b"0123456789ABCDEF" * (TextWatch.MAX_RUN // 16)
    watch.feed(run + b"\x00", 0.0)
    assert watch.feed(run + b"\x00", TextWatch.HOLD_SEC), "a non-text byte after it does not undo the line"


def test_text_cut_by_a_byte_that_is_no_text_is_not_a_line() -> None:
    watch = TextWatch()
    for now in (0.0, TextWatch.HOLD_SEC, 2 * TextWatch.HOLD_SEC):
        assert not watch.feed(LINE[:8] + b"\x00" + LINE[8:] + b"\r\n", now)


# ---- the packet in a frame


def test_a_ui_frame_is_its_packet_on_the_radio_that_heard_it() -> None:
    read = read_frame(kiss_frame(UI), T, reading=Reading(snr=4.5, rssi=-80.0), radio_id=HF_ID)
    assert not isinstance(read, str)
    packet, frame = read
    assert frame == FRAME
    assert (packet.direction, packet.source, packet.destination, packet.path, packet.info) == (
        "in",
        "OH2XYZ-9",
        "APRS",
        ("WIDE1-1",),
        b">hi",
    )
    assert (packet.raw, packet.heard_at, packet.via, packet.radio_id) == (ax25.encode(FRAME), T, "rf", HF_ID)
    assert (packet.snr, packet.rssi) == (4.5, -80.0)
    dummy = read_frame(kiss_frame(UI), T, True)
    assert not isinstance(dummy, str) and (dummy[0].via, dummy[0].radio_id) == ("dummy", FM_ID)


@pytest.mark.parametrize(
    ("source", "destination", "info", "symbol", "timestamp"),
    [
        (
            "OH2XYZ-9",
            "APRS",
            b"$GPRMC,063909,A,3349.4302,N,11700.3721,W,43.022,89.3,291099,13.6,E*52",
            ">",
            datetime(1999, 10, 29, 6, 39, 9, tzinfo=UTC),
        ),
        ("OH2XYZ-9", "S32UVT", b'`(_fn"Oj/', "j", None),
        ("OH2XYZ-9", "APRS", b"@281130z6010.00N/02450.00E>hi", ">", datetime(2026, 11, 28, 11, 30, tzinfo=UTC)),
    ],
    ids=["a tracker's symbol from its source's ssid", "mic-e from the destination", "a day and time from now"],
)
def test_a_packet_is_decoded_from_its_source_destination_and_the_time_it_was_heard(
    source: str, destination: str, info: bytes, symbol: str, timestamp: datetime | None
) -> None:
    frame = ax25.Frame(ax25.Address.parse(destination), ax25.Address.parse(source), info=info)
    packet = packet_of("out", ax25.encode(frame), frame, T)
    assert isinstance(packet.decoded, Position)
    assert (packet.decoded.symbol_code, packet.decoded.timestamp) == (symbol, timestamp)
    assert (packet.direction, packet.via, packet.radio_id) == ("out", "rf", FM_ID), "a radio is no dummy unless said"


def test_a_third_party_packet_is_rf_gated() -> None:
    gated = ax25.Frame(FRAME.destination, FRAME.source, info=b"}OH2ABC>APRS,TCPIP,OH2XYZ-9*:>far")
    read = read_frame(kiss_frame(kiss.encode(ax25.encode(gated))), T)
    assert not isinstance(read, str) and read[0].via == "rf-gated"


def test_a_kiss_command_is_not_read_as_a_packet() -> None:
    data = kiss.encode(ax25.encode(FRAME), port=2, command=1)
    assert read_frame(kiss_frame(data), T) == "KISS command 1 on port 2, ignored"
    assert not is_ui(kiss_frame(data))


def test_a_frame_that_is_not_ui_or_not_ax25_says_so() -> None:
    assert read_frame(kiss_frame(NOT_UI), T) == "not a UI frame (control 0x3F, PID 0xF0)"
    said = read_frame(kiss_frame(kiss.encode(b"\x01\x02\x03")), T)
    assert isinstance(said, str) and said.startswith("not an AX.25 frame: ")
    assert not is_ui(kiss_frame(NOT_UI)) and not is_ui(kiss_frame(kiss.encode(b"\x01\x02"))) and is_ui(kiss_frame(UI))


@pytest.mark.expects_errors
def test_a_frame_that_breaks_the_reader_is_logged_and_answered_as_an_internal_error(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def broken(*args: object) -> None:
        raise RuntimeError("parser broken")

    monkeypatch.setattr("neoaprs.aprsthirdparty.parse_packet", broken)
    with caplog.at_level("ERROR", logger="neoaprs.tnc"):
        assert read_frame(kiss_frame(UI), T) == "internal error"
    [record] = caplog.records
    assert record.exc_info is not None and record.getMessage() == "tnc: a frame could not be handled"


def test_printable_shows_what_cannot_be_printed_as_a_question_mark() -> None:
    assert printable("a\x00b\tc\x7fd ä") == "a?b?c?d ä"
