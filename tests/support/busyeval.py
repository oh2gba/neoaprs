"""Busy detectors held against each other on the same recorded spectra (scripts/mercury-measure autobusy): a `Recording` is what one receiver saw in one scene, the bands of every spectrum with the time it came, the frames
that were on the air (when they began and ended, and at what signal-to-noise ratio), the BUSY lines the real Mercury said on its control port, and when the quiet part began and ended; `replay` runs a detector over the bands;
`score` says what it did: which frames it saw, how soon, how long it held after them, and how many seconds it was busy when nothing was on the air. The numbers are those of docs/mercury.md.

Seeing a frame is a busy period that touches the time the frame was on the air (from its PTT ON to half a second after its PTT OFF). Holding is what the radio would do: a BUSY holds our frames for at most the cap
(neoaprs/mercury.py BUSY_HOLD_MAX_SEC) from its beginning, so the held seconds of a period are the smaller of its length and the cap."""
import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from neoaprs.mercury import BUSY_HOLD_MAX_SEC

WARM_UP_SEC = 1.0                        # the first spectra of a Mercury are not read (see `replay`)
SEEN_AFTER_SEC = 0.5                     # a busy period that begins up to this long after the frame's PTT OFF still counts as seeing it
CLEAR_AFTER_SEC = 2.5                    # after a frame's PTT OFF this long a detector may still be busy (the hang and the tail) without it being false


class Detector(Protocol):
    @property
    def busy(self) -> bool: ...

    def update(self, now: float, bands: Sequence[float]) -> bool: ...


@dataclass
class Recording:
    scene: str                                            # what the receiver heard, in words
    spectra: list[tuple[float, list[float]]] = field(default_factory=list)       # (when, the bands in dB), the time on the clock of the measurement
    frames: list[tuple[float, float, float]] = field(default_factory=list)       # (PTT ON, PTT OFF, SNR in 3 kHz) of the frames the transmitter sent
    mercury: list[tuple[float, bool]] = field(default_factory=list)              # (when, on) of the BUSY lines of Mercury's own detector, at the threshold NeoAPRS writes
    frames_span: tuple[float, float] = (0.0, 0.0)           # the part with frames, and the quiet part after it with none
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
    """The busy periods (from, to) a fresh detector makes over the recording's spectra, without the first WARM_UP_SEC of them (the spectrum of a Mercury that has just begun to listen is a window that fills up from zeros: it
    rises 25 dB in the first 0.2 s, and a floor that was taken from it is not one); a period still open at the end is closed at the last spectrum."""
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
    """The busy periods of a series of BUSY ON / BUSY OFF lines (closed at `end` when the last one is ON)."""
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
    seen: dict[float, tuple[int, int]]                     # by SNR: (frames seen, frames sent)
    lag_sec: float | None                                  # the mean time from a frame's PTT ON to the beginning of the busy period that saw it (0 when it was busy already)
    hang_sec: float | None                                 # the mean time the detector stays busy after a frame's PTT OFF
    false_frames_sec: float                                # busy seconds in the part with frames, away from the frames
    false_quiet_sec: float                                 # busy seconds in the quiet part
    held_quiet_sec: float                                  # the seconds of the quiet part the radio would be held (each period at most BUSY_HOLD_MAX_SEC)
    longest_quiet_sec: float                               # the longest busy period of the quiet part


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
