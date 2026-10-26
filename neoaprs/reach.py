"""How a packet got to us, told for the person: the way of an internet packet read out of its APRS-IS path, and the two latest routes of a station that the map draws.

The q-construct that APRS-IS servers put in a path says how the packet entered the network. `qAR` and `qAO` (and `qAr`, `qAo`, their indirect forms) name an iGate that heard the packet on the radio, `qAO` one that only listens;
the starred addresses before the q-construct are the digipeaters that repeated it on the way. `qAC`, `qAS`, `qAX` and `qAU`, or `TCPIP*` with no q-construct, mean a client sent the packet into the network itself, an app or a
program, and it was never on the air. A path that says neither (`qAZ`, a trace, no q-construct at all) is not read.

A station keeps the way of its latest internet packet (`Reach`) and the two latest different routes of its packets of any channel (`RouteMark`): the map draws the latest and the one before it, and no others.

Pure code: a path is the strings of `Packet.path`, each with its own star."""
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .packet import IS, Packet
from .route import digipeaters, route_of

MARKS_KEPT = 2                                      # the routes of a station that are kept: the latest and the one before it that was another
_Q = re.compile(r"q[A-Za-z]{2}")
_IGATE_QS = frozenset({"qAR", "qAr", "qAO", "qAo"})     # an iGate heard it on the radio (qAO: one that only listens)
_CLIENT_QS = frozenset({"qAC", "qAS", "qAX", "qAU"})    # a client sent it into the network
_CLIENT_MARKERS = ("TCPIP", "TCPXX")

Kind = Literal["igate", "app"]
MarkKind = Literal["rf", "gated", "igate", "app"]


@dataclass(frozen=True, slots=True)
class Reach:
    """How a packet from the internet got there: `igate` heard it on the radio (`igate` is its call, `hops` the digipeaters that repeated it, `?` for one that put no call in) or `app` sent it from the internet, never on the air."""
    kind: Kind
    igate: str = ""
    hops: tuple[str, ...] = ()


def reach_of_path(path: tuple[str, ...]) -> Reach | None:
    """The way an APRS-IS path says the packet got into the network; None when it says neither (no q-construct and no TCPIP, a trace, an iGate q-construct with no call after it)."""
    at = next((i for i, element in enumerate(path) if _Q.fullmatch(element)), None)
    if at is None:
        return Reach("app") if any(element.rstrip("*").startswith(_CLIENT_MARKERS) for element in path) else None
    code, after = path[at], path[at + 1].rstrip("*") if at + 1 < len(path) else ""
    if code in _CLIENT_QS:
        return Reach("app")
    if code in _IGATE_QS and after:
        return Reach("igate", after, route_of(digipeaters(path[:at])).hops)
    return None


def reach_of(packet: Packet) -> Reach | None:
    """The way a packet received over the internet got into it; None for a packet that was on the radio (its route is `route_of`'s), and for a path that does not say."""
    return reach_of_path(packet.path) if packet.via == IS else None


@dataclass(frozen=True, slots=True)
class RouteMark:
    """One route a station's packet came by, for the map: `rf` on the radio (no hops: direct), `gated` on the radio as a third-party packet that the iGate `gate` put on the air (`hops` repeated the gate's frame), `igate` heard on the
    radio by the iGate `gate` and put on the internet, `app` sent from the internet (no line). `at` is when the packet was heard and `lat`, `lon` where its station was then, None where that is not known."""
    kind: MarkKind
    hops: tuple[str, ...]
    gate: str
    at: datetime
    lat: float | None
    lon: float | None

    def same_route(self, other: "RouteMark") -> bool:
        return (self.kind, self.hops, self.gate) == (other.kind, other.hops, other.gate)


def mark_of(packet: Packet, lat: float | None, lon: float | None) -> RouteMark | None:
    """The route of a received packet; None for an internet packet whose path does not say how it got there."""
    if packet.via == IS:
        reach = reach_of(packet)
        return None if reach is None else RouteMark(reach.kind, reach.hops, reach.igate, packet.heard_at, lat, lon)
    route = route_of(packet.path, packet.gate)
    return RouteMark("gated" if route.gate else "rf", route.hops, route.gate, packet.heard_at, lat, lon)


def pushed(marks: tuple[RouteMark, ...], mark: RouteMark) -> tuple[RouteMark, ...]:
    """The routes of a station with the route of a packet just heard: the latest first, and the one before it that was another. A packet by the route of the latest one only renews it; one by the route of the
    older one makes it the latest, and the latest the older."""
    if marks and marks[0].same_route(mark):
        return (mark, *marks[1:])
    return (mark, *marks[:MARKS_KEPT - 1])

