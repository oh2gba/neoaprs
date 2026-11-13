"""What Mercury's UI interface says and the scope made of it (neoaprs/mercuryscope.py): the spectrum frame, the status message, the two commands, the level worked back from the spectrum's own scale (white noise of a known
RMS), and the rows of the waterfall: the passband at the modem's own bins, two spectra to a row, a byte of dB
on the modem's scale, and the binary frame the page is sent."""
import json
import math
import random

import pytest

from neoaprs import mercuryscope as ms
from neoaprs.mercury import TUNE_LEVEL_DBFS, tune_level
from neoaprs.mercuryscope import RowMeter, ScopeRow, Spectrum, parse_row, parse_spectrum, parse_status, row_frame, spectrum_frame

BINS = 512


def noise_spectrum(rms: float, jitter: float = 0.0, rate: int = 8000) -> Spectrum:
    """The spectrum Mercury makes of white noise of this RMS (in units of the 16-bit sample): 10 log (384 s^2) minus the modem's full scale in every bin."""
    level = 10 * math.log10(ms.WINDOW_POWER * rms * rms) - ms.FULL_SCALE_DB
    return Spectrum(rate, tuple(level + random.uniform(-jitter, jitter) for _ in range(BINS)))


def test_a_spectrum_frame_is_the_magic_the_size_the_rate_and_the_floats_and_comes_back_as_they_were() -> None:
    db = [float(i) / 4 - 60 for i in range(BINS)]
    frame = spectrum_frame(db, 8000)
    assert frame[:4] == bytes([0x59, 0x52, 0x43, 0x4D]) and len(frame) == 8 + 4 * BINS, "the magic 0x4D435259 and the floats, little-endian, as Mercury's spectrum_publisher_thread writes them"
    spectrum = parse_spectrum(frame)
    assert spectrum is not None and spectrum.sample_rate == 8000 and list(spectrum.db) == db and spectrum.hz_per_bin() == pytest.approx(7.8125)


def test_a_frame_that_is_no_spectrum_is_none() -> None:
    good = spectrum_frame([0.0] * 16)
    assert parse_spectrum(good) is not None
    assert parse_spectrum(b"") is None and parse_spectrum(good[:6]) is None
    assert parse_spectrum(b"\x00" + good[1:]) is None, "the magic"
    assert parse_spectrum(good[:-1]) is None and parse_spectrum(good + b"\x00") is None, "the size must be the header and the floats"
    assert parse_spectrum(ms.SPECTRUM_HEADER.pack(ms.SPECTRUM_MAGIC, 0, 8000)) is None and parse_spectrum(ms.SPECTRUM_HEADER.pack(ms.SPECTRUM_MAGIC, 16, 0) + bytes(64)) is None


def test_a_spectrum_with_a_bin_that_is_not_a_number_or_infinitely_high_is_none_and_the_rows_go_on_after_it() -> None:
    for bad in (math.nan, math.inf):
        frame = spectrum_frame([-60.0] * (BINS - 1) + [bad])
        assert parse_spectrum(frame) is None
    assert parse_spectrum(spectrum_frame([-60.0] * (BINS - 1) + [-math.inf])) is not None, "silence is a bin of minus infinity and stays"
    meter = RowMeter()
    made = []
    for bad in (None, math.nan, None, math.inf, None, None):
        spectrum = parse_spectrum(spectrum_frame([-60.0] * 100 + [bad if bad is not None else -60.0] + [-60.0] * (BINS - 101)))
        if spectrum is not None:
            made.append(meter.feed(spectrum, False))
    assert [row is not None for row in made] == [False, True, False, True], "a bad spectrum is dropped whole and every later pair still makes its row"


def test_the_status_message_gives_the_gain_the_peak_and_the_audio_health_and_anything_else_is_none() -> None:
    text = json.dumps({"type": "status", "snr": 1.5, "tx_gain_db": -3.0, "tx_peak_dbfs": -6.4, "audio_ok": True, "audio_error": "", "busy": ""})
    assert parse_status(text) == ms.UiStatus(-3.0, -6.4, True)
    assert parse_status(json.dumps({"type": "capture_dev_list", "list": []})) is None
    assert parse_status("not json") is None and parse_status("[1]") is None
    assert parse_status(json.dumps({"type": "status", "tx_gain_db": "0", "tx_peak_dbfs": 0, "audio_ok": True})) is None, "a field of the wrong kind"
    assert parse_status(json.dumps({"type": "status", "tx_gain_db": 0})) is None, "a field missing"


