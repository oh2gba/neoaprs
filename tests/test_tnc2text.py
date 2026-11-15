"""The text a TNC or a radio prints of what it hears (neoaprs/tnc2text.py), on the fixtures of tests/fixtures/text/: each `.txt` or `.bin` with a `.json` of the frames expected, the lines that are rejected
and whether the line was found to be 7 bits. The same bytes in any pieces give the same frames; a frame printed as its TNC2 text and read back is the packet its KISS frame gives, but for a CR or LF at the
end of its information; the same text with even or odd parity gives the same frames; noise gives none, and ASCII noise is never taken as 7 bits."""
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from hypothesis import assume, given, strategies as st

from neoaprs import ax25, kiss
from neoaprs.tnc2text import DECIDE_BYTES, DECIDE_QUIET, MAX_LINE, PENDING_SEC, Rejected, TextReader, looks_like_text
from neoaprs.tncmode import packet_of, read_frame
from tests.support.files import FIXTURES, fixture_bytes

TEXT = FIXTURES / "text"
NAMES = sorted(p.name for p in TEXT.iterdir() if p.suffix in (".txt", ".bin"))
NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
CALL_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def read(data: bytes, *, pieces: int = 0) -> tuple[list[ax25.Frame], list[Rejected], TextReader]:
    """What a reader makes of the bytes, fed whole or in pieces of `pieces` bytes, and then a quiet line."""
    reader = TextReader()
    chunks = [data] if pieces == 0 else [data[i:i + pieces] for i in range(0, len(data), pieces)]
    found = [item for chunk in chunks for item in reader.feed(chunk, 0.0)] + reader.feed(b"", PENDING_SEC + 1.0)
    return [f for f in found if isinstance(f, ax25.Frame)], [r for r in found if isinstance(r, Rejected)], reader


def expected(name: str) -> dict[str, object]:
    return json.loads((TEXT / f"{Path(name).stem}.json").read_text())


def as_json(frame: ax25.Frame) -> dict[str, object]:
    return {"source": str(frame.source), "destination": str(frame.destination), "path": [str(a) for a in frame.path], "info": frame.info.decode("latin-1")}


def parity(data: bytes, odd: bool = False) -> bytes:
    """The bytes as a TNC at 7 bits with a parity bit sends them, read by a line opened at 8N1: bit 7 is the parity bit."""
    return bytes((b & 0x7F) | (0x80 if (b & 0x7F).bit_count() % 2 != odd else 0) for b in data)


@pytest.mark.parametrize("name", NAMES)
def test_each_fixture_gives_its_frames_and_rejects_what_began_like_a_header_and_is_none(name: str) -> None:
    want = expected(name)
    frames, rejected, reader = read((TEXT / name).read_bytes())
    assert [as_json(f) for f in frames] == want["frames"], want["note"]
    assert len(rejected) == want["rejected"], [r.reason for r in rejected]
    assert (reader.seven_bit, reader.parity) == (want.get("seven_bit", False), want.get("parity", "")), "7 bits with parity is found by itself, and only on such a line"
    assert all(f.is_ui for f in frames), "every line is a UI frame with PID F0"


@pytest.mark.parametrize("name", NAMES)
def test_the_same_bytes_in_any_pieces_give_the_same_frames(name: str) -> None:
    data = (TEXT / name).read_bytes()
    whole = read(data)[0]
    assert read(data, pieces=1)[0] == whole, "byte by byte"
    for cut in range(1, len(data)):
        reader = TextReader()
        found = reader.feed(data[:cut], 0.0) + reader.feed(data[cut:], 0.1) + reader.feed(b"", PENDING_SEC + 1.0)
        assert [f for f in found if isinstance(f, ax25.Frame)] == whole, f"cut at {cut}"


def test_the_generated_fixtures_are_what_they_say() -> None:
    oneline = fixture_bytes("text/tnc2-oneline.txt")
    assert fixture_bytes("text/tnc2-7e1.bin") == parity(oneline) and fixture_bytes("text/tnc2-7o1.bin") == parity(oneline, odd=True)
    mice = ax25.decode(fixture_bytes("ax25/mic_e.bin"))
    assert fixture_bytes("text/mice.bin") == mice.tnc2().encode("latin-1") + b"\r" and {0x7F, 0x1C, 0x9F} <= set(mice.info)
    assert fixture_bytes("text/mice-filtered.bin") == fixture_bytes("text/mice.bin").replace(b"\x1c", b"", 1)
    assert fixture_bytes("text/mice-7e1.bin") == parity(fixture_bytes("text/mice.bin"))


