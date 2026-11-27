"""What the satellites layer tells the pages: a mark per satellite with points to move it by, and the
card of each satellite a page has open (the next pass, the frequencies to tune, the Doppler shift now).

Pure functions of the satellites, the station and the time."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from .satellitelist import Mode, Satellite
from .satellites import Orbit, Pass, Station, downlink_shift_hz, footprint_km, look, sub_point, track, uplink_shift_hz

MARK_BACK_SEC = 30.0
MARK_AHEAD_SEC = 300.0  # longer than ROUND_SEC of the service, so a page never runs out of points
MARK_STEP_SEC = 30.0
TRACK_STEP_SEC = 60.0
LOOK_STEP_SEC = 5.0
LOOK_AHEAD_SEC = 90.0

TimedPoint = tuple[datetime, float, float]


@dataclass(frozen=True)
class Mark:
    id: int
    name: str
    points: tuple[TimedPoint, ...]


@dataclass(frozen=True)
class Tune:
    """A frequency of the list and what to tune it to at the next pass's rise, highest point and set."""

    hz: int
    rise_hz: int | None
    max_hz: int | None
    set_hz: int | None


@dataclass(frozen=True)
class LookNow:
    at: datetime
    el_deg: float
    down_hz: tuple[int, ...]  # the shift heard on each downlink
    up_hz: tuple[int, ...]  # the offset to send on each uplink


@dataclass(frozen=True)
class Card:
    id: int
    name: str
    downlinks: tuple[Tune, ...]
    uplinks: tuple[Tune, ...]
    mode: Mode | None
    path: str
    alt_km: float
    footprint_km: float
    track: tuple[TimedPoint, ...]
    next_pass: Pass | None
    looks: tuple[LookNow, ...]  # while it is up: samples to tell the elevation and Doppler now by


@dataclass(frozen=True)
class View:
    at: datetime
    elements_at: datetime | None
    marks: tuple[Mark, ...]
    cards: tuple[Card, ...]


def _points(orbit: Orbit, start: datetime, sec: float, step_sec: float) -> tuple[TimedPoint, ...]:
    return tuple((t, round(p.lat, 4), round(p.lon, 4)) for t, p in track(orbit, start, sec, step_sec))


def mark(satellite: Satellite, orbit: Orbit, now: datetime) -> Mark | None:
    points = _points(orbit, now - timedelta(seconds=MARK_BACK_SEC), MARK_BACK_SEC + MARK_AHEAD_SEC, MARK_STEP_SEC)
    return Mark(satellite.id, satellite.name, points) if points else None


def next_pass(found: Sequence[Pass], now: datetime) -> Pass | None:
    """The pass under way, else the next one; None if none is listed."""
    return next((one for one in found if one.set > now), None)


def _tunes(hzs: Sequence[int], up: bool, seen: Pass | None) -> tuple[Tune, ...]:
    shift = uplink_shift_hz if up else downlink_shift_hz

    def at(hz: int, rate: float | None) -> int | None:
        return None if rate is None else round(hz + shift(hz, rate))

    rates = (None, None, None) if seen is None else (seen.rise_rate_km_sec, seen.max_rate_km_sec, seen.set_rate_km_sec)
    return tuple(Tune(hz, at(hz, rates[0]), at(hz, rates[1]), at(hz, rates[2])) for hz in hzs)


def _looks(satellite: Satellite, orbit: Orbit, station: Station, seen: Pass, now: datetime) -> tuple[LookNow, ...]:
    if not seen.rise <= now < seen.set:
        return ()
    found = []
    for n in range(int(LOOK_AHEAD_SEC // LOOK_STEP_SEC) + 1):
        t = now + timedelta(seconds=n * LOOK_STEP_SEC)
        seen_then = look(orbit, station, t)
        if seen_then is None or t > seen.set + timedelta(seconds=LOOK_STEP_SEC):
            break
        rate = seen_then.rate_km_sec
        found.append(
            LookNow(
                t,
                round(seen_then.el_deg, 2),
                tuple(round(downlink_shift_hz(hz, rate)) for hz in satellite.downlinks_hz),
                tuple(round(uplink_shift_hz(hz, rate)) for hz in satellite.uplinks_hz),
            )
        )
    return tuple(found)


def card(
    satellite: Satellite, orbit: Orbit, station: Station | None, now: datetime, found: Sequence[Pass]
) -> Card | None:
    """The card of a satellite; without a station it has no pass and no Doppler. None if SGP4 fails now."""
    here = sub_point(orbit, now)
    if here is None:
        return None
    seen = next_pass(found, now) if station is not None else None
    return Card(
        satellite.id,
        satellite.name,
        _tunes(satellite.downlinks_hz, False, seen),
        _tunes(satellite.uplinks_hz, True, seen),
        satellite.mode,
        satellite.path,
        round(here.alt_km, 1),
        round(footprint_km(here.alt_km), 1),
        _points(orbit, now, orbit.period_sec, TRACK_STEP_SEC),
        seen,
        () if seen is None or station is None else _looks(satellite, orbit, station, seen, now),
    )
