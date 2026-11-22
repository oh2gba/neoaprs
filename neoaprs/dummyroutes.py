"""Where the Dummy radio's moving stations (dummyscene.py) go.

A route is a few corners in km east and north of the station, walked at a steady speed round and
round, or there and back, within about six kilometres of the centre.
"""

import math
from dataclasses import dataclass

MAX_LAT = 89.9
# a degree of latitude; longitude is this times the cosine of the latitude
KM_PER_DEGREE = 111.32


@dataclass(frozen=True)
class Route:
    corners: tuple[tuple[float, float], ...]  # (km east, km north) of the centre
    # True: from the last corner back to the first; False: there and back
    loop: bool

    def _legs(self) -> list[tuple[tuple[float, float], tuple[float, float], float]]:
        ring = self.corners + ((self.corners[0],) if self.loop else ())
        return [(a, b, math.dist(a, b)) for a, b in zip(ring, ring[1:])]

    @property
    def length_km(self) -> float:
        """Return the length of one round, or one way."""
        return sum(leg for _, _, leg in self._legs())

    def at(self, km: float) -> tuple[float, float, int]:
        """Return (km east, km north, course in degrees) at `km` along the route."""
        length = self.length_km
        along = km % length if self.loop else km % (2 * length)
        back = not self.loop and along > length
        along = 2 * length - along if back else along
        for a, b, leg in self._legs():
            if along <= leg or (a, b, leg) == self._legs()[-1]:
                f = min(1.0, along / leg)
                course = math.degrees(math.atan2(b[0] - a[0], b[1] - a[1])) % 360
                return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, round((course + (180 if back else 0)) % 360)
            along -= leg
        raise AssertionError("unreachable")


def around(centre: tuple[float, float], east_km: float, north_km: float) -> tuple[float, float]:
    """Return the latitude and longitude of the place `east_km`, `north_km` from `centre`."""
    lat, lon = centre
    new_lat = max(-MAX_LAT, min(MAX_LAT, lat + north_km / KM_PER_DEGREE))
    new_lon = lon + east_km / (KM_PER_DEGREE * math.cos(math.radians(max(-MAX_LAT, min(MAX_LAT, lat)))))
    return new_lat, (new_lon + 180) % 360 - 180


# a ring of main streets, about 22 km
TOWN_LOOP = Route(((-3.0, -2.0), (-3.2, 1.5), (-1.0, 3.0), (2.5, 3.2), (4.0, 0.8), (3.2, -2.4), (0.0, -3.0)), loop=True)
# a wider round
DELIVERY_ROUND = Route(
    ((-5.0, -1.0), (-1.5, -2.2), (2.0, -1.2), (5.5, 1.5), (3.0, 4.2), (-1.0, 3.6), (-4.2, 2.8)), loop=True
)
# out along the ring road and back
RING_ROAD = Route(((-5.5, -3.5), (-2.0, -4.0), (2.0, -3.6), (5.0, -1.0)), loop=False)
# round a park, about a kilometre
PARK_PATH = Route(((1.2, 0.8), (1.6, 1.1), (1.9, 0.7), (1.6, 0.3)), loop=True)
