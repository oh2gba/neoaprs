"""Where a satellite is and how it is seen from the station: SGP4 positions, look angles, passes, Doppler.

Pure functions of an orbit and a time; the elements are OMM fields (CelesTrak's CSV columns). TEME is
turned to the earth's frame by GMST alone (IAU 1982), far inside what the elements' own age allows."""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sgp4.api import WGS72, Satrec, jday

WGS84_A_KM = 6378.137
WGS84_F = 1 / 298.257223563
WGS84_E2 = WGS84_F * (2 - WGS84_F)
MEAN_RADIUS_KM = 6371.0088
EARTH_TURN_RAD_SEC = 7.292115e-5  # the earth's rotation, rad/s
LIGHT_KM_SEC = 299792.458
LISTED_DEG = 10.0  # a pass whose highest point is lower is not listed
STEP_SEC = 30.0  # the scan for passes; a pass that reaches LISTED_DEG lasts minutes
SEARCH_HOURS = 24.0
LOOK_BACK_SEC = 30 * 60.0  # how far before now a pass in progress may have begun
REFINE_SEC = 1.0
OMM_NUMBERS = (
    "ECCENTRICITY",
    "INCLINATION",
    "RA_OF_ASC_NODE",
    "ARG_OF_PERICENTER",
    "MEAN_ANOMALY",
    "BSTAR",
    "MEAN_MOTION_DOT",
    "MEAN_MOTION_DDOT",
)
OMM_FIELDS = ("EPOCH", "MEAN_MOTION", "NORAD_CAT_ID", *OMM_NUMBERS)
SGP4_EPOCH = datetime(1949, 12, 31, tzinfo=UTC)  # day 0 of SGP4's epoch
MAX_NUMBER = 340000  # the largest catalogue number SGP4 takes (Alpha-5)

Vector = tuple[float, float, float]


@dataclass(frozen=True)
class Orbit:
    id: int
    satrec: Satrec
    epoch: datetime
    mean_motion: float  # revolutions a day

    @property
    def period_sec(self) -> float:
        return 86400.0 / self.mean_motion


@dataclass(frozen=True)
class Station:
    lat: float
    lon: float
    alt_m: float = 0.0


@dataclass(frozen=True)
class SubPoint:
    lat: float
    lon: float
    alt_km: float


@dataclass(frozen=True)
class Look:
    az_deg: float
    el_deg: float
    range_km: float
    rate_km_sec: float  # above zero while the distance grows


@dataclass(frozen=True)
class Pass:
    rise: datetime
    set: datetime
    max_at: datetime
    max_el_deg: float
    rise_az_deg: float
    set_az_deg: float
    rise_rate_km_sec: float
    max_rate_km_sec: float
    set_rate_km_sec: float


def _epoch(text: str) -> datetime | None:
    try:
        when = datetime.fromisoformat(text.strip().removesuffix("Z"))
    except ValueError:
        return None
    return when.replace(tzinfo=UTC) if when.tzinfo is None else when.astimezone(UTC)


def orbit_of(fields: Mapping[str, object]) -> Orbit | None:
    """Return the orbit of one OMM record (values as CelesTrak's CSV gives them); None if it is not one."""
    texts = {name: str(fields.get(name, "")).strip() for name in OMM_FIELDS}
    epoch = _epoch(texts["EPOCH"])
    try:
        mean_motion = float(texts["MEAN_MOTION"])
        number = int(texts["NORAD_CAT_ID"])
        values = [float(texts[name]) for name in OMM_NUMBERS]
    except ValueError:
        return None
    if (
        epoch is None
        or not 0.5 < mean_motion < 20
        or not 0 < number < MAX_NUMBER
        or not all(map(math.isfinite, values))
    ):
        return None
    ecc, inc, node, perigee, anomaly, bstar, ndot, nddot = values
    satrec = Satrec()
    days = (epoch - SGP4_EPOCH).total_seconds() / 86400.0
    rad = math.pi / 180
    # (the units of the mean motion's derivatives as SGP4.cpp takes them)
    satrec.sgp4init(
        WGS72, "i", number, days, bstar, ndot / (1036800.0 / math.pi), nddot / (2985984000.0 / 2.0 / math.pi),
        ecc, perigee * rad, inc * rad, anomaly * rad, mean_motion / 720.0 * math.pi, node * rad,
    )  # fmt: skip
    if satrec.error != 0 or not 0 <= ecc < 1:
        return None
    return Orbit(number, satrec, epoch, mean_motion)


