"""Track which pages look at the satellites layer, with the cards each has open, and send each the
layer's view as `satellites`: every mark, and only the cards that page has open.

A page more than the hub's `BEHIND` bytes behind is skipped; the next round brings it up to date."""

from typing import Any, Protocol

from neoaprs.clock import iso
from neoaprs.satellites import Pass
from neoaprs.satelliteview import Card, Mark, TimedPoint, Tune, View

from .hub import BEHIND
from .session import Connection


class Looked(Protocol):
    view: View | None

    def look(self, on: bool, cards: frozenset[int]) -> None: ...


def _points(points: tuple[TimedPoint, ...]) -> list[dict[str, Any]]:
    return [{"at": iso(at), "lat": lat, "lon": lon} for at, lat, lon in points]


def _tune(tune: Tune) -> dict[str, Any]:
    return {"hz": tune.hz, "rise_hz": tune.rise_hz, "max_hz": tune.max_hz, "set_hz": tune.set_hz}


def _pass(seen: Pass | None) -> dict[str, Any] | None:
    if seen is None:
        return None
    return {
        "rise": iso(seen.rise),
        "set": iso(seen.set),
        "max_at": iso(seen.max_at),
        "max_el_deg": round(max(0.0, seen.max_el_deg), 2),
        "rise_az_deg": round(seen.rise_az_deg, 1) % 360,
        "set_az_deg": round(seen.set_az_deg, 1) % 360,
    }


def mark_row(mark: Mark) -> dict[str, Any]:
    return {"id": mark.id, "name": mark.name, "points": _points(mark.points)}


def card_row(card: Card) -> dict[str, Any]:
    return {
        "id": card.id,
        "name": card.name,
        "downlinks": [_tune(one) for one in card.downlinks],
        "uplinks": [_tune(one) for one in card.uplinks],
        "mode": card.mode,
        "path": card.path,
        "alt_km": card.alt_km,
        "footprint_km": card.footprint_km,
        "track": _points(card.track),
        "next_pass": _pass(card.next_pass),
        "looks": [
            {"at": iso(one.at), "el_deg": one.el_deg, "down_hz": list(one.down_hz), "up_hz": list(one.up_hz)}
            for one in card.looks
        ],
    }


def view_message(view: View, cards: frozenset[int]) -> dict[str, Any]:
    return {
        "type": "satellites",
        "at": iso(view.at),
        "elements_at": iso(view.elements_at),
        "satellites": [mark_row(one) for one in view.marks],
        "cards": [card_row(one) for one in view.cards if one.id in cards],
    }


class SatelliteLooks:
    def __init__(self, service: Looked) -> None:
        self._service = service
        self._pages: dict[Connection, frozenset[int]] = {}

    def look(self, conn: Connection, on: bool, cards: frozenset[int]) -> None:
        """Start, change or stop a page's look; a page that already closed is ignored."""
        if not on:
            self.forget(conn)
            return
        if conn.closed:
            return
        self._pages[conn] = cards
        if self._service.view is not None:
            self._send(conn, view_message(self._service.view, cards))
        self._tell_service()

    def forget(self, conn: Connection) -> None:
        if self._pages.pop(conn, None) is not None:
            self._tell_service()

    def pages(self) -> int:
        return len(self._pages)

    def _tell_service(self) -> None:
        self._service.look(bool(self._pages), frozenset().union(*self._pages.values()))

    def told(self, view: View) -> None:
        """Send the view of a round to every page that looks."""
        for conn, cards in list(self._pages.items()):
            self._send(conn, view_message(view, cards))

    @staticmethod
    def _send(conn: Connection, message: dict[str, Any]) -> None:
        if conn.buffered() <= BEHIND:
            conn.send(message)
