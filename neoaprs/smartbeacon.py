"""SmartBeaconing: when a moving station sends its position.

The algorithm is HamHUD's SmartBeaconing, by Tony Arnerich KD7TA and Steve Bragg KA9MVA, as Dire Wolf and APRSdroid implement it, with the speeds in kilometres per hour. It has two parts.

The rate. A station that stands still (at or below `slow_kmh`) beacons every `slow_sec`, one that goes fast (at or above `fast_kmh`) every `fast_sec`, and between the two the time falls with the
speed: `fast_sec * fast_kmh / speed` seconds, so a station at half the fast speed beacons at half the fast rate.

Corner pegging. Above `slow_kmh` a turn is beaconed at once: when the course differs from the course of the last beacon by more than `turn_min_deg + turn_slope / speed_in_mph` degrees (a fast
vehicle turns a little to follow a bend, a slow one a lot to be heard to turn; the slope is in the original's degrees times miles per hour) and at least `turn_min_sec` have passed since that beacon.

The first fix after the start is beaconed at once (`start`), and a beacon asked for (the page's Beacon now) is `request`. The module is pure: it decides, it sends nothing."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from neoaprs.units import MILE_KM

Reason = Literal["start", "time", "turn", "request"]


@dataclass(frozen=True)
class SmartSettings:
    """The seven numbers of the algorithm. The operator chooses a preset (`PRESETS`), not the numbers."""
    fast_kmh: float = 100.0
    fast_sec: float = 60.0
    slow_kmh: float = 8.0
    slow_sec: float = 1800.0
    turn_min_deg: float = 30.0
    turn_min_sec: float = 15.0
    turn_slope: float = 255.0


TRAVEL = ("car", "bicycle", "foot", "boat")                 # how the station travels (the setting `beacon/travel`); the first is the default
PRESETS: dict[str, SmartSettings] = {                          # the car is Dire Wolf's default SmartBeaconing; the others are NeoAPRS's own choice for a slower way of moving
    "car": SmartSettings(fast_kmh=100, fast_sec=60, slow_kmh=8, slow_sec=1800, turn_min_deg=30, turn_min_sec=15, turn_slope=255),
    "bicycle": SmartSettings(fast_kmh=30, fast_sec=60, slow_kmh=4, slow_sec=1800, turn_min_deg=35, turn_min_sec=20, turn_slope=255),
    "foot": SmartSettings(fast_kmh=7, fast_sec=120, slow_kmh=1.5, slow_sec=1800, turn_min_deg=45, turn_min_sec=60, turn_slope=100),
    "boat": SmartSettings(fast_kmh=40, fast_sec=60, slow_kmh=3, slow_sec=1800, turn_min_deg=20, turn_min_sec=30, turn_slope=255),
}


@dataclass(frozen=True)
class Sent:
    """The last beacon: when it went out and the course the station had then (None when it had none)."""
    at: datetime
    course_deg: int | None


@dataclass(frozen=True)
class Decision:
    """Whether to beacon now and why (None: not now), and when the next beacon by time is due at the speed there is now (None before the first beacon)."""
    reason: Reason | None
    next_due: datetime | None


def rate_sec(settings: SmartSettings, speed_kmh: float) -> float:
    """Seconds between two beacons at this speed: `slow_sec` up to `slow_kmh`, `fast_sec` from `fast_kmh`, `fast_sec * fast_kmh / speed` between."""
    if speed_kmh <= settings.slow_kmh:
        return settings.slow_sec
    if speed_kmh >= settings.fast_kmh:
        return settings.fast_sec
    return settings.fast_sec * settings.fast_kmh / speed_kmh


def turn_threshold_deg(settings: SmartSettings, speed_kmh: float) -> float:
    """The change of course in degrees that is a turn at this speed (above `slow_kmh`; the speed is never 0 there)."""
    return settings.turn_min_deg + settings.turn_slope / (speed_kmh / MILE_KM)


def heading_change_deg(now_deg: int, then_deg: int) -> int:
    """The smaller angle between two courses, 0 to 180."""
    difference = abs(now_deg - then_deg) % 360
    return min(difference, 360 - difference)


def decide(settings: SmartSettings, last: Sent | None, now: datetime, speed_kmh: float | None, course_deg: int | None, request: bool = False) -> Decision:
    """The decision for a fix at `now` with this speed and course (None: the receiver gave none; no speed counts as standing still, no course as no turn), given the last beacon (None: there has been none).

    A request wins, then the start, then the time (the interval of the speed has passed since the last beacon), then a turn."""
    speed = speed_kmh or 0.0
    if last is None:
        return Decision("request" if request else "start", None)
    due = last.at + timedelta(seconds=rate_sec(settings, speed))
    if request:
        return Decision("request", due)
    if now >= due:
        return Decision("time", due)
    if speed > settings.slow_kmh and _turned(settings, last, now, speed, course_deg):
        return Decision("turn", due)
    return Decision(None, due)


def _turned(settings: SmartSettings, last: Sent, now: datetime, speed_kmh: float, course_deg: int | None) -> bool:
    """Corner pegging: the course changed by more than the threshold of this speed, and the least time since the last beacon has passed."""
    if course_deg is None or last.course_deg is None:
        return False
    if (now - last.at).total_seconds() < settings.turn_min_sec:
        return False
    return heading_change_deg(course_deg, last.course_deg) > turn_threshold_deg(settings, speed_kmh)
