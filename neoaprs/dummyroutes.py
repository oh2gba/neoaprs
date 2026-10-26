"""Where the moving stations of the Dummy radio (dummyscene.py) go: a route is a few corners in kilometres east and north of the station, walked at a steady speed round and round, or there and back. The corners are
plausible streets for a town the size of Helsinki and keep every moving station within about six kilometres of the centre."""
import math
from dataclasses import dataclass

KM_PER_DEGREE = 111.32                # a degree of latitude; a degree of longitude is this times the cosine of the latitude


@dataclass(frozen=True)
class Route:
    corners: tuple[tuple[float, float], ...]       # (km east, km north) of the centre
    loop: bool                                     # True: from the last corner back to the first and on; False: there and back

    def _legs(self) -> list[tuple[tuple[float, float], tuple[float, float], float]]:
        ring = self.corners + ((self.corners[0],) if self.loop else ())
        return [(a, b, math.dist(a, b)) for a, b in zip(ring, ring[1:])]

    @property
    def length_km(self) -> float:
        """One round, or one way."""
        return sum(leg for _, _, leg in self._legs())

    def at(self, km: float) -> tuple[float, float, int]:
        """(km east, km north, course in degrees) of the place `km` along the route; past the end it goes round again, or back."""
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
    """The latitude and longitude of the place `east_km` and `north_km` from `centre`."""
    lat, lon = centre
    return lat + north_km / KM_PER_DEGREE, lon + east_km / (KM_PER_DEGREE * math.cos(math.radians(lat)))


TOWN_LOOP = Route(((-3.0, -2.0), (-3.2, 1.5), (-1.0, 3.0), (2.5, 3.2), (4.0, 0.8), (3.2, -2.4), (0.0, -3.0)), loop=True)               # a ring of main streets, about 22 km
DELIVERY_ROUND = Route(((-5.0, -1.0), (-1.5, -2.2), (2.0, -1.2), (5.5, 1.5), (3.0, 4.2), (-1.0, 3.6), (-4.2, 2.8)), loop=True)         # a wider round
RING_ROAD = Route(((-5.5, -3.5), (-2.0, -4.0), (2.0, -3.6), (5.0, -1.0)), loop=False)                                               # out along the ring road and back
PARK_PATH = Route(((1.2, 0.8), (1.6, 1.1), (1.9, 0.7), (1.6, 0.3)), loop=True)                                                      # round a park, about a kilometre