def test_the_mic_e_fixture_read_from_text_is_its_kiss_frame_and_at_7_bits_its_0x9f_loses_bit_7() -> None:
    kiss_frame = ax25.decode(fixture_bytes("ax25/mic_e.bin"))
    assert type(packet_of("in", ax25.encode(kiss_frame), kiss_frame, NOW).decoded).__name__ == "Undecoded", "no position: these fixtures show which bytes pass; MICE_TH_D7 below is the position"
    [text_frame] = read(fixture_bytes("text/mice.bin"))[0]
    assert text_frame == kiss_frame and packet_of("in", ax25.encode(text_frame), text_frame, NOW).decoded == packet_of("in", ax25.encode(kiss_frame), kiss_frame, NOW).decoded
    [seven] = read(fixture_bytes("text/mice-7e1.bin"))[0]
    assert seven.info == kiss_frame.info.replace(b"\x9f", b"\x1f") and b"\x7f\x1c" in seven.info, "0x7F and 0x1C come through 7 bits; 0x9F arrives as 0x1F"


MICE_TH_D7 = b"OH2GBA-7>VPQP20,WIDE1-1:`4TD\x1dm?>/>Hello\r"          # tests/fixtures/aprs/cases.json, "Mic-E from a TH-D7": 60.17 N 24.94 E, 135 degrees, 33.336 km/h


def test_a_mic_e_position_read_from_text_is_the_same_at_8_and_at_7_bits_and_one_whose_control_character_the_tnc_took_out_is_a_packet_and_no_crash() -> None:
    def position(data: bytes) -> tuple[object, ...]:
        [frame] = read(data)[0]
        decoded = packet_of("in", ax25.encode(frame), frame, NOW).decoded
        return (type(decoded).__name__, getattr(decoded, "lat", None), getattr(decoded, "lon", None), getattr(decoded, "course_deg", None), getattr(decoded, "speed_kmh", None))
    assert position(MICE_TH_D7) == position(parity(MICE_TH_D7)) == ("Position", 60.17, 24.94, 135, 33.336), "Mic-E's bytes are within 0x1C to 0x7F: 7 bits keep them"
    assert position(MICE_TH_D7.replace(b"\x1d", b"", 1)) == ("Undecoded", None, None, None, None), "FILTER ON took 0x1D out: the position is spoiled, the packet is kept (recorded)"
    assert position(fixture_bytes("text/mice-filtered.bin"))[0] == "Undecoded"


def kiss_frames() -> list[ax25.Frame]:
    """Every UI frame of the AX.25 fixtures and of the TH-D7's KISS capture."""
    frames = [ax25.decode((FIXTURES / "ax25" / f"{p.stem}.bin").read_bytes()) for p in sorted((FIXTURES / "ax25").glob("*.bin"))]
    frames += [ax25.decode(k.payload) for k in kiss.KissDecoder().feed(fixture_bytes("kiss/thd7-2026-10-21.bin")) if k.command == 0]
    return [f for f in frames if f.is_ui]


def test_a_frame_printed_as_its_tnc2_text_and_read_back_is_the_packet_its_kiss_frame_gives_but_for_a_cr_or_lf_ending_its_information() -> None:
    frames = kiss_frames()
    ending = [f for f in frames if f.info.endswith((b"\r", b"\n"))]
    assert len(frames) >= 8 and {str(f.source) for f in ending} >= {"OH2RDG", "OH2RDS"}, "two frames of the capture end their information with CR"
    for frame in frames:
        heard = read(frame.tnc2().encode("latin-1") + b"\r")[0]
        cut = ax25.Frame(frame.destination, frame.source, frame.path, info=frame.info.rstrip(b"\r\n"))
        by_kiss = read_frame(kiss.KissFrame(0, 0, ax25.encode(cut)), NOW)
        assert not isinstance(by_kiss, str) and len(heard) == 1, frame.tnc2()
        packet = packet_of("in", ax25.encode(heard[0]), heard[0], NOW)
        assert (packet.source, packet.destination, packet.path, packet.info, packet.decoded) == (by_kiss[0].source, by_kiss[0].destination, by_kiss[0].path, by_kiss[0].info, by_kiss[0].decoded), frame.tnc2()
    for frame in ending:
        assert read(frame.tnc2().encode("latin-1") + b"\r")[0][0].info != frame.info, "without the cut the two differ: the CR ends the line"


# ---- the forms one at a time

def test_a_header_without_its_information_takes_the_next_line_and_is_dropped_when_none_comes_in_time_or_another_header_comes() -> None:
    reader = TextReader()
    assert reader.feed(b"OH2AB>APRS:\r", 0.0) == []
    [frame] = reader.feed(b"\n\n>hello\r", 1.0)
    assert isinstance(frame, ax25.Frame) and frame.info == b">hello", "the Yaesu's line feeds between the two lines do no harm"
    assert reader.feed(b"OH2AB>APRS:\r", 2.0) == [] and reader.feed(b">late\r", 2.0 + PENDING_SEC + 0.5) == [], "the information came too late: the header was dropped, and a line that is no header alone is passed over"
    assert reader.feed(b"OH2AB>APRS:\rOH2CD>APRS:\r>mine\r", 10.0) == [ax25.Frame(ax25.Address("APRS"), ax25.Address("OH2CD"), info=b">mine")], "a header that came meanwhile drops the one held"
    assert reader.feed(b"OH2AB>APRS:\rcmd:\r>still mine\r", 20.0) == [ax25.Frame(ax25.Address("APRS"), ax25.Address("OH2AB"), info=b">still mine")], "a prompt alone is no information"


