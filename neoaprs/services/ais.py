"""The ships on the map (`ais/enabled`): the AIS positions of Fintraffic's Digitraffic within RADIUS_KM of our position, read every minute, and the voyage data of the ships (name, call sign, type, size,
draught, destination, ETA) read every ten minutes, the first time whole and after that what changed since the last answer. Digitraffic is open data under CC BY 4.0 (Fintraffic / digitraffic.fi), and asks for
gzip and for a `Digitraffic-User` that names the application. Only received and drawn: a ship is no packet and no station, and nothing of it is sent on the radio or to APRS-IS (services/trafficfeed.py)."""
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from neoaprs.ais import Ship, Voyage, parse_locations, parse_vessels, ships_near
from neoaprs.config import Config

from .trafficfeed import Feed

BASE_URL = "https://meri.digitraffic.fi/api/ais/v1"
RADIUS_KM = 450.0
FIX_MAX_AGE_SEC = 3600.0              # a position older than this is not shown: the ship has gone quiet or out of range
VESSELS_EVERY_SEC = 600.0
MAX_LOCATIONS_BYTES = 20_000_000      # (about 0.3 MB for 450 km round Helsinki, unpacked)
MAX_VESSELS_BYTES = 50_000_000        # (the whole list of the Baltic, unpacked, the first time)


class ShipFeed(Feed[Ship]):
    name = "ais"
    every_sec = 60.0
    what = "ships"
    radius_km = RADIUS_KM
    keep_sec = FIX_MAX_AGE_SEC

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.voyages: dict[int, Voyage] = {}
        self._voyages_at: datetime | None = None         # when the voyage data was last read
        self._voyages_since_ms: int | None = None        # what the next question for the voyage data asks from: the newest it has had

    def switch(self, config: Config) -> bool:
        return config.ais_enabled

    def heard_at(self, item: Ship) -> datetime:
        return item.fix.at

    async def read(self, centre: tuple[float, float]) -> Mapping[str, Ship]:
        await self._read_voyages()
        lat, lon = centre
        data = await self._fetch(f"{BASE_URL}/locations?latitude={lat:.4f}&longitude={lon:.4f}&radius={RADIUS_KM:.0f}", self.user, MAX_LOCATIONS_BYTES)
        fixes = parse_locations(data)
        ships = ships_near(fixes, self.voyages, centre, RADIUS_KM, self.clock() - timedelta(seconds=FIX_MAX_AGE_SEC))
        return {str(mmsi): ship for mmsi, ship in ships.items()}

    async def _read_voyages(self) -> None:
        """The voyage data, when it is due: whole the first time, after that what changed since the newest it had. A failure here is the round's (FetchError)."""
        now = self.clock()
        if self._voyages_at is not None and timedelta(0) <= now - self._voyages_at < timedelta(seconds=VESSELS_EVERY_SEC):
            return
        since = f"?from={self._voyages_since_ms}" if self._voyages_since_ms is not None else ""
        data = await self._fetch(f"{BASE_URL}/vessels{since}", self.user, MAX_VESSELS_BYTES)
        self.voyages.update(parse_vessels(data))
        stamps = [item.get("timestamp") for item in data if isinstance(item, dict)] if isinstance(data, list) else []
        newest = max((s for s in stamps if isinstance(s, int)), default=None)
        if newest is not None:
            self._voyages_since_ms = max(newest, self._voyages_since_ms or 0)
        self._voyages_at = now

    def settings_changed(self) -> None:
        super().settings_changed()
        if not self.enabled:                             # (read whole again when it is switched on again)
            self.voyages.clear()
            self._voyages_at, self._voyages_since_ms = None, None
