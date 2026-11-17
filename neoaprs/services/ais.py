"""The ships on the map (`ais/enabled`): the AIS positions of Fintraffic's Digitraffic within `ais/radius_km` of our position, read every minute, and the voyage data of the ships (name, call sign, type, size,
draught, destination, ETA) read every ten minutes, and of those the ones `ais/types` and `ais/hide_still` let through, the first time whole and after that what changed since the last answer. Digitraffic is open data under CC BY 4.0 (Fintraffic / digitraffic.fi), and asks for
gzip and for a `Digitraffic-User` that names the application. Only received and drawn: a ship is no packet and no station, and nothing of it is sent on the radio or to APRS-IS (services/trafficfeed.py)."""
from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

from neoaprs.ais import Ship, Voyage, parse_locations, parse_vessels, ships_near, shown
from neoaprs.config import Config

from .trafficfeed import Feed

BASE_URL = "https://meri.digitraffic.fi/api/ais/v1"
FIX_MAX_AGE_SEC = 3600.0              # a position older than this is not shown: the ship has gone quiet or out of range
VESSELS_EVERY_SEC = 600.0
RETELL_SEC = 600.0                    # a ship that only reports again in the same place is told to the page this often (a moored ship reports every few minutes)
MAX_LOCATIONS_BYTES = 20_000_000      # (about 0.3 MB for 450 km round Helsinki, unpacked)
MAX_VESSELS_BYTES = 50_000_000        # (the whole list of the Baltic, unpacked, the first time)


class ShipFeed(Feed[Ship]):
    name = "ais"
    every_sec = 60.0
    what = "ships"
    track_step_m = 30.0
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

    def place(self, item: Ship) -> tuple[float, float]:
        return item.fix.lat, item.fix.lon

    def same(self, told: Ship, now: Ship) -> bool:
        """A ship that reported again with nothing changed but the time is told again only after RETELL_SEC (so that the time it was heard does not grow too old on the page)."""
        return replace(told.fix, at=now.fix.at) == now.fix and told.voyage == now.voyage and told.distance_km == now.distance_km and now.fix.at - told.fix.at < timedelta(seconds=RETELL_SEC)

    def radius(self, config: Config) -> float:
        return float(config.ais_radius_km)

    def window_min(self, config: Config) -> int:
        return config.ais_track_min

    async def read(self, centre: tuple[float, float]) -> Mapping[str, Ship]:
        await self._read_voyages()
        lat, lon = centre
        config, radius = self._config(), self.radius_km
        data = await self._fetch(f"{BASE_URL}/locations?latitude={lat:.4f}&longitude={lon:.4f}&radius={radius:.0f}", self.user, MAX_LOCATIONS_BYTES)
        ships = ships_near(parse_locations(data), self.voyages, centre, radius, self.clock() - timedelta(seconds=FIX_MAX_AGE_SEC))
        types = frozenset(config.ais_types.split(","))
        return {str(mmsi): ship for mmsi, ship in ships.items() if shown(ship, types, config.ais_hide_still)}

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
