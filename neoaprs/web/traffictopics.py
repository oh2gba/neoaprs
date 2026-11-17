"""The topics of the map's traffic (neoaprs/web/topics.py adds them): `ships` by MMSI and `aircraft` by ICAO address, told item by item from their feeds (services/ais.py, services/adsb.py), and `traffic`, the state of
the two feeds, told whole at most once a second. Only received over the internet, never sent anywhere."""
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from neoaprs.signal import Signal

from .hub import StateHub, Topic
from .trafficwire import AircraftRow, FeedSource, ShipRow, traffic_state

TRAFFIC_EVERY_SEC = 1.0                 # the ships and the aircraft come in rounds of hundreds: their states are told at most once a second
FEED_KEYS = ("ais/", "adsb/")           # (a change of these draws the tracks for another window; the filter and the radius apply at the next round, which the feed asks for at once)


class Feed[T](FeedSource, Protocol):
    """What these topics need of a feed (services/trafficfeed.py)."""
    @property
    def items(self) -> Mapping[str, T]: ...
    @property
    def changed(self) -> Signal[[str]]: ...
    @property
    def cleared(self) -> Signal[[]]: ...
    @property
    def state_changed(self) -> Signal[[]]: ...
    def track(self, key: str) -> list[tuple[float, float]]: ...


def _rows[T](row: Callable[[T, list[tuple[float, float]]], dict[str, Any]], feed: Feed[T]) -> Callable[[], dict[str, Any]]:
    return lambda: {key: row(item, feed.track(key)) for key, item in feed.items.items()}


def _one[T](row: Callable[[T, list[tuple[float, float]]], dict[str, Any]], feed: Feed[T]) -> Callable[[str], dict[str, Any] | None]:
    """The row of one ship or aircraft, with its track; None for one that has gone."""
    def one(key: str) -> dict[str, Any] | None:
        item = feed.items.get(key)
        return None if item is None else row(item, feed.track(key))
    return one


class TrafficTopics:
    def __init__(self, hub: StateHub, ships: Feed[Any], aircraft: Feed[Any]) -> None:
        self.hub = hub
        self.ships, self.aircraft = ships, aircraft
        hub.add(Topic("ships", _rows(ShipRow.of, ships), _one(ShipRow.of, ships)))
        hub.add(Topic("aircraft", _rows(AircraftRow.of, aircraft), _one(AircraftRow.of, aircraft)))
        hub.add(Topic("traffic", lambda: traffic_state(ships, aircraft), interval=TRAFFIC_EVERY_SEC))

    def followed(self) -> list[tuple[Signal[...], Callable[..., None]]]:
        """The signals of the two feeds, with what tells the hub."""
        return [
            (self.ships.changed, self._ship_changed), (self.ships.cleared, self._ships_cleared), (self.ships.state_changed, self._traffic_changed),
            (self.aircraft.changed, self._aircraft_changed), (self.aircraft.cleared, self._aircraft_cleared), (self.aircraft.state_changed, self._traffic_changed),
        ]

    def config_changed(self, keys: set[str] | list[str] | tuple[str, ...]) -> None:
        self.hub.changed("traffic")
        if any(key.startswith(FEED_KEYS) for key in keys):
            self.hub.changed("ships")
            self.hub.changed("aircraft")

    def _ship_changed(self, key: str) -> None:
        self.hub.changed("ships", key)
        self.hub.changed("traffic")                 # (the count)

    def _ships_cleared(self) -> None:
        self.hub.changed("ships")

    def _aircraft_changed(self, key: str) -> None:
        self.hub.changed("aircraft", key)
        self.hub.changed("traffic")

    def _aircraft_cleared(self) -> None:
        self.hub.changed("aircraft")

    def _traffic_changed(self) -> None:
        self.hub.changed("traffic")
