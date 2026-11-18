"""The pages that look at a layer of traffic on the map (`layer_look`, neoaprs/web/layerwire.py), and the layer's whole table sent to them as `layer_things`, in the pattern of the levels' feed
(neoaprs/web/levelfeed.py): a page that begins to look is sent the table as it is now at once; a page whose socket holds more than the hub's `BEHIND` of what it has not read is sent no table (the next one tells it
all); a page that leaves is forgotten. The layers' service (neoaprs/services/layers.py) is told when the first page begins to look at a layer and when the last one stops: it asks the layer's source only while one
looks."""
from typing import Any, Protocol

from neoaprs.clock import iso
from neoaprs.layerthing import LAYERS, Layer, LayerTable, Thing

from .hub import BEHIND
from .session import Connection


class Watched(Protocol):
    """What the pages' looks need of the layers' service."""
    def watch(self, layer: Layer, on: bool) -> None: ...
    def table(self, layer: Layer) -> LayerTable: ...


def thing_row(thing: Thing) -> dict[str, Any]:
    """A thing as `LayerThing` says it: every field, the time in ISO."""
    return {"id": thing.id, "lat": thing.lat, "lon": thing.lon, "at": iso(thing.at), "heading_deg": thing.heading_deg, "speed_kmh": thing.speed_kmh, "name": thing.name, "emergency": thing.emergency,
            "altitude_m": thing.altitude_m, "registration": thing.registration, "type": thing.type, "ship_type": thing.ship_type, "course_deg": thing.course_deg, "destination": thing.destination}


def table_message(table: LayerTable) -> dict[str, Any]:
    """The `layer_things` message of a layer's table."""
    return {"type": "layer_things", "layer": table.layer, "source": table.source, "away": table.away, "things": [thing_row(thing) for thing in table.things]}


class LayerLooks:
    """Which pages look at which layer."""

    def __init__(self, service: Watched) -> None:
        self._service = service
        self._pages: dict[Layer, set[Connection]] = {layer: set() for layer in LAYERS}

    def look(self, conn: Connection, layer: Layer, on: bool) -> None:
        """The page looks at the layer, or no more. A page that has left meanwhile is not taken (the command ran after it closed)."""
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
        self._send(conn, table_message(self._service.table(layer)))

    def _leave(self, conn: Connection, layer: Layer) -> None:
        pages = self._pages[layer]
        if conn in pages:
            pages.discard(conn)
            if not pages:
                self._service.watch(layer, False)

    def forget(self, conn: Connection) -> None:
        """The page left: it looks at nothing."""
        for layer in LAYERS:
            self._leave(conn, layer)

    def pages(self, layer: Layer) -> int:
        return len(self._pages[layer])

    def told(self, table: LayerTable) -> None:
        """The service has a table for the pages that look at its layer."""
        pages = self._pages[table.layer]
        if pages:
            message = table_message(table)
            for conn in list(pages):
                self._send(conn, message)

    @staticmethod
    def _send(conn: Connection, message: dict[str, Any]) -> None:
        if conn.buffered() <= BEHIND:
            conn.send(message)
