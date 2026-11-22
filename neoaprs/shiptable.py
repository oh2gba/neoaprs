"""The ships a layer holds, by their MMSI: the last position of each and what it said of itself, put together as the page's one shape of a thing (layerthing.Thing). Memory only; no I/O."""
from dataclasses import replace
from datetime import datetime, timedelta

from .aisdecode import AisPosition, AisStatic
from .clock import Clock, utcnow
from .layerthing import Thing
from .units import KNOT_KMH

STATIC_KEEP = timedelta(hours=24)         # what a ship said of itself is kept this long without a position of it
UNDER_WAY_KN = 0.5                        # at this speed or more the course is the way the ship points when it gives no heading


class ShipTable:
    def __init__(self, clock: Clock = utcnow, bound: int | None = None) -> None:
        """`bound`: what a feed that may flood is held to, the table itself: past twice this many positions (or words) the oldest are dropped down to it."""
        self._clock = clock
        self._bound = bound
        self._positions: dict[int, AisPosition] = {}
        self._statics: dict[int, tuple[AisStatic, datetime]] = {}         # mmsi -> (what it said, when we got it)

    def position(self, p: AisPosition) -> None:
        """Keeps the position unless the ship's last one is newer."""
        last = self._positions.get(p.mmsi)
        if last is None or p.at >= last.at:
            self._positions[p.mmsi] = p
            if self._bound is not None and len(self._positions) > 2 * self._bound:
                newest = sorted(self._positions.values(), key=lambda held: held.at, reverse=True)[:self._bound]
                self._positions = {held.mmsi: held for held in newest}

    def static(self, s: AisStatic) -> None:
        """Keeps what the ship says of itself; a name, kind or destination that this message leaves empty does not wipe what an earlier one said (a class B ship tells its name and its kind in two messages)."""
        before = self._statics.get(s.mmsi)
        if before is not None:
            old = before[0]
            s = replace(s, name=s.name or old.name, ship_type=s.ship_type if s.ship_type is not None else old.ship_type, destination=s.destination or old.destination)
        self._statics.pop(s.mmsi, None)                       # (so that the dict's order is the order of arrival)
        self._statics[s.mmsi] = (s, self._clock())
        if self._bound is not None and len(self._statics) > 2 * self._bound:
            self._statics = dict(list(self._statics.items())[-self._bound:])


    def things(self, now: datetime, max_age_sec: float) -> list[Thing]:
        """The ships whose position is at most `max_age_sec` old, as things; the older ones and the words kept without a position for over 24 hours are forgotten."""
        self._positions = {mmsi: p for mmsi, p in self._positions.items() if (now - p.at).total_seconds() <= max_age_sec}
        self._statics = {mmsi: kept for mmsi, kept in self._statics.items() if now - kept[1] <= STATIC_KEEP or mmsi in self._positions}
        return [self._thing(p) for p in self._positions.values()]

    def _thing(self, p: AisPosition) -> Thing:
        kept = self._statics.get(p.mmsi)
        static = kept[0] if kept else None
        course = None if p.cog_deg is None else round(p.cog_deg) % 360
        if p.heading_deg is not None:
            heading = p.heading_deg
        elif course is not None and p.sog_kn is not None and p.sog_kn >= UNDER_WAY_KN:
            heading = course
        else:
            heading = None
        return Thing(id=str(p.mmsi), lat=p.lat, lon=p.lon, at=p.at, heading_deg=heading, speed_kmh=None if p.sog_kn is None else p.sog_kn * KNOT_KMH,
                     name=static.name if static else "", ship_type=static.ship_type if static else None, course_deg=course, destination=static.destination if static else "")
