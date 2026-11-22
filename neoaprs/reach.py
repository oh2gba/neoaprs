"""How a packet got to us: an internet packet's way from its APRS-IS path, and routes.

`qAR`/`qAO` name an iGate that heard the packet on the radio; `qAC`, `qAS`, `qAX`, `qAU` or
`TCPIP*` mean a client sent it into the network. Pure code.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .packet import IS, Packet
from .route import CLIENT_QS, IGATE_QS, INTERNET_MARKERS, digipeaters, is_q_construct, route_of, used_path

# routes of a station kept
MARKS_KEPT = 2

Kind = Literal["igate", "app"]
MarkKind = Literal["rf", "gated", "igate", "app"]


@dataclass(frozen=True, slots=True)
class Reach:
    """How an internet packet got there: an iGate heard it (with `hops`), or an app sent it."""

    kind: Kind
    igate: str = ""
    hops: tuple[str, ...] = ()


def reach_of_path(path: tuple[str, ...]) -> Reach | None:
    """Return the way an APRS-IS path says the packet got into the network, or None."""
    at = next((i for i, element in enumerate(path) if is_q_construct(element)), None)
    if at is None:
        return (
            Reach("app") if any(element.rstrip("*").startswith(tuple(INTERNET_MARKERS)) for element in path) else None
        )
    code, after = path[at], path[at + 1].rstrip("*") if at + 1 < len(path) else ""
    if code in CLIENT_QS:
        return Reach("app")
    if code in IGATE_QS and after:
        return Reach("igate", after, route_of(used_path(digipeaters(path[:at]))).hops)
    return None


def reach_of(packet: Packet) -> Reach | None:
    """Return the way an internet packet got in; None for a radio packet or an unclear path."""
    return reach_of_path(packet.path) if packet.via == IS else None


@dataclass(frozen=True, slots=True)
class RouteMark:
    """One route a station's packet came by, for the map: `rf`, `gated`, `igate` or `app`.

    `at` is when it was heard, `lat`/`lon` where its station was then (None if unknown).
    """

    kind: MarkKind
    hops: tuple[str, ...]
    gate: str
    at: datetime
    lat: float | None
    lon: float | None

    def same_route(self, other: "RouteMark") -> bool:
        return (self.kind, self.hops, self.gate) == (other.kind, other.hops, other.gate)


def mark_of(packet: Packet, lat: float | None, lon: float | None) -> RouteMark | None:
    """Return the route of a received packet; None for an internet packet with an unclear path."""
    if packet.via == IS:
        reach = reach_of(packet)
        return None if reach is None else RouteMark(reach.kind, reach.hops, reach.igate, packet.heard_at, lat, lon)
    route = route_of(packet.path, packet.gate)
    return RouteMark("gated" if route.gate else "rf", route.hops, route.gate, packet.heard_at, lat, lon)


def pushed(marks: tuple[RouteMark, ...], mark: RouteMark) -> tuple[RouteMark, ...]:
    """Return a station's routes with the route just heard, latest first (two kept)."""
    if marks and marks[0].same_route(mark):
        return (mark, *marks[1:])
    return (mark, *marks[: MARKS_KEPT - 1])
