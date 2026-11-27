"""Track which pages look at a map layer and send them the layer's table as `layer_things`.

A new viewer gets the table at once. A page more than the hub's `BEHIND` bytes behind is skipped;
the next table brings it up to date.
"""

from datetime import datetime
from typing import Any, Protocol

from neoaprs.airports import place
from neoaprs.clock import Clock, iso, utcnow
from neoaprs.layerthing import LAYERS, Layer, LayerTable, Thing

from .hub import BEHIND
from .session import Connection


class Watched(Protocol):
    def watch(self, layer: Layer, on: bool) -> None: ...
    def table(self, layer: Layer, trails: bool = False) -> LayerTable: ...


def thing_row(thing: Thing, layer: Layer) -> dict[str, Any]:
    """Return a thing as `LayerThing` has it; places are looked up for aircraft airports only."""
    return {
        "id": thing.id,
        "lat": thing.lat,
        "lon": thing.lon,
        "at": iso(thing.at),
        "heading_deg": thing.heading_deg,
        "speed_kmh": thing.speed_kmh,
        "name": thing.name,
        "emergency": thing.emergency,
        "altitude_m": thing.altitude_m,
        "vertical_ms": thing.vertical_ms,
        "registration": thing.registration,
        "type": thing.type,
        "category": thing.category,
        "designator": thing.designator,
        "ship_type": thing.ship_type,
        "course_deg": thing.course_deg,
        "destination": thing.destination,
        "origin": thing.origin,
        "origin_place": place(thing.origin),
        "destination_place": place(thing.destination) if layer == "aircraft" else "",
    }


def table_message(table: LayerTable, now: datetime) -> dict[str, Any]:
    return {
        "type": "layer_things",
        "at": iso(now),
        "layer": table.layer,
        "source": table.source,
        "away": table.away,
        "things": [thing_row(thing, table.layer) for thing in table.things],
        "trails": [
            {"id": trail.id, "points": [[round(lon, 5), round(lat, 5), iso(at)] for lon, lat, at in trail.points]}
            for trail in table.trails
        ],
    }


class LayerLooks:
    def __init__(self, service: Watched, clock: Clock = utcnow) -> None:
        self._service = service
        self._clock = clock
        self._pages: dict[Layer, set[Connection]] = {layer: set() for layer in LAYERS}

    def look(self, conn: Connection, layer: Layer, on: bool) -> None:
        """Start or stop a page's look; a page that already closed is ignored."""
        if not on:
            self._leave(conn, layer)
            return
        if conn.closed:
            return
        pages = self._pages[layer]
        first = not pages
        pages.add(conn)
        if first:
            self._service.watch(layer, True)
        self._send(conn, table_message(self._service.table(layer, trails=True), self._clock()))

    def _leave(self, conn: Connection, layer: Layer) -> None:
        pages = self._pages[layer]
        if conn in pages:
            pages.discard(conn)
            if not pages:
                self._service.watch(layer, False)

    def forget(self, conn: Connection) -> None:
        """Remove the page from every layer."""
        for layer in LAYERS:
            self._leave(conn, layer)

    def pages(self, layer: Layer) -> int:
        return len(self._pages[layer])

    def told(self, table: LayerTable) -> None:
        """Send a new table to every page looking at its layer."""
        pages = self._pages[table.layer]
        if pages:
            message = table_message(table, self._clock())
            for conn in list(pages):
                self._send(conn, message)

    @staticmethod
    def _send(conn: Connection, message: dict[str, Any]) -> None:
        if conn.buffered() <= BEHIND:
            conn.send(message)