def _julian(t: datetime) -> tuple[float, float]:
    t = t.astimezone(UTC)
    jd, fr = jday(t.year, t.month, t.day, t.hour, t.minute, t.second + t.microsecond / 1e6)
    return jd, fr


def gmst_rad(t: datetime) -> float:
    """Greenwich mean sidereal time (IAU 1982), radians."""
    jd, fr = _julian(t)
    tut1 = (jd + fr - 2451545.0) / 36525.0
    sec = -6.2e-6 * tut1**3 + 0.093104 * tut1**2 + (876600.0 * 3600 + 8640184.812866) * tut1 + 67310.54841
    return math.radians(sec / 240.0) % (2 * math.pi)


def _teme(orbit: Orbit, t: datetime) -> tuple[Vector, Vector] | None:
    error, r, v = orbit.satrec.sgp4(*_julian(t))
    return None if error != 0 else ((r[0], r[1], r[2]), (v[0], v[1], v[2]))


def _to_earth(r: Vector, v: Vector, t: datetime) -> tuple[Vector, Vector]:
    """TEME position and velocity to the earth's frame, the velocity relative to the turning earth."""
    g = gmst_rad(t)
    c, s = math.cos(g), math.sin(g)
    x, y, z = c * r[0] + s * r[1], -s * r[0] + c * r[1], r[2]
    vx = c * v[0] + s * v[1] + EARTH_TURN_RAD_SEC * y
    vy = -s * v[0] + c * v[1] - EARTH_TURN_RAD_SEC * x
    return (x, y, z), (vx, vy, v[2])


def _station_xyz(station: Station) -> Vector:
    lat, lon = math.radians(station.lat), math.radians(station.lon)
    n = WGS84_A_KM / math.sqrt(1 - WGS84_E2 * math.sin(lat) ** 2)
    h = station.alt_m / 1000.0
    return (
        (n + h) * math.cos(lat) * math.cos(lon),
        (n + h) * math.cos(lat) * math.sin(lon),
        (n * (1 - WGS84_E2) + h) * math.sin(lat),
    )


def _geodetic(r: Vector) -> SubPoint:
    x, y, z = r
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1 - WGS84_E2))
    for _ in range(5):
        n = WGS84_A_KM / math.sqrt(1 - WGS84_E2 * math.sin(lat) ** 2)
        lat = math.atan2(z + WGS84_E2 * n * math.sin(lat), p)
    n = WGS84_A_KM / math.sqrt(1 - WGS84_E2 * math.sin(lat) ** 2)
    alt = p / math.cos(lat) - n if abs(lat) < math.radians(89) else z / math.sin(lat) - n * (1 - WGS84_E2)
    return SubPoint(math.degrees(lat), math.degrees(math.atan2(y, x)), alt)


def sub_point(orbit: Orbit, t: datetime) -> SubPoint | None:
    """Return the point on the ground under the satellite and its height; None if SGP4 fails there."""
    teme = _teme(orbit, t)
    return None if teme is None else _geodetic(_to_earth(*teme, t)[0])


def look(orbit: Orbit, station: Station, t: datetime) -> Look | None:
    """Return the azimuth, elevation, distance and range rate from the station; None if SGP4 fails."""
    teme = _teme(orbit, t)
    if teme is None:
        return None
    r, v = _to_earth(*teme, t)
    s = _station_xyz(station)
    d = (r[0] - s[0], r[1] - s[1], r[2] - s[2])
    distance = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2)
    lat, lon = math.radians(station.lat), math.radians(station.lon)
    east = -math.sin(lon) * d[0] + math.cos(lon) * d[1]
    north = -math.sin(lat) * math.cos(lon) * d[0] - math.sin(lat) * math.sin(lon) * d[1] + math.cos(lat) * d[2]
    up = math.cos(lat) * math.cos(lon) * d[0] + math.cos(lat) * math.sin(lon) * d[1] + math.sin(lat) * d[2]
    rate = (d[0] * v[0] + d[1] * v[1] + d[2] * v[2]) / distance
    return Look(math.degrees(math.atan2(east, north)) % 360.0, math.degrees(math.asin(up / distance)), distance, rate)