def test_the_commands_are_what_mercury_takes() -> None:
    assert json.loads(ms.waterfall_command(True)) == {"command": "set_waterfall", "value": "on"}
    assert json.loads(ms.waterfall_command(False)) == {"command": "set_waterfall", "value": "off"}, "any value but off turns the feed on"
    assert json.loads(ms.tx_gain_command(-3)) == {"command": "set_tx_gain", "value": "-3"} and json.loads(ms.tx_gain_command(2.5))["value"] == "2.5"


def test_the_gain_is_a_whole_number_between_mercurys_limits() -> None:
    assert (ms.TX_GAIN_MIN_DB, ms.TX_GAIN_MAX_DB) == (-20, 20), "ui_communication.c clamps set_tx_gain to them"
    assert [ms.clamp_gain(x) for x in (-99, -20.4, 0.4, 3.6, 20, 55)] == [-20, -20, 0, 4, 20, 20]


def test_the_tune_tone_follows_the_gain_as_far_as_tune_goes() -> None:
    assert tune_level(0) == TUNE_LEVEL_DBFS == -15.0
    assert tune_level(6) == -9.0 and tune_level(-20) == -35.0
    assert tune_level(20) == 0.0 and tune_level(40) == 0.0, "TUNE takes no more than 0 dBFS"
    assert tune_level(-80) == -60.0, "and no less than -60"


@pytest.mark.parametrize("rms", [10.0, 100.0, 1000.0, 8000.0])
def test_the_level_of_white_noise_is_worked_back_to_its_rms_in_the_band(rms: float) -> None:
    """White noise of RMS s fills every one of the 512 bins alike; the passband holds the share of them it covers, and the level is that share of the variance, in dB under a full-scale sample."""
    spectrum = noise_spectrum(rms)
    bins = int(ms.SCOPE_HI_HZ / 7.8125) - int(ms.SCOPE_LO_HZ / 7.8125) + 1
    expected = 20 * math.log10(rms / 32768) + 10 * math.log10(bins / BINS)
    assert ms.level_dbfs(spectrum) == pytest.approx(expected, abs=0.01)
    assert ms.level_dbfs(spectrum, 0, 4000) == pytest.approx(20 * math.log10(rms / 32768), abs=0.01), "the whole spectrum is the noise's own RMS"


def test_the_level_of_a_row_is_in_whole_dbfs_between_silence_and_full_scale() -> None:
    def level(spectrum: Spectrum) -> int:
        meter = RowMeter()
        meter.feed(spectrum, False)
        row = meter.feed(spectrum, False)
        assert row is not None
        return row.level
    assert level(noise_spectrum(3000.0)) == round(20 * math.log10(3000 / 32768) + 10 * math.log10(308 / BINS))
    assert level(Spectrum(8000, (-200.0,) * BINS)) == ms.LEVEL_MIN_DBFS
    assert level(noise_spectrum(1e9)) == ms.LEVEL_MAX_DBFS


# ---- the rows of the waterfall

def flat(db: float, rate: int = 8000, bins: int = BINS) -> Spectrum:
    return Spectrum(rate, (db,) * bins)


def test_the_passband_of_a_row_is_307_bins_of_the_modem_from_the_39th_and_a_byte_is_half_a_db_from_minus_110() -> None:
    assert ms.ROW_BINS == 307 and ms.ROW_FIRST_BIN == 39
    assert ms.ROW_FIRST_BIN * 7.8125 >= ms.SCOPE_LO_HZ > (ms.ROW_FIRST_BIN - 1) * 7.8125, "the first bin is the first whole bin inside the passband"
    assert (ms.ROW_FIRST_BIN + ms.ROW_BINS - 1) * 7.8125 <= ms.SCOPE_HI_HZ < (ms.ROW_FIRST_BIN + ms.ROW_BINS) * 7.8125, "the last is the last whole bin inside it"
    assert [ms.byte_of_db(db) for db in (-110.0, -109.8, -109.6, 0.0, 17.5)] == [0, 0, 1, 220, 255]
    assert ms.byte_of_db(-232.0) == 0 and ms.byte_of_db(40.0) == 255, "what the byte cannot hold is the nearest byte"


