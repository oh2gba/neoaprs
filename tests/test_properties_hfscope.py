"""Properties of the readers of what the Mercury program says: its list of sound cards, and the spectrum,
status, row and history messages of its UI socket, also as a radio's scope frame.
Any listing, a real one damaged above all, gives cards that record or play, never an exception.
A spectrum, a status, a row, a history and a radio frame written read back as they were.
Any bytes or text give the message or None; a number read is finite, a size within the frame.
"""

import json
import math
import struct

from hypothesis import given
from hypothesis import strategies as st

from neoaprs import mercurycards
from neoaprs.mercuryscope import (
    HISTORY_KIND,
    ROW_BINS,
    SPECTRUM_MAX_BINS,
    KeptRow,
    ScopeRow,
    UiStatus,
    history_frame,
    parse_history,
    parse_row,
    parse_spectrum,
    parse_status,
    row_frame,
    spectrum_frame,
)
from neoaprs.web.scopefeed import RADIO_HEADER, parse_radio_frame, radio_header
from tests.support.mutation import mutated_bytes, mutated_json, mutated_text

LINUX_Z = (
    "No configuration file found: running on built-in defaults.\nListing ALSA soundcards:\nplayback devices:\n"
    "device: name: 'USB Audio CODEC'  id: 'plughw:1,0'  (system default)\ndevice: name: 'HDA Intel PCH'  id: 'plughw:0,0'\n"
    "capture devices:\ndevice: name: 'USB Audio CODEC'  id: 'plughw:1,0'  (system default)\n"
)
ROUTE_Z = (
    "playback devices:\ndevice #1: Default (system route) id=default\n"
    "capture devices:\ndevice #1: Default (system route) id=default\n"
)
WINDOWS_Z = (
    "playback devices:\n"
    "device: name: 'Speakers (Realtek High Definition Audio)'  id: '{0.0.0.00000000}.{aaaa}'  (system default)\n"
    "device: name: 'Speakers (USB Audio CODEC)'  id: '{0.0.0.00000000}.{ca03}'\n"
    "capture devices:\n"
    "device: name: 'Microphone (USB Audio CODEC)'  id: '{0.0.1.00000000}.{2301}'\n"
    "device: name: 'Microphone (Realtek High Definition Audio)'  id: '{0.0.1.00000000}.{cccc}'  (system default)\n"
    "device: name: 'Line (Webcam)'  id: '{0.0.1.00000000}.{dddd}'\n"
)
STATUS = {"type": "status", "snr": 1.5, "tx_gain_db": -3.0, "tx_peak_dbfs": -6.4, "audio_ok": True, "busy": ""}

_LISTINGS = st.one_of(st.text(max_size=200), st.sampled_from([LINUX_Z, ROUTE_Z, WINDOWS_Z]).flatmap(mutated_text))
_FLOAT32 = st.floats(width=32, allow_nan=False).filter(lambda v: v != math.inf)
_ROW = st.builds(ScopeRow, st.binary(min_size=ROW_BINS, max_size=ROW_BINS), st.integers(-128, 127), st.booleans())


@given(_LISTINGS, st.dictionaries(st.integers(0, 9), st.text(min_size=1, max_size=8), max_size=3))
def test_any_listing_of_sound_cards_gives_cards_that_record_or_play(text: str, names: dict[int, str]) -> None:
    """Any text gives cards each of which records or plays; a number kept is one the listing has."""
    for card in mercurycards.parse_sound_cards(text, names):
        assert card.playback or card.capture
        if card.numbered:
            assert card.numbered in text


def test_a_device_in_a_list_that_is_neither_playback_nor_capture_is_nothing() -> None:
    """A device under another heading is passed over, not a card that neither records nor plays."""
    assert mercurycards.parse_sound_cards("qlayback devices:\ndevice: name: 'x'  id: 'y'\n") == []


def test_a_card_number_of_thousands_of_digits_is_kept_as_listed() -> None:
    """A card number too long for int() is an id like any other, not a ValueError."""
    listed = f"hw:{'1' * 5000},0"
    cards = mercurycards.parse_sound_cards(f"playback devices:\ndevice: name: 'x'  id: '{listed}'\n", {1: "PCH"})
    assert [c.id for c in cards] == [listed]


