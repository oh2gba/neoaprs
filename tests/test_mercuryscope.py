"""What Mercury's UI interface says and the scope made of it (neoaprs/mercuryscope.py): the spectrum frame, the status message, the two commands, the level worked back from the spectrum's own scale (white noise of a known
RMS), and the meter that turns the stream of spectra into a picture every 0.2 s with a floor kept slowly."""
import json
import math
import random

import pytest

from neoaprs import mercuryscope as ms
from neoaprs.mercury import TUNE_LEVEL_DBFS, tune_level
from neoaprs.mercuryscope import SCOPE_BINS, ScopeMeter, Spectrum, parse_spectrum, parse_status, spectrum_frame

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


def test_a_band_is_the_mean_power_of_its_bins() -> None:
    db = [-60.0] * BINS
    db[200] = -40.0
    spectrum = Spectrum(8000, tuple(db))
    lo, hi = 200 * 7.8125, 205 * 7.8125
    assert ms.band_db(spectrum, lo, hi) == pytest.approx(10 * math.log10((10 ** -4 + 5 * 10 ** -6) / 6), abs=0.01)


def picture(meter: ScopeMeter, spectra: list[Spectrum], update_floor: bool = True) -> ms.ScopeFrame:
    for spectrum in spectra:
        meter.feed(spectrum)
    frame = meter.take(update_floor)
    assert frame is not None
    return frame


def test_the_meter_has_no_picture_until_a_spectrum_is_fed_and_a_picture_uses_up_what_was_fed() -> None:
    meter = ScopeMeter()
    assert meter.take() is None
    meter.feed(noise_spectrum(300.0))
    assert meter.take() is not None and meter.take() is None


def test_quiet_noise_is_the_floor_and_a_tone_stands_over_it_in_its_own_bin() -> None:
    random.seed(1)
    meter = ScopeMeter()
    quiet = picture(meter, [noise_spectrum(300.0, 0.0) for _ in range(4)])
    assert len(quiet.bins) == SCOPE_BINS and set(quiet.bins) == {0}, "the floor is the noise: nothing stands over it"
    db = list(noise_spectrum(300.0).db)
    tone_bin = round(1500 / 7.8125)
    db[tone_bin] += 30
    loud = picture(meter, [Spectrum(8000, tuple(db)) for _ in range(4)])
    index = (1500 - ms.SCOPE_LO_HZ) // 50
    assert loud.bins[index] > 15 and max(loud.bins[:index - 1]) == 0 and max(loud.bins[index + 2:]) == 0, "only the 50 Hz bin of the tone"
    assert loud.level > quiet.level


def test_the_level_is_in_whole_dbfs_between_silence_and_full_scale() -> None:
    meter = ScopeMeter()
    assert picture(meter, [noise_spectrum(3000.0)]).level == round(20 * math.log10(3000 / 32768) + 10 * math.log10(308 / BINS))
    assert picture(meter, [Spectrum(8000, (-200.0,) * BINS)]).level == ms.LEVEL_MIN_DBFS
    assert picture(meter, [noise_spectrum(1e9)]).level == ms.LEVEL_MAX_DBFS


def test_the_floor_falls_fast_and_rises_slowly_so_that_a_signal_is_not_taken_for_it() -> None:
    meter = ScopeMeter()
    picture(meter, [noise_spectrum(300.0)])
    assert meter.floor is not None
    before = meter.floor
    for _ in range(5):
        picture(meter, [noise_spectrum(3000.0)])                      # a step of 20 dB in all the bins
    assert meter.floor - before < 10, "five pictures (a second) have moved the floor a fraction of the step"
    step = picture(meter, [noise_spectrum(3000.0)])
    assert max(step.bins) >= 10, "and the step still stands over it"
    for _ in range(200):                                              # (forty seconds)
        picture(meter, [noise_spectrum(3000.0)])
    assert meter.floor - before > 15, "in the end the step is the floor"
    high = meter.floor
    picture(meter, [noise_spectrum(300.0)])
    assert meter.floor < high - 5, "and a lower reading is the floor again at once"


def test_the_floor_stands_still_while_the_radio_transmits() -> None:
    meter = ScopeMeter()
    picture(meter, [noise_spectrum(300.0)])
    floor = meter.floor
    picture(meter, [noise_spectrum(8000.0)], update_floor=False)
    assert meter.floor == floor, "the spectrum is of our own signal then"


def test_a_new_start_forgets_the_floor() -> None:
    meter = ScopeMeter()
    picture(meter, [noise_spectrum(300.0)])
    meter.feed(noise_spectrum(300.0))
    meter.reset()
    assert meter.floor is None and meter.take() is None
