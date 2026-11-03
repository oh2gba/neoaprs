"""The channel-busy detectors (neoaprs/channelbusy.py) on made-up bands: the debounce, Mercury's own detector worked again (what it does with a frame, a step, a carrier: the facts docs/mercury.md builds on), and the detector
NeoAPRS uses instead while it can read the spectrum (OccupancyBusy): a signal as wide as a frame is busy at any noise level, and a step, a drift, static, a carrier, the slopes of a narrow filter and the quiet are not.
The channels of the measurement, with real Mercury instances, are scripts/mercury-measure autobusy."""
import math
import random
from collections.abc import Callable, Sequence

import pytest

from neoaprs.channelbusy import SILENCE_DB, Debounce, MercuryBusy, OccupancyBusy, OccupancySettings, Timing

BANDS = 17
STEP_SEC = 0.05
FRAME = range(6, 10)                     # the four bands a frame fills (1187 to 1781 Hz)


class Air:
    """The bands a detector is given: noise at a level with the wander of a mean of 19 bins, a few bands lifted, the slopes of a filter."""

    def __init__(self, seed: int = 1, level: float = -30.0, skirts: Sequence[float] = ()) -> None:
        self.rng = random.Random(seed)
        self.level = level
        self.skirts = list(skirts) or [0.0] * BANDS
        self.t = 0.0

    def bands(self, lifted: dict[int, float] | None = None, noise_db: float = 0.0) -> list[float]:
        out = [self.level + noise_db + self.skirts[i] + self.rng.gauss(0.0, 1.0) for i in range(BANDS)]
        for band, db in (lifted or {}).items():
            out[band] = 10 * math.log10(10 ** (out[band] / 10) + 10 ** ((out[band] + db) / 10))
        return out

    def run(self, detector: OccupancyBusy | MercuryBusy, seconds: float, lifted: dict[int, float] | None = None, noise: Callable[[float], float] | None = None) -> list[bool]:
        """The detector's state after each spectrum of `seconds` of the same air (a spectrum every STEP_SEC); `noise` says how many dB the whole noise is up at the second since the start of this run."""
        states = []
        for k in range(int(seconds / STEP_SEC)):
            self.t += STEP_SEC
            states.append(detector.update(self.t, self.bands(lifted, noise(k * STEP_SEC) if noise else 0.0)))
        return states


def first(states: list[bool], value: bool = True) -> float | None:
    return next((i * STEP_SEC for i, s in enumerate(states) if s == value), None)


def frame(db: float) -> dict[int, float]:
    return {band: db for band in FRAME}


# ---- the debounce

def test_a_state_asserts_after_the_debounce_and_releases_after_the_hang_and_a_gap_starts_the_time_again() -> None:
    d = Debounce(Timing(0.3, 1.5))
    assert [d.update(t, True, False) for t in (0.0, 0.2, 0.31)] == [False, False, True]
    assert [d.update(t, False, False) for t in (1.0, 2.0)] == [True, True], "neither above nor below the release: held"
    assert [d.update(t, False, True) for t in (3.0, 4.0, 4.6)] == [True, True, False]
    d = Debounce(Timing(0.3, 1.5))
    assert [d.update(t, t not in (0.2,), False) for t in (0.0, 0.2, 0.4, 0.6, 0.8)] == [False, False, False, False, True], "a dip below starts the 0.3 s again"
    assert [d.update(t, False, t != 1.4) for t in (1.0, 1.2, 1.4, 1.6, 2.8, 3.2)] == [True, True, True, True, True, False], "and a rise over the release starts the hang again"


# ---- Mercury's own detector

def test_mercurys_detector_is_quiet_on_noise_busy_on_a_frame_after_the_debounce_and_clear_after_the_hang() -> None:
    air, d = Air(), MercuryBusy()
    assert not any(air.run(d, 60.0)), "an empty channel is not busy"
    states = air.run(d, 4.0, frame(25.0))
    assert first(states) is not None and 0.2 < (first(states) or 0) < 0.6
    states = air.run(d, 4.0)
    assert 1.2 < (first(states, False) or 0) < 2.0, "the hang: 1.5 s after the last of the signal"


