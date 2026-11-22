"""Distance and bearing on the earth, the box round a circle, and a track thinned for replay.

Positions are degrees, north and east positive. The earth is a sphere of the mean radius."""

import math
from collections.abc import Sequence
from datetime import datetime

EARTH_RADIUS_KM = 6371.0088


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the initial bearing from the first position to the second, 0 up to 360; 0 if equal."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    bearing = math.degrees(math.atan2(y, x)) % 360.0
    return 0.0 if bearing >= 360.0 else bearing


KM_PER_DEGREE = 111.195  # a degree of latitude on the sphere of EARTH_RADIUS_KM
MAX_MERCATOR_LAT = 85.0511  # the map's tiles end here


def box_around(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    """Return the box west, south, east, north (degrees) holding the circle round the position.

    A square on the ground; it stops at the edges of the world map and is not wrapped over them.
    """
    lat = max(-MAX_MERCATOR_LAT, min(MAX_MERCATOR_LAT, lat))
    dlat = radius_km / KM_PER_DEGREE
    south, north = max(-MAX_MERCATOR_LAT, lat - dlat), min(MAX_MERCATOR_LAT, lat + dlat)
    widest = max(abs(south), abs(north))
    scale = math.cos(math.radians(widest))
    dlon = 180.0 if scale < 1e-6 else min(180.0, radius_km / (KM_PER_DEGREE * scale))
    return max(-180.0, lon - dlon), south, min(180.0, lon + dlon), north


Point = tuple[datetime, float, float]


class Thinning:
    """A track thinned as points come: one near the last kept (`metres`, `seconds`) is left out.

    The last point and the one just before a move are kept, so a replay waits at a stop.
    """

    def __init__(self, metres: float, seconds: float) -> None:
        self.metres = metres
        self.seconds = seconds
        self._kept: list[Point] = []
        self._left: Point | None = None  # the latest point left out since the last one kept

    def add(self, point: Point) -> None:
        if self._kept:
            at, lat, lon = self._kept[-1]
            gone = (point[0] - at).total_seconds()
            if gone < self.seconds or distance_km(lat, lon, point[1], point[2]) * 1000 < self.metres:
                self._left = point
                return
            still = self._left
            if still is not None and (still[0] - at).total_seconds() >= self.seconds:
                self._kept.append(still)
        self._kept.append(point)
        self._left = None

    def points(self) -> list[Point]:
        return self._kept if self._left is None else [*self._kept, self._left]


def thinned(track: Sequence[Point], metres: float, seconds: float) -> list[Point]:
    """Return the points of a track (when, lat, lon; oldest first) a replay needs (Thinning)."""
    thinning = Thinning(metres, seconds)
    for point in track:
        thinning.add(point)
    return thinning.points()
