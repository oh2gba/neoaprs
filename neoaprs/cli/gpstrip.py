"""A synthetic drive for `neoaprs gps-replay`: a loop of straight legs and corners with a stop in the middle, one position a second, the way a car drives it.

The car starts standing still, accelerates to its cruising speed, slows for each corner (to `CORNER_MS`), turns, accelerates again, and on the last leg stops for `STOP_SEC` seconds half way along it. The loop is a rectangle, 1200 m north, 800 m
east, 1200 m south and 800 m west, driven again and again. The geometry is flat (metres east and north of the start, turned into degrees), which is good for the few kilometres of a lap.
Pure code: `Trip.step()` moves the car one second on and says where it is."""
import math
from dataclasses import dataclass

METRES_PER_DEGREE = 111194.9            # a degree of latitude
ACCEL_MS2 = 1.5                         # how fast the car speeds up
DECEL_MS2 = 2.0                         # and slows down
CORNER_MS = 8.0                         # the speed it takes a corner at (29 km/h)
TURN_DEG_PER_SEC = 45.0                 # how fast it turns
STOP_SEC = 90                           # the stop in the middle of the last leg
START_SEC = 10                          # it stands still this long before it sets off
ALTITUDE_M = 31.0


@dataclass(frozen=True)
class Leg:
    heading_deg: int
    length_m: float
    stop_at_m: float | None = None      # a stop this far along the leg


LAP = (Leg(0, 1200.0), Leg(90, 800.0), Leg(180, 1200.0), Leg(270, 800.0, stop_at_m=400.0))


@dataclass(frozen=True)
class Sample:
    lat: float
    lon: float
    speed_ms: float
    course_deg: int
    altitude_m: float


def _turned(heading: float, toward: float, step: float) -> float:
    """The heading after turning at most `step` degrees the short way toward `toward`."""
    difference = (toward - heading + 180.0) % 360.0 - 180.0
    return (heading + max(-step, min(step, difference))) % 360.0


class Trip:
    def __init__(self, lat: float, lon: float, kmh: float, legs: tuple[Leg, ...] = LAP) -> None:
        self.lat0, self.lon0 = lat, lon
        self.cruise_ms = kmh / 3.6
        self.legs = legs
        self.east_m = self.north_m = 0.0
        self.speed_ms = 0.0
        self.heading = float(legs[0].heading_deg)
        self.leg = 0
        self.along_m = 0.0
        self.paused = START_SEC                 # seconds still to stand
        self.stopped_on_leg = False             # the stop of this leg has been made

    def sample(self) -> Sample:
        lat = self.lat0 + self.north_m / METRES_PER_DEGREE
        lon = self.lon0 + self.east_m / (METRES_PER_DEGREE * math.cos(math.radians(self.lat0)))
        return Sample(lat, lon, self.speed_ms, round(self.heading) % 360, ALTITUDE_M)

    def step(self) -> Sample:
        """The car one second on."""
        if self.paused > 0:
            self.paused -= 1
            self.speed_ms = 0.0
            return self.sample()
        leg = self.legs[self.leg]
        to_end = leg.length_m - self.along_m
        to_stop = None if leg.stop_at_m is None or self.stopped_on_leg else leg.stop_at_m - self.along_m
        braking_for_stop = to_stop is not None and to_stop <= to_end
        distance, end_speed = (to_stop, 0.0) if braking_for_stop and to_stop is not None else (to_end, CORNER_MS)
        allowed = math.sqrt(end_speed ** 2 + 2.0 * DECEL_MS2 * max(distance, 0.0))
        target = min(self.cruise_ms, allowed)
        speed = min(self.speed_ms + ACCEL_MS2, target) if target > self.speed_ms else max(self.speed_ms - DECEL_MS2, target)
        self._move((self.speed_ms + speed) / 2.0)
        self.speed_ms = speed
        self.heading = _turned(self.heading, float(self.legs[self.leg].heading_deg), TURN_DEG_PER_SEC)
        if braking_for_stop and to_stop is not None and to_stop - speed <= 0.5 and speed < 1.0:
            self.speed_ms, self.paused, self.stopped_on_leg = 0.0, STOP_SEC, True
        elif self.along_m >= leg.length_m:
            self._next_leg()
        return self.sample()

    def _move(self, metres: float) -> None:
        radians = math.radians(self.heading)
        self.east_m += metres * math.sin(radians)
        self.north_m += metres * math.cos(radians)
        self.along_m += metres

    def _next_leg(self) -> None:
        self.leg = (self.leg + 1) % len(self.legs)
        self.along_m, self.stopped_on_leg = 0.0, False
