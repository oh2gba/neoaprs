"""The aircraft on the map (`adsb/enabled`): the open ADS-B data of adsb.fi (its feeders' receivers, readsb's JSON) within `adsb/radius_km` of our position, read every EVERY_SEC (the feed allows one question a second
for everyone at one address). Only received and drawn: an aircraft is no packet and no station, and nothing of it is sent on the radio or to APRS-IS (services/trafficfeed.py)."""
from collections.abc import Mapping
from datetime import datetime, timedelta

from neoaprs.adsb import Aircraft, aircraft_near, feed_url, parse_aircraft
from neoaprs.config import Config

from .trafficfeed import Feed

BASE_URL = "https://opendata.adsb.fi/api/v2"
EVERY_SEC = 15.0
SEEN_MAX_SEC = 60.0                   # an aircraft whose position is older than this is not shown: it has landed, or flown out of every receiver's range
MAX_BYTES = 10_000_000


class AircraftFeed(Feed[Aircraft]):
    name = "adsb"
    every_sec = EVERY_SEC
    what = "aircraft"
    track_step_m = 200.0
    keep_sec = SEEN_MAX_SEC

    def switch(self, config: Config) -> bool:
        return config.adsb_enabled

    def heard_at(self, item: Aircraft) -> datetime:
        return item.at

    def place(self, item: Aircraft) -> tuple[float, float]:
        return item.lat, item.lon

    def radius(self, config: Config) -> float:
        return float(config.adsb_radius_km)

    def window_min(self, config: Config) -> int:
        return config.adsb_track_min

    async def read(self, centre: tuple[float, float]) -> Mapping[str, Aircraft]:
        radius = self.radius_km
        data = await self._fetch(feed_url(BASE_URL, centre, radius), self.user, MAX_BYTES)
        now = self.clock()
        return aircraft_near(parse_aircraft(data, now), centre, radius, now - timedelta(seconds=SEEN_MAX_SEC))