def test_mercurys_detector_takes_a_step_of_20_db_in_the_noise_for_a_signal_for_minutes_and_a_step_of_10_db_for_none() -> None:
    """The facts that cost the channel its 20 s cap (docs/mercury.md): the floor follows a rise of the noise slowly, a minute or two for a big step."""
    air, d = Air(), MercuryBusy()
    air.run(d, 20.0)
    assert not any(air.run(d, 60.0, noise=lambda t: 10.0))
    air, d = Air(), MercuryBusy()
    air.run(d, 20.0)
    states = air.run(d, 90.0, noise=lambda t: 20.0)
    assert states[int(60 / STEP_SEC)] and states[int(80 / STEP_SEC)], "busy 60 s and 80 s after the step"


def test_mercurys_detector_is_held_by_a_carrier_that_stands_out_of_its_band_by_more_than_the_threshold() -> None:
    air, d = Air(), MercuryBusy()
    air.run(d, 20.0)
    assert not any(air.run(d, 30.0, {3: 11.0}))
    assert air.run(d, 30.0, {3: 20.0})[-1], "a carrier 20 dB over its band holds it for as long as it lasts"


def test_digital_silence_is_no_quiet_channel_for_either_detector() -> None:
    for d in (MercuryBusy(), OccupancyBusy()):
        air = Air()
        air.run(d, 5.0)
        silence = [SILENCE_DB - 10.0] * BANDS
        before = d.busy
        assert d.update(100.0, silence) is before and d.busy is before


# ---- the automatic control

def test_the_occupancy_detector_is_quiet_on_noise_for_ten_minutes_at_any_level() -> None:
    for level in (-60.0, -30.0, -5.0):
        air, d = Air(seed=3, level=level), OccupancyBusy()
        assert not any(air.run(d, 600.0)), level


def test_a_frame_is_busy_after_a_fraction_of_a_second_at_any_noise_level_and_clear_about_a_second_and_a_half_after_it() -> None:
    for level in (-60.0, -30.0, -5.0):
        air, d = Air(seed=2, level=level), OccupancyBusy()
        air.run(d, 30.0)
        states = air.run(d, 4.0, frame(12.0))
        assert 0.3 <= (first(states) or 9.9) <= 1.0, level
        states = air.run(d, 5.0)
        assert 0.9 <= (first(states, False) or 9.9) <= 2.2, level


def test_a_weak_frame_is_seen_down_to_where_the_modem_decodes_and_noise_alone_is_not_taken_for_one() -> None:
    seen = {}
    for db in (1.0, 4.5, 6.0, 9.0):
        air, d = Air(seed=5), OccupancyBusy()
        air.run(d, 30.0)
        seen[db] = any(air.run(d, 4.0, frame(db)))
    assert seen == {1.0: False, 4.5: True, 6.0: True, 9.0: True}
    assert not OccupancyBusy().busy


def test_a_carrier_or_two_bands_is_no_frame_and_three_bands_are() -> None:
    for lifted, busy in (({3: 30.0}, False), ({7: 25.0, 8: 25.0}, False), ({7: 12.0, 8: 12.0, 9: 12.0}, True), ({0: 12.0, 1: 12.0, 2: 12.0}, True), ({7: 30.0, 9: 30.0, 11: 30.0}, False)):
        air, d = Air(seed=4), OccupancyBusy()
        air.run(d, 30.0)
        assert any(air.run(d, 6.0, lifted)) is busy, lifted


def test_a_run_of_two_or_four_bands_can_be_asked_for() -> None:
    air, d = Air(seed=4), OccupancyBusy(OccupancySettings(run=2))
    air.run(d, 30.0)
    assert any(air.run(d, 6.0, {7: 12.0, 8: 12.0}))
    air, d = Air(seed=4), OccupancyBusy(OccupancySettings(run=4))
    air.run(d, 30.0)
    assert not any(air.run(d, 6.0, {7: 12.0, 8: 12.0, 9: 12.0}))
    assert any(air.run(d, 6.0, frame(12.0)))


