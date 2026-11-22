"""Busy detectors held against each other on the same recorded spectra (scripts/mercury-measure
autobusy).

A frame is seen by a busy period that touches the time it was on the air (PTT ON to half a second
after PTT OFF). A BUSY holds our frames for at most BUSY_HOLD_MAX_SEC (neoaprs/mercury.py), so the
held seconds of a period are the smaller of its length and that cap.
"""
import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from neoaprs.mercury import BUSY_HOLD_MAX_SEC

# The first spectra of a Mercury are not read (see `replay`).
WARM_UP_SEC = 1.0
# A busy period beginning up to this long after a frame's PTT OFF still counts as seeing it.
SEEN_AFTER_SEC = 0.5
# A detector may be busy this long after PTT OFF (hang and tail) without it being false.
CLEAR_AFTER_SEC = 2.5


class Detector(Protocol):
    @property
    def busy(self) -> bool: ...

    def update(self, now: float, bands: Sequence[float]) -> bool: ...


@dataclass
class Recording:
    scene: str                                            # what the receiver heard, in words
    # (when, the bands in dB), on the measurement's clock.
    spectra: list[tuple[float, list[float]]] = field(default_factory=list)
    # (PTT ON, PTT OFF, SNR in 3 kHz) of the transmitted frames.
    frames: list[tuple[float, float, float]] = field(default_factory=list)
    # (when, on) of Mercury's own BUSY lines at the threshold NeoAPRS writes.
    mercury: list[tuple[float, bool]] = field(default_factory=list)
    # The part with frames, and the quiet part after it with none
    frames_span: tuple[float, float] = (0.0, 0.0)
    quiet_span: tuple[float, float] = (0.0, 0.0)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self)), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Recording":
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return cls(data["scene"], [(t, b) for t, b in data["spectra"]], [(a, b, c) for a, b, c in data["frames"]], [(t, on) for t, on in data["mercury"]],
                   (data["frames_span"][0], data["frames_span"][1]), (data["quiet_span"][0], data["quiet_span"][1]))


Period = tuple[float, float]


def replay(make: Callable[[], Detector], recording: Recording) -> list[Period]:
    """The busy periods (from, to) a fresh detector makes over the spectra, skipping the first
    WARM_UP_SEC.

    The spectrum of a Mercury that has just begun to listen fills up from zeros and rises 25 dB in
    the first 0.2 s. A period still open at the end is closed at the last spectrum.
    """
    detector = make()
    periods: list[Period] = []
    since: float | None = None
    last = 0.0
    first = recording.spectra[0][0] if recording.spectra else 0.0
    for when, bands in recording.spectra:
        if when < first + WARM_UP_SEC:
            continue
        busy = detector.update(when, bands)
        last = when
        if busy and since is None:
            since = when
        elif not busy and since is not None:
            periods.append((since, when))
            since = None
    if since is not None:
        periods.append((since, last))
    return periods


def periods_of(events: Sequence[tuple[float, bool]], end: float) -> list[Period]:
    """The busy periods of a series of BUSY ON / OFF lines, closed at `end` when the last one is ON.
    """
    periods: list[Period] = []
    since: float | None = None
    for when, on in events:
        if on and since is None:
            since = when
        elif not on and since is not None:
            periods.append((since, when))
            since = None
    if since is not None:
        periods.append((since, end))
    return periods


def overlap(a: Period, b: Period) -> float:
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


@dataclass
class Score:
    # By SNR: (frames seen, frames sent).
    seen: dict[float, tuple[int, int]]
    # Mean time from a frame's PTT ON to the start of the busy period that saw it.
    lag_sec: float | None
    # Mean time the detector stays busy after a frame's PTT OFF.
    hang_sec: float | None
    # Busy seconds in the part with frames, away from the frames.
    false_frames_sec: float
    false_quiet_sec: float                                 # busy seconds in the quiet part
    # Seconds of the quiet part the radio would be held (each period at most BUSY_HOLD_MAX_SEC).
    held_quiet_sec: float
    # The longest busy period of the quiet part.
    longest_quiet_sec: float


def score(periods: Sequence[Period], recording: Recording) -> Score:
    seen: dict[float, list[int]] = {}
    lags: list[float] = []
    hangs: list[float] = []
    clear: list[Period] = []
    for on, off, snr in recording.frames:
        mine = [p for p in periods if p[1] >= on and p[0] <= off + SEEN_AFTER_SEC]
        found = seen.setdefault(snr, [0, 0])
        found[1] += 1
        if mine:
            found[0] += 1
            lags.append(max(0.0, mine[0][0] - on))
            hangs.append(max(0.0, mine[-1][1] - off))
        clear.append((on, off + CLEAR_AFTER_SEC))
    frames_start, frames_end = recording.frames_span
    quiet = recording.quiet_span
    false_frames = sum(overlap(p, (frames_start, frames_end)) for p in periods) - sum(overlap(p, c) for p in periods for c in clear)
    in_quiet = [(max(p[0], quiet[0]), min(p[1], quiet[1])) for p in periods if overlap(p, quiet) > 0]
    return Score({snr: (n[0], n[1]) for snr, n in sorted(seen.items())}, sum(lags) / len(lags) if lags else None, sum(hangs) / len(hangs) if hangs else None,
                 max(0.0, false_frames), sum(b - a for a, b in in_quiet), sum(min(b - a, BUSY_HOLD_MAX_SEC) for a, b in in_quiet), max((b - a for a, b in in_quiet), default=0.0))
