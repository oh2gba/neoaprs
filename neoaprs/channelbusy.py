"""Channel-busy detectors that work on spectrum bands, as pure streaming objects.

`update(now_sec, bands)` takes the mean dB power of each 150 Hz band from 300 to 2700 Hz and
returns whether the channel is busy. `MercuryBusy` copies Mercury's detector.
"""
import math
from collections.abc import Sequence
from dataclasses import dataclass

# Mercury's BUSY_SILENCE_DB: digital silence leaves the state alone.
SILENCE_DB = -180.0


@dataclass(frozen=True)
class Timing:
    """BUSY after `debounce_sec` of the reading above its level, CLEAR after `hang_sec` below."""
    debounce_sec: float = 0.3
    hang_sec: float = 1.5


class Debounce:
    """Debounced busy state; the caller says whether the reading asserts or releases."""

    def __init__(self, timing: Timing) -> None:
        self.timing = timing
        self.busy = False
        self._above_since: float | None = None
        self._below_since: float | None = None

    def update(self, now: float, above: bool, below: bool) -> bool:
        """Return the state; `above` asserts BUSY, `below` releases it."""
        if not self.busy:
            if above:
                self._above_since = now if self._above_since is None else self._above_since
                if now - self._above_since >= self.timing.debounce_sec:
                    self.busy, self._above_since, self._below_since = True, None, None
            else:
                self._above_since = None
        elif below:
            self._below_since = now if self._below_since is None else self._below_since
            if now - self._below_since >= self.timing.hang_sec:
                self.busy, self._above_since, self._below_since = False, None, None
        else:
            self._below_since = None
        return self.busy


@dataclass(frozen=True)
class MercurySettings:
    threshold_db: float = 14.0
    hysteresis_db: float = 3.0
    timing: Timing = Timing()
    # Fraction the floor moves per spectrum: to a lower reading, a higher one, one while BUSY.
    fall: float = 0.20
    rise: float = 0.003
    held: float = 0.0006


class MercuryBusy:
    """BUSY when the loudest band is `threshold_db` over the floor, CLEAR `hysteresis_db` lower.

    The floor is the quarter-quietest band, tracked asymmetrically.
    """

    def __init__(self, settings: MercurySettings | None = None) -> None:
        self.settings = settings = settings or MercurySettings()
        self.floor: float | None = None
        self._state = Debounce(settings.timing)

    @property
    def busy(self) -> bool:
        return self._state.busy

    def update(self, now: float, bands: Sequence[float]) -> bool:
        s = self.settings
        peak = max(bands)
        if peak < SILENCE_DB:
            return self._state.busy
        candidate = sorted(bands)[len(bands) // 4]
        if self.floor is None:
            self.floor = candidate
        elif candidate < self.floor:
            self.floor += s.fall * (candidate - self.floor)
        else:
            self.floor += (s.held if self._state.busy else s.rise) * (candidate - self.floor)
        excess = peak - self.floor
        return self._state.update(now, excess >= s.threshold_db, excess < s.threshold_db - s.hysteresis_db)


@dataclass(frozen=True)
class OccupancySettings:
    """The numbers of OccupancyBusy."""
    # A band is lifted at `lift_db` over the quiet reference and stays counted at `keep_db`.
    lift_db: float = 4.0
    keep_db: float = 2.0
    run: int = 3
    smooth_sec: float = 0.25
    quantile: float = 0.25
    # Subtract each band's slow floor, so that receiver filter slopes are not a lift.
    flatten: bool = True
    floor_rise_sec: float = 17.0
    floor_fall_sec: float = 2.0
    timing: Timing = Timing(0.3, 0.8)


class OccupancyBusy:
    """BUSY while a run of adjacent bands stands over a low quantile of the flattened bands."""

    def __init__(self, settings: OccupancySettings | None = None) -> None:
        self.settings = settings = settings or OccupancySettings()
        self._power: list[float] | None = None
        self._last: float | None = None
        self._floor: list[float] | None = None
        self._floor_at: float | None = None
        self._state = Debounce(settings.timing)

    @property
    def busy(self) -> bool:
        return self._state.busy

    def pause(self) -> None:
        """Reset the state and averaging while the radio transmits; the slow floors are kept."""
        self._power = self._last = None
        self._state = Debounce(self.settings.timing)

    def update(self, now: float, bands: Sequence[float]) -> bool:
        s = self.settings
        if max(bands) < SILENCE_DB:
            return self._state.busy
        smooth = self._smoothed(now, bands)
        if s.flatten:
            smooth = self._flattened(smooth, now)
        reference = sorted(smooth)[min(len(smooth) - 1, int(len(smooth) * s.quantile))]
        asserted = self._run([b - reference >= s.lift_db for b in smooth]) >= s.run
        kept = self._run([b - reference >= s.keep_db for b in smooth]) >= s.run
        return self._state.update(now, asserted, not kept)

    def _smoothed(self, now: float, bands: Sequence[float]) -> list[float]:
        power = [10 ** (b / 10) for b in bands]
        if self._power is None or self._last is None or len(self._power) != len(power):
            self._power = power
        else:
            alpha = 1 - math.exp(-max(0.0, now - self._last) / self.settings.smooth_sec) if self.settings.smooth_sec > 0 else 1.0
            self._power = [old + alpha * (new - old) for old, new in zip(self._power, power, strict=True)]
        self._last = now
        return [10 * math.log10(p + 1e-30) for p in self._power]

    def _flattened(self, smooth: list[float], now: float) -> list[float]:
        """Return the bands minus their slow floors.

        A floor does not rise while BUSY, so that a frame does not lift its own floor.
        """
        s = self.settings
        if self._floor is None or self._floor_at is None or len(self._floor) != len(smooth):
            self._floor = list(smooth)
        else:
            dt = max(0.0, now - self._floor_at)
            fall = 1 - math.exp(-dt / s.floor_fall_sec) if s.floor_fall_sec > 0 else 1.0
            rise = 0.0 if self._state.busy else 1 - math.exp(-dt / s.floor_rise_sec)
            self._floor = [low + (fall if band < low else rise) * (band - low) for band, low in zip(smooth, self._floor, strict=True)]
        self._floor_at = now
        return [band - low for band, low in zip(smooth, self._floor, strict=True)]

    @staticmethod
    def _run(flags: Sequence[bool]) -> int:
        longest = current = 0
        for flag in flags:
            current = current + 1 if flag else 0
            longest = max(longest, current)
        return longest
