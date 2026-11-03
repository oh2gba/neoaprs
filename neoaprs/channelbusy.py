"""Channel-busy detectors that work on the bands of the spectrum (neoaprs/mercuryscope.py `bands_db`: the mean power of each 150 Hz band of 300 to 2700 Hz in dB, twenty times a second), as pure streaming objects: `update(now_sec, bands)`
returns whether the channel is busy. Two are here. `MercuryBusy` is Mercury's own detector (`modem/channel_busy.c` of 1.9.21), worked again so that it can be held beside another on the very spectra it sees: a peak band over a floor that
is tracked slowly. `OccupancyBusy` asks another question of the same bands: is there a signal as wide as a frame, whatever the noise round it is doing. The comparison, its channels and its numbers are in docs/mercury.md."""
import math
from collections.abc import Sequence
from dataclasses import dataclass

SILENCE_DB = -180.0                      # Mercury's BUSY_SILENCE_DB: digital silence (the zeros of a radio that transmits) is no quiet channel, and leaves the state and the floor alone


@dataclass(frozen=True)
class Timing:
    """How a detector turns a reading into a state: BUSY after `debounce_sec` of the reading above, CLEAR after `hang_sec` of it below."""
    debounce_sec: float = 0.3
    hang_sec: float = 1.5


class Debounce:
    """The debounced state of a reading that is above or below its level, as Mercury's detector holds it (the assert and the release use their own levels, so the caller says which applies)."""

    def __init__(self, timing: Timing) -> None:
        self.timing = timing
        self.busy = False
        self._above_since: float | None = None
        self._below_since: float | None = None

    def update(self, now: float, above: bool, below: bool) -> bool:
        """`above`: the reading is over the level that asserts BUSY; `below`: it is under the level that releases it. Returns the state."""
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
    fall: float = 0.20                   # the floor moves toward a lower reading by this part of the way at each spectrum, toward a higher one by `rise`, and by `held` while BUSY (channel_busy.c)
    rise: float = 0.003
    held: float = 0.0006


class MercuryBusy:
    """Mercury's detector: BUSY when the loudest band is `threshold_db` over the floor (the quarter-quietest band, tracked asymmetrically) for the debounce, CLEAR when it is `hysteresis_db` lower for the hang."""

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
    """The numbers of OccupancyBusy; the defaults are the ones the measurement of docs/mercury.md chose (`scripts/mercury-measure autobusy`)."""
    lift_db: float = 4.0                 # a band is lifted when it stands this far over the quiet reference
    keep_db: float = 2.0                 # and stays counted while it stands this far (a signal that fades a little does not flicker)
    run: int = 3                         # adjacent lifted bands that make a signal: 450 Hz, where a frame is 562 and a carrier 20
    smooth_sec: float = 0.25             # the bands are averaged over this long before they are compared (noise bands wander by a dB or two from one spectrum to the next)
    quantile: float = 0.25               # the quiet reference is this quantile of the bands, now
    flatten: bool = True                 # each band is first taken from its own slow floor, so that the slopes of a receiver's filter are not a lift
    floor_rise_sec: float = 17.0         # how slowly that floor rises toward a higher reading (Mercury's own 0.003 of the way at twenty spectra a second)
    floor_fall_sec: float = 2.0          # and how fast it falls toward a lower one
    timing: Timing = Timing(0.3, 0.8)    # BUSY after 0.3 s of a signal; CLEAR 0.8 s after it, to which the smoothing adds 0.6 s: a frame's PTT OFF to CLEAR is about the 1.5 s Mercury's own takes


class OccupancyBusy:
    """BUSY while a run of adjacent bands stands over the quiet reference of the same moment. Each band is first taken over its own slow floor (the slopes of a receiver's filter are no signal), and the reference is a low
    quantile of those, now: a rise of the noise over the whole passband (a step, a slow drift, a burst of static) moves it with the bands and is no signal, a carrier, narrower than a band, is a run of one, and a frame,
    562 Hz wide, a run of three or four."""

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
        """The radio transmits: what it hears is its own signal. The state and the averaging are forgotten, the floors, which move slowly, are kept."""
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
        """The bands averaged in power over `smooth_sec`, in dB."""
        power = [10 ** (b / 10) for b in bands]
        if self._power is None or self._last is None or len(self._power) != len(power):
            self._power = power
        else:
            alpha = 1 - math.exp(-max(0.0, now - self._last) / self.settings.smooth_sec) if self.settings.smooth_sec > 0 else 1.0
            self._power = [old + alpha * (new - old) for old, new in zip(self._power, power, strict=True)]
        self._last = now
        return [10 * math.log10(p + 1e-30) for p in self._power]

    def _flattened(self, smooth: list[float], now: float) -> list[float]:
        """The bands over their own slow floors, which fall to a lower reading in `floor_fall_sec` and rise in `floor_rise_sec` (not at all while BUSY, so that a frame does not lift its own floor)."""
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