def footprint_km(alt_km: float, lowest_deg: float = 0.0) -> float:
    """Return the ground radius of the circle from which the satellite stands above `lowest_deg`."""
    e0 = math.radians(lowest_deg)
    ratio = MEAN_RADIUS_KM / (MEAN_RADIUS_KM + max(0.0, alt_km)) * math.cos(e0)
    return MEAN_RADIUS_KM * (math.acos(min(1.0, ratio)) - e0)


def downlink_shift_hz(f_hz: float, rate_km_sec: float) -> float:
    """Return how far from `f_hz` the station hears it: below while the satellite goes away."""
    return -f_hz * rate_km_sec / LIGHT_KM_SEC


def uplink_shift_hz(f_hz: float, rate_km_sec: float) -> float:
    """Return how far from `f_hz` to send so that the satellite hears `f_hz`."""
    return f_hz / (1 - rate_km_sec / LIGHT_KM_SEC) - f_hz


def track(orbit: Orbit, start: datetime, sec: float, step_sec: float) -> list[tuple[datetime, SubPoint]]:
    """Return the sub-points from `start` for `sec` seconds, every `step_sec`; a point SGP4 fails at is left out."""
    found = []
    for n in range(int(sec // step_sec) + 1):
        t = start + timedelta(seconds=n * step_sec)
        point = sub_point(orbit, t)
        if point is not None:
            found.append((t, point))
    return found


def _elevation(orbit: Orbit, station: Station, t: datetime) -> float:
    seen = look(orbit, station, t)
    return -90.0 if seen is None else seen.el_deg


def _crossing(orbit: Orbit, station: Station, low: datetime, high: datetime) -> datetime:
    """The instant to REFINE_SEC where the elevation crosses 0 between two times on either side."""
    below = _elevation(orbit, station, low) < 0
    while (high - low).total_seconds() > REFINE_SEC:
        mid = low + (high - low) / 2
        if (_elevation(orbit, station, mid) < 0) == below:
            low = mid
        else:
            high = mid
    return low + (high - low) / 2


def _highest(orbit: Orbit, station: Station, low: datetime, high: datetime) -> datetime:
    """The instant of the greatest elevation between rise and set (golden section to REFINE_SEC)."""
    k = (math.sqrt(5) - 1) / 2
    a, b = low, high
    c, d = b - (b - a) * k, a + (b - a) * k
    while (b - a).total_seconds() > REFINE_SEC:
        if _elevation(orbit, station, c) > _elevation(orbit, station, d):
            b, d = d, c
            c = b - (b - a) * k
        else:
            a, c = c, d
            d = a + (b - a) * k
    return a + (b - a) / 2


def _pass(orbit: Orbit, station: Station, rise: datetime, set_: datetime) -> Pass | None:
    top = _highest(orbit, station, rise, set_)
    at_rise, at_top, at_set = (look(orbit, station, t) for t in (rise, top, set_))
    if at_rise is None or at_top is None or at_set is None:
        return None
    return Pass(
        rise,
        set_,
        top,
        at_top.el_deg,
        at_rise.az_deg,
        at_set.az_deg,
        at_rise.rate_km_sec,
        at_top.rate_km_sec,
        at_set.rate_km_sec,
    )


def passes(
    orbit: Orbit, station: Station, now: datetime, hours: float = SEARCH_HOURS, lowest_deg: float = LISTED_DEG
) -> list[Pass]:
    """Return the passes that have not set by `now` and begin within `hours`, highest point at least `lowest_deg`.

    A pass under way at `now` comes first, its rise in the past."""
    start = now - timedelta(seconds=LOOK_BACK_SEC)
    steps = int((hours * 3600 + LOOK_BACK_SEC) // STEP_SEC)
    found: list[Pass] = []
    t, up = start, _elevation(orbit, station, start) >= 0
    rise = start if up else None
    for n in range(1, steps + 1):
        nxt = start + timedelta(seconds=n * STEP_SEC)
        now_up = _elevation(orbit, station, nxt) >= 0
        if now_up and not up:
            rise = _crossing(orbit, station, t, nxt)
        elif up and not now_up and rise is not None:
            set_ = _crossing(orbit, station, t, nxt)
            made = _pass(orbit, station, rise, set_) if set_ > now else None
            if made is not None and made.max_el_deg >= lowest_deg:
                found.append(made)
            rise = None
        t, up = nxt, now_up
    return found