def test_a_piece_of_a_line_is_forgotten_after_a_quiet_time_and_an_overlong_line_is_dropped_with_its_rest() -> None:
    reader = TextReader()
    assert reader.feed(b"OH2AB>APRS:>hal", 0.0) == [] and reader.feed(b"OH2CD>APRS:>whole\r", PENDING_SEC + 0.5) == [ax25.Frame(ax25.Address("APRS"), ax25.Address("OH2CD"), info=b">whole")]
    long = b"OH2AB>APRS:>" + b"x" * MAX_LINE
    assert reader.feed(long[:300], 10.0) + reader.feed(long[300:] + b"tail\rOH2CD>APRS:>next\r", 10.1) == [ax25.Frame(ax25.Address("APRS"), ax25.Address("OH2CD"), info=b">next")]


@pytest.mark.parametrize(("line", "reason"), [
    (b"OH3AB>OH3CD <DM>:", "<DM>"),
    (b"OH3AB>OH3CD <UA>:", "<UA>"),
    (b"OH3AB>OH3CD <RR>:", "<RR>"),
    (b"TOOLONGCALL>APRS:>x", "not an AX.25 address"),
    (b"OH2AB-16>APRS:>x", "not an AX.25 address"),
    (b"OH2AB>APRS,A,B,C,D,E,F,G,H,I:>x", "at most 8 digipeaters"),
    (b"OH2AB>APRS*:>x", "only a digipeater"),
    (b"OH2AB>OH2CD>APRS,WIDE1-1:>x", "both a chain"),
    (b"OH2AB>OH2CD {NET/ROM}:x", "not AX.25"),
    (b"OH2AB>=garbage:x", "not a header"),
])
def test_a_line_that_began_like_a_header_and_is_none_is_rejected_with_its_reason(line: bytes, reason: str) -> None:
    frames, rejected, _ = read(line + b"\r")
    assert frames == [] and len(rejected) == 1 and reason in rejected[0].reason and rejected[0].text == line.decode("latin-1")


def test_a_mark_that_allows_another_letter_after_ui_is_a_ui_frame_and_a_stamp_before_the_header_is_passed_over() -> None:
    assert [as_json(f) for f in read(b"OH2AB>APRS <UI R>:>x\r22:51:33 OH2CD>APRS:>y\r10-Jul-86 22:54:25 OH2EF>APRS:>z\r")[0]] == [
        {"source": "OH2AB", "destination": "APRS", "path": [], "info": ">x"}, {"source": "OH2CD", "destination": "APRS", "path": [], "info": ">y"}, {"source": "OH2EF", "destination": "APRS", "path": [], "info": ">z"}]


def test_an_information_field_longer_than_ax25_carries_is_rejected_with_its_reason_in_the_one_line_and_the_two_line_form() -> None:
    head, info = b"OH2AB>APRS,WIDE1-1:", b">" + b"x" * 300
    assert len(head + info) < MAX_LINE and len(info) > ax25.MAX_INFO
    for data, text in ((head + info + b"\r", head + info), (head + b"\r" + info + b"\r", info)):
        frames, rejected, _ = read(data)
        assert frames == [] and rejected == [Rejected(text.decode("latin-1"), f"an information field of 301 bytes, more than the {ax25.MAX_INFO} AX.25 allows")], data[:24]
    [frame] = read(head + b">" + b"x" * (ax25.MAX_INFO - 1) + b"\r")[0]
    assert len(frame.info) == ax25.MAX_INFO and ax25.decode(ax25.encode(frame)) == frame, "256 bytes are a frame"


def test_the_search_takes_a_port_whose_text_reads_as_a_heard_packet() -> None:
    assert looks_like_text(fixture_bytes("text/yaesu.txt")) and looks_like_text(fixture_bytes("text/tnc2-7e1.bin")) and looks_like_text(b"cmd:" + fixture_bytes("text/tnc2-manual.txt"))
    assert not looks_like_text(fixture_bytes("text/noise.txt")) and not looks_like_text(kiss.encode(ax25.encode(kiss_frames()[0]))) and not looks_like_text(b"")