def test_a_rise_of_the_noise_over_the_whole_passband_is_no_signal_a_step_a_drift_or_a_burst_of_static() -> None:
    air, d = Air(seed=6), OccupancyBusy()
    air.run(d, 30.0)
    assert not any(air.run(d, 120.0, noise=lambda t: 20.0)), "a step of 20 dB, which holds Mercury's for two minutes"
    air, d = Air(seed=6), OccupancyBusy()
    air.run(d, 30.0)
    assert not any(air.run(d, 150.0, noise=lambda t: min(12.0, t / 10.0))), "a rise of 12 dB over two minutes"
    air, d = Air(seed=6), OccupancyBusy()
    air.run(d, 30.0)
    assert not any(air.run(d, 60.0, noise=lambda t: 18.0 if (t % 4.0) < 0.15 else 0.0)), "static 18 dB over the noise, 150 ms every 4 s"


def test_the_slopes_of_a_narrow_filter_are_no_signal_with_the_floors_and_a_signal_without_them() -> None:
    skirts = [-22.0, -18.0, -12.0, -6.0] + [0.0] * (BANDS - 8) + [-6.0, -12.0, -18.0, -22.0]
    air, d = Air(seed=7, skirts=skirts), OccupancyBusy()
    assert not any(air.run(d, 120.0)), "flattened: the filter's shape is learned, and no band stands over the others"
    assert any(air.run(d, 6.0, frame(12.0))), "and a frame still does"
    air, bare = Air(seed=7, skirts=skirts), OccupancyBusy(OccupancySettings(flatten=False))
    assert any(air.run(bare, 20.0)), "not flattened: the middle of the passband stands 20 dB over the slopes, for ever"


def test_a_voice_like_signal_that_falls_with_the_pitch_is_seen_and_a_long_signal_does_not_lift_its_own_floor() -> None:
    voice = {i: 18.0 - 1.4 * i for i in range(12)}
    air, d = Air(seed=8), OccupancyBusy()
    air.run(d, 30.0)
    states = air.run(d, 60.0, voice)
    assert first(states) is not None and states[-1] and states[int(25 / STEP_SEC)], "busy for as long as it lasts"
    assert first(air.run(d, 6.0), False) is not None, "and clear after it"


def test_a_signal_that_fades_a_little_keeps_the_channel_busy_and_one_that_fades_away_does_not() -> None:
    air, d = Air(seed=9), OccupancyBusy()
    air.run(d, 30.0)
    assert any(air.run(d, 2.0, frame(10.0)))
    assert air.run(d, 3.0, frame(3.5))[-1], "kept at 2 dB over"
    assert not air.run(d, 4.0)[-1]


def test_the_transmitters_own_signal_is_forgotten_by_a_pause_and_the_floors_are_kept() -> None:
    air, d = Air(seed=10), OccupancyBusy()
    air.run(d, 30.0)
    air.run(d, 3.0, frame(25.0))
    assert d.busy
    d.pause()
    assert not d.busy
    states = air.run(d, 3.0, frame(12.0))
    assert first(states) is not None and (first(states) or 9.0) < 1.0, "the floors are still the quiet ones: a signal that is there after the pause is seen at once"


def test_a_spectrum_of_another_size_starts_the_floors_again() -> None:
    d = OccupancyBusy()
    for k in range(40):
        d.update(k * STEP_SEC, [-30.0 + (k % 3) * 0.1] * BANDS)
    for k in range(40, 80):
        d.update(k * STEP_SEC, [-30.0 + (k % 3) * 0.1] * 12)
    assert not d.busy


@pytest.mark.parametrize("make", [MercuryBusy, OccupancyBusy])
def test_a_detector_that_has_just_begun_does_not_make_a_signal_of_the_first_reading(make: Callable[[], OccupancyBusy | MercuryBusy]) -> None:
    d = make()
    assert not d.update(0.0, [-30.0] * BANDS) and not d.busy