@given(st.lists(_FLOAT32, min_size=1, max_size=SPECTRUM_MAX_BINS // 16), st.integers(1, 65535))
def test_a_spectrum_reads_back(db: list[float], rate: int) -> None:
    """parse_spectrum of spectrum_frame is the rate and the bins, -inf (silence) included."""
    spectrum = parse_spectrum(spectrum_frame(db, rate))
    assert spectrum is not None and spectrum.sample_rate == rate and list(spectrum.db) == db


@given(st.one_of(st.binary(max_size=80), mutated_bytes(spectrum_frame([-60.0, -math.inf, 3.5, 0.0] * 4))))
def test_any_bytes_are_a_spectrum_of_its_size_with_no_nan_or_none(frame: bytes) -> None:
    """Any bytes give None or a spectrum whose bins fill the frame, none NaN or +inf, at a rate above 0."""
    spectrum = parse_spectrum(frame)
    if spectrum is not None:
        assert 0 < len(spectrum.db) <= SPECTRUM_MAX_BINS and len(frame) == 8 + 4 * len(spectrum.db)
        assert spectrum.sample_rate > 0 and math.isfinite(spectrum.hz_per_bin())
        assert not any(math.isnan(v) or v == math.inf for v in spectrum.db)


@given(
    st.floats(allow_nan=False, allow_infinity=False), st.floats(allow_nan=False, allow_infinity=False), st.booleans()
)
def test_a_status_reads_back(gain: float, peak: float, ok: bool) -> None:
    """parse_status of a status message is its gain, its peak and its audio health."""
    assert parse_status(json.dumps({**STATUS, "tx_gain_db": gain, "tx_peak_dbfs": peak, "audio_ok": ok})) == UiStatus(
        gain, peak, ok
    )


@given(st.one_of(st.text(max_size=60), mutated_json(STATUS).map(json.dumps), mutated_text(json.dumps(STATUS))))
def test_any_text_is_a_status_with_finite_numbers_or_none(text: str) -> None:
    """Any text, a real status damaged above all, gives None or a status whose numbers are finite."""
    status = parse_status(text)
    if status is not None:
        assert math.isfinite(status.tx_gain_db) and math.isfinite(status.tx_peak_dbfs)


def test_a_status_with_a_number_too_big_or_not_finite_or_nested_too_deep_is_none() -> None:
    """A gain beyond a float, an infinite or NaN peak, and JSON nested past the recursion limit are no status."""
    for gain, peak in (("1" + "0" * 400, "0"), ("0", "Infinity"), ("0", "1e400"), ("NaN", "0")):
        assert parse_status(f'{{"type":"status","tx_gain_db":{gain},"tx_peak_dbfs":{peak},"audio_ok":true}}') is None
    assert parse_status("[" * 100_000) is None


@given(_ROW)
def test_a_row_reads_back(row: ScopeRow) -> None:
    """parse_row of row_frame is the row."""
    assert parse_row(row_frame(row)) == row


@given(
    st.one_of(
        st.binary(max_size=ROW_BINS + 8),
        mutated_bytes(row_frame(ScopeRow(bytes(i % 256 for i in range(ROW_BINS)), -41, True))),
    )
)
def test_any_bytes_are_a_row_of_its_bins_or_none(frame: bytes) -> None:
    """Any bytes give None or a row of ROW_BINS bins at a level of a signed byte."""
    row = parse_row(frame)
    if row is not None:
        assert len(row.bins) == ROW_BINS and -128 <= row.level <= 127


@given(st.lists(st.tuples(_ROW, st.integers(0, 120_000)), max_size=4), st.floats(0, 1e15))
def test_a_history_reads_back(rows: list[tuple[ScopeRow, int]], wall_ms: float) -> None:
    """parse_history of history_frame is each row with its age in ms."""
    now = 1000.0
    kept = [KeptRow(i, now - age / 1000, row) for i, (row, age) in enumerate(rows)]
    assert parse_history(history_frame(kept, now, wall_ms)) == rows


_HISTORY = history_frame([KeptRow(1, 9.5, ScopeRow(bytes(ROW_BINS), -60, False))] * 2, 10.0, 1.7e12)


@given(st.one_of(st.binary(max_size=40).map(lambda b: bytes([HISTORY_KIND]) + b), mutated_bytes(_HISTORY)))
def test_any_bytes_are_rows_that_fill_the_history_or_none(frame: bytes) -> None:
    """Any bytes give None or rows of ROW_BINS bins that fill the frame after its header."""
    rows = parse_history(frame)
    if rows is not None:
        assert 9 + len(rows) * (6 + ROW_BINS) == len(frame)
        assert all(len(row.bins) == ROW_BINS and 0 <= age < 2**32 for row, age in rows)


@given(st.integers(0, 2**32 - 1), st.binary(min_size=1, max_size=40))
def test_a_radio_frame_reads_back(radio: int, inner: bytes) -> None:
    """parse_radio_frame of a radio's header and a frame is the radio and the frame."""
    assert parse_radio_frame(radio_header(radio) + inner) == (radio, inner)


@given(
    st.one_of(st.binary(max_size=20), mutated_bytes(radio_header(2) + row_frame(ScopeRow(bytes(ROW_BINS), 0, False))))
)
def test_any_bytes_are_a_radio_and_the_rest_of_the_frame_or_none(frame: bytes) -> None:
    """Any bytes give None or a radio id of 32 bits and a frame of at least one byte that ends the bytes."""
    found = parse_radio_frame(frame)
    if found is not None:
        radio, inner = found
        assert 0 <= radio < 2**32 and inner and frame == radio_header(radio) + inner
        assert struct.unpack_from("<I", frame, 1)[0] == radio and len(inner) == len(frame) - RADIO_HEADER.size