def test_a_short_line_of_7_bits_is_decided_when_the_line_goes_quiet() -> None:
    line = parity(b"OH2AB>APRS:>Hello\r")
    assert len(line) < DECIDE_BYTES
    reader = TextReader()
    assert reader.feed(line, 0.0) == [] and reader.bits == 0, "not decided yet: the bytes above 0x7F wait"
    assert reader.feed(b"", PENDING_SEC + 1.0) == [ax25.Frame(ax25.Address("APRS"), ax25.Address("OH2AB"), info=b">Hello")] and reader.seven_bit


@pytest.mark.parametrize("first", [b"cmd:\r", b"OH2AB>APRS:", b"\r\ncmd:cmd:\r"], ids=["prompt", "piece of a line", "eleven bytes"])
def test_a_short_piece_of_7_bits_and_a_quiet_line_leave_the_line_undecided_so_that_the_packets_after_it_are_read_at_7_bits(first: bytes) -> None:
    assert len(first) < DECIDE_QUIET and any(b > 0x7F for b in parity(first))
    reader = TextReader()
    assert reader.feed(parity(first), 0.0) == [] and reader.feed(b"", PENDING_SEC + 1.0) == [] and reader.bits == 0, "too few bytes to tell 7 bits from 8"
    oneline = fixture_bytes("text/tnc2-oneline.txt")
    later = reader.feed(parity(oneline), PENDING_SEC + 2.0) + reader.feed(b"", 2 * PENDING_SEC + 4.0)
    assert reader.seven_bit and reader.parity == "even" and [f for f in later if isinstance(f, ax25.Frame)] == read(oneline)[0] != []


def test_a_line_with_letters_outside_ascii_is_8_bits_at_once() -> None:
    reader = TextReader()
    assert reader.feed("OH2AB>APRS:>Hyvää päivää\r".encode(), 0.0) == [ax25.Frame(ax25.Address("APRS"), ax25.Address("OH2AB"), info=">Hyvää päivää".encode())] and reader.bits == 8


# ---- properties

calls = st.builds(lambda call, ssid: ax25.Address(call, ssid), st.text(alphabet=CALL_CHARS, min_size=1, max_size=6), st.integers(0, 15))
BREAKS = {0x0D, 0x0A, 0x11, 0x13}


@st.composite
def frames(draw: st.DrawFn, seven: bool = False) -> ax25.Frame:
    """A UI frame as a TNC prints it whole: its information has no line end and is not empty, the digipeaters it has been through are the first ones, and the information does not begin with what a
    header may carry after its path (a ` [stamp]`, a ` <mark>`)."""
    path = draw(st.lists(calls, max_size=8))
    used = draw(st.integers(0, len(path)))
    info = draw(st.binary(min_size=1, max_size=200).map(lambda b: bytes(x & 0x7F if seven else x for x in b if (x & 0x7F if seven else x) not in BREAKS)).filter(lambda b: b != b"" and not b.startswith((b" [", b" <", b": <"))))
    return ax25.Frame(draw(calls), draw(calls), tuple(ax25.Address(a.call, a.ssid, i < used) for i, a in enumerate(path)), info=info)


@given(st.lists(frames(), min_size=1, max_size=5), st.lists(st.integers(1, 40), min_size=1, max_size=20))
def test_any_frame_survives_its_text_whatever_the_pieces(sent: list[ax25.Frame], sizes: list[int]) -> None:
    data = b"".join(f.tnc2().encode("latin-1") + b"\r" for f in sent)
    reader, found, at = TextReader(), [], 0
    while at < len(data):
        size = sizes[len(found) % len(sizes)]
        found += reader.feed(data[at:at + size], 0.0)
        at += size
    found += reader.feed(b"", PENDING_SEC + 1.0)
    assert found == sent


@given(st.lists(frames(seven=True), min_size=2, max_size=5), st.booleans())
def test_the_same_text_with_even_or_odd_parity_gives_the_same_frames_and_says_7_bits(sent: list[ax25.Frame], odd: bool) -> None:
    text = b"".join(f.tnc2().encode("latin-1") + b"\r" for f in sent)
    assume(len(text) >= DECIDE_BYTES)                           # (a shorter stream says too little to tell 7 bits from 8: it is read as 8)
    frames_of, _, reader = read(parity(text, odd))
    assert frames_of == read(text)[0] == sent
    assert reader.seven_bit == any((b & 0x7F).bit_count() % 2 != odd for b in text), "7 bits once a byte came with bit 7 set by its parity"


@given(st.binary(max_size=2000).map(lambda b: b.replace(b">", b"").replace(b"\xbe", b"")))
def test_noise_with_no_header_gives_no_frame(noise: bytes) -> None:
    assert read(noise)[0] == [] and read(noise, pieces=7)[0] == []


@given(st.binary(max_size=2000).map(lambda b: bytes(x & 0x7F for x in b)))
def test_ascii_noise_is_never_taken_as_7_bits(noise: bytes) -> None:
    assert not read(noise)[2].seven_bit
