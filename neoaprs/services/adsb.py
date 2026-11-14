"""The aircraft on the map (`adsb/enabled`): the open ADS-B data of adsb.fi (its feeders' receivers, readsb's JSON) within RADIUS_KM of our position, read every EVERY_SEC (the feed allows one question a second
for everyone at one address). Only received and drawn: an aircraft is no packet and no station, and nothing of it is sent on the radio or to APRS-IS (services/trafficfeed.py)."""
from collections.abc import Mapping
from datetime import datetime, timedelta

from neoaprs.adsb import Aircraft, aircraft_near, feed_url, parse_aircraft
from neoaprs.config import Config

from .trafficfeed import Feed

BASE_URL = "https://opendata.adsb.fi/api/v2"
RADIUS_KM = 450.0
EVERY_SEC = 15.0
SEEN_MAX_SEC = 60.0                   # an aircraft whose position is older than this is not shown: it has landed, or flown out of every receiver's range
MAX_BYTES = 10_000_000


class AircraftFeed(Feed[Aircraft]):
    name = "adsb"
    every_sec = EVERY_SEC
    what = "aircraft"
    radius_km = RADIUS_KM
    keep_sec = SEEN_MAX_SEC

    def switch(self, config: Config) -> bool:
        return config.adsb_enabled

    def heard_at(self, item: Aircraft) -> datetime:
        return item.at

    async def read(self, centre: tuple[float, float]) -> Mapping[str, Aircraft]:
        data = await self._fetch(feed_url(BASE_URL, centre, RADIUS_KM), self.user, MAX_BYTES)
        now = self.clock()
        return aircraft_near(parse_aircraft(data, now), centre, RADIUS_KM, now - timedelta(seconds=SEEN_MAX_SEC))