def test_a_row_is_two_spectra_averaged_in_power_and_the_bins_are_those_of_the_passband() -> None:
    meter = RowMeter()
    low, high = [-60.0] * BINS, [-60.0] * BINS
    low[100], high[100] = -50.0, -40.0
    low[38], high[38] = 0.0, 0.0                                         # (a bin under the passband)
    low[346], high[346] = 0.0, 0.0                                       # (and one over it)
    assert meter.feed(Spectrum(8000, tuple(low)), False) is None, "one spectrum is half a row"
    row = meter.feed(Spectrum(8000, tuple(high)), False)
    assert row is not None and len(row.bins) == ms.ROW_BINS and row.tx is False
    mean = 10 * math.log10((10 ** -5 + 10 ** -4) / 2)
    assert row.bins[100 - ms.ROW_FIRST_BIN] == ms.byte_of_db(mean), "the mean of the powers, not of the dB (-50 and -40 make -43.4, not -45)"
    assert set(row.bins) == {ms.byte_of_db(-60.0), ms.byte_of_db(mean)}, "nothing of the bins beside the passband is in the row"
    assert meter.feed(flat(-60.0), False) is None and meter.feed(flat(-60.0), False) is not None, "and the next row is the next two"


def test_a_row_says_the_level_of_the_passband_and_whether_the_radio_transmitted() -> None:
    meter = RowMeter()
    meter.feed(noise_spectrum(300.0), False)
    row = meter.feed(noise_spectrum(300.0), False)
    assert row is not None and row.level == round(ms.level_dbfs(noise_spectrum(300.0))) and -45 < row.level < -35, "the level is the passband's: white noise of RMS 300 of 32768 is -40.8 dBFS over the whole spectrum"
    loud = RowMeter()
    loud.feed(flat(100.0), False)
    row = loud.feed(flat(100.0), False)
    assert row is not None and row.level == ms.LEVEL_MAX_DBFS and set(row.bins) == {255}
    silent = RowMeter()
    silent.feed(flat(-300.0), False)
    row = silent.feed(flat(-300.0), False)
    assert row is not None and row.level == ms.LEVEL_MIN_DBFS and set(row.bins) == {0}


def test_a_row_is_wholly_of_reception_or_wholly_of_our_transmission() -> None:
    meter = RowMeter()
    assert meter.feed(flat(-60.0), False) is None
    assert meter.feed(flat(0.0), True) is None, "the radio keyed between the two: the pair starts again, and the spectrum before it is not in the row"
    row = meter.feed(flat(0.0), True)
    assert row is not None and row.tx is True and set(row.bins) == {ms.byte_of_db(0.0)}
    assert meter.feed(flat(-60.0), False) is None
    row = meter.feed(flat(-60.0), False)
    assert row is not None and row.tx is False and set(row.bins) == {ms.byte_of_db(-60.0)}


def test_a_spectrum_that_is_not_mercurys_is_no_part_of_a_row() -> None:
    meter = RowMeter()
    assert meter.feed(flat(-60.0, bins=256), False) is None and meter.feed(flat(-60.0, rate=16000), False) is None
    assert meter.feed(flat(-60.0), False) is None, "the first spectrum of a row is still the first"
    meter.reset()
    assert meter.feed(flat(-60.0), False) is None, "a reset forgets the half row"


def test_the_binary_frame_is_the_kind_the_flags_the_signed_level_and_the_bytes_and_comes_back_as_it_was() -> None:
    bins = bytes(i % 256 for i in range(ms.ROW_BINS))
    frame = row_frame(ScopeRow(bins, -41, True))
    assert len(frame) == 310 and frame[:3] == bytes([1, 1, 256 - 41]) and frame[3:] == bins
    assert parse_row(frame) == ScopeRow(bins, -41, True)
    assert row_frame(ScopeRow(bins, -90, False))[:3] == bytes([1, 0, 256 - 90]) and parse_row(row_frame(ScopeRow(bins, 0, False))) == ScopeRow(bins, 0, False)
    assert parse_row(frame[:-1]) is None and parse_row(frame + b"\x00") is None and parse_row(b"") is None, "the size is exact"
    assert parse_row(b"\x02" + frame[1:]) is None, "a frame of another kind is no row"
