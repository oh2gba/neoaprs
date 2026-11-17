"""The tracks of the map's ships and aircraft (services/trafficfeed.py): the places each has been at, by key, a new one kept only when it is at least `step_m` from the last (a moored ship adds nothing), none older
than KEEP_SEC and at most MAX_POINTS. What the page is given is the part newer than the window it asks for (ais/track_min, adsb/track_min), thinned to at most MAX_SENT places, each to DIGITS decimals. Pure code, in memory only."""
from collections import deque
from datetime import datetime, timedelta

from .geo import distance_km

KEEP_SEC = 12 * 3600.0               # the longest window the settings offer (configtraffic.TRACK_MINUTES)
MAX_POINTS = 2000                    # the places one item keeps
MAX_SENT = 150                       # the places one row carries to the page
DIGITS = 5                           # the decimals of a place on the wire: about a metre


class Tracks:
    def __init__(self, step_m: float) -> None:
        self.step_m = step_m
        self._places: dict[str, deque[tuple[datetime, float, float]]] = {}

    def add(self, key: str, at: datetime, lat: float, lon: float) -> None:
        """The item is at this place now: kept when it has moved `step_m` since the last one kept, and the places older than KEEP_SEC go."""
        places = self._places.setdefault(key, deque(maxlen=MAX_POINTS))
        if places and distance_km(places[-1][1], places[-1][2], lat, lon) * 1000.0 < self.step_m:
            return
        places.append((at, lat, lon))
        limit = at - timedelta(seconds=KEEP_SEC)
        while places and places[0][0] < limit:
            places.popleft()

    def drop(self, key: str) -> None:
        self._places.pop(key, None)

    def clear(self) -> None:
        self._places.clear()

    def count(self, key: str, since: datetime) -> int:
        """How many places of the item are newer than `since`."""
        return sum(1 for place in self._places.get(key, ()) if place[0] > since)

    def since(self, key: str, since: datetime) -> list[tuple[float, float]]:
        """The places of the item newer than `since`, the oldest first, as (lat, lon): every n-th when there are more than MAX_SENT, and always the newest."""
        places = [(round(lat, DIGITS), round(lon, DIGITS)) for at, lat, lon in self._places.get(key, ()) if at > since]
        if len(places) <= MAX_SENT:
            return places
        step = -(-len(places) // MAX_SENT)
        return places[::step][: MAX_SENT - 1] + [places[-1]]
