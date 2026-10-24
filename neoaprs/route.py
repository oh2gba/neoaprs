"""How a packet reached us: the route read out of its AX.25 path, and the count of the routes a station's packets came by.

A path lists up to 8 digipeater addresses, and each has a has-been-repeated bit (the star of the TNC2 text, `OH2RCH-2*`). A digipeater that repeats a packet usually puts its own call in place of the alias it
used (WIDE1-1 becomes OH2RCH-2*), so the starred addresses, in order, are the route; the last of them is the station whose transmission we heard. A starred alias (WIDE1*, TRACE2-1*) is a hop whose call we
do not know, an anonymous one. No starred address at all means the packet came straight from its sender. Addresses without a star have not been used yet and are not part of the route.

A third-party packet (an iGate put on the air what it heard on the internet, aprsthirdparty.py) is heard from the iGate, not from its sender: its route starts at the gate, "via OH7JHF-1 (internet)", and
goes on through the digipeaters that repeated the gate's frame. The gate is no digipeater of the path, so such a delivery is counted apart and never makes a route to suggest.

Pure code: a path is the strings of `Packet.path`, each with its own star as `Address.__str__` writes it."""
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from neoaprs.policy import HEARD_PATH_ATTEMPTS, HEARD_PATH_MAX_DIGIPEATERS, HEARD_PATH_MIN_PACKETS, HEARD_PATH_WINDOW_MIN

UNKNOWN = "?"                                       # a hop whose call is not known, in `Route.hops`
WIDE_PATH = "WIDE1-1,WIDE2-1"                       # the recommended path: what an empty path setting means, and what is suggested for a station that was heard through a hop with no call
DIRECT_ONLY = "DIRECT"                              # what a path setting says to mean no digipeaters at all, explicitly (an empty one means the recommended path); it stands alone and is no call
TIMES_KEPT = 2                                      # the times of the latest packets that are kept for each route (and for direct): enough to tell whether HEARD_PATH_MIN_PACKETS of them are recent
ROUTES_KEPT = 8                                     # the routes counted for one station
RF_ONLY = "RFONLY"                                  # the path element that an iGate does not gate to the internet a packet with (NOGATE says the same)
NO_GATE = "NOGATE"
_MARKERS = ("TCPIP", "TCPXX", NO_GATE, RF_ONLY, "NOTCP", "qA")
_ALIAS = re.compile(r"^(WIDE|TRACE|RELAY|ECHO|GATE|TEMP|TRACK|SAR)\d?(-\d{1,2})?$")


@dataclass(frozen=True, slots=True)
class Route:
    hops: tuple[str, ...]                           # the starred addresses in order; a hop that is an alias is "?"
    heard_from: str | None                          # the call of the last hop, the station we heard; None for a direct packet and when the last hop is an alias
    direct: bool                                    # no address is starred and no gate: heard from the sender itself
    anonymous: int = 0                              # how many hops are aliases
    gate: str = ""                                  # the iGate that put a third-party packet on the air; hops are the digipeaters of the gate's frame
    written: tuple[str, ...] = field(default=(), compare=False)   # the hops as the path wrote them ("WIDE1", "OH2RCH-2"), without the star; empty for a route rebuilt from a count


def is_alias(address: str) -> bool:
    return _ALIAS.match(address) is not None


def is_marker(address: str) -> bool:
    """Whether a path element is a marker for the iGates and the internet (TCPIP, TCPXX, NOGATE, RFONLY, NOTCP, a q-construct such as qAR) and no digipeater: nothing repeats it, so no hop of a chain is made of it."""
    return address.rstrip("*").startswith(_MARKERS)


def digipeaters(path: tuple[str, ...]) -> tuple[str, ...]:
    """The path without its markers: the hops."""
    return tuple(address for address in path if not is_marker(address))


def rf_only_path(path: tuple[str, ...]) -> tuple[str, ...]:
    """The path with RFONLY as its last element, which asks the iGates not to put the packet on the internet; a path that holds RFONLY or NOGATE already is as it is."""
    return path if any(address.rstrip("*") in (RF_ONLY, NO_GATE) for address in path) else (*path, RF_ONLY)


def route_of(path: tuple[str, ...], gate: str = "") -> Route:
    """The route of a received packet from its path, the star of each address that has been repeated kept on it ("WIDE1*", "OH2RCH-2*"); `gate` is the iGate of a third-party packet. For a third-party
    packet `heard_from` is the last digipeater, or the gate when its frame was heard direct."""
    written = tuple(address[:-1] for address in path if address.endswith("*"))
    hops = tuple(UNKNOWN if is_alias(address) else address for address in written)
    last = hops[-1] if hops else (gate or None)
    return Route(hops, None if last == UNKNOWN else last, not hops and not gate, hops.count(UNKNOWN), gate, written)


def route_text(route: Route) -> str:
    """"direct", "via OH2RCH-2", "via OH2RCH-1 → OH2RCH-3", "via ? → OH2RCH-2"; a third-party packet starts at its gate: "via OH7JHF-1 (internet)", "via OH7JHF-1 (internet) → OH2RCH-3"."""
    if route.direct:
        return "direct"
    return "via " + " → ".join(([f"{route.gate} (internet)"] if route.gate else []) + list(route.hops))


def received_text(path: tuple[str, ...], gate: str = "") -> str:
    """The text of the route of a packet that was heard, from its path (and the gate of a third-party packet)."""
    return route_text(route_of(path, gate))


def suggested_path(route: Route) -> str:
    """The digipeaters to send by to reach the station that was heard by way of `route`: the route turned round (heard via A → B, send by B,A), empty for direct, and WIDE1-1,WIDE2-1 when a hop is
    an anonymous one, as there is no call to name. (A route with a gate is not one to send by: Deliveries never offers it.)"""
    if route.direct:
        return ""
    if route.anonymous:
        return WIDE_PATH
    return ",".join(reversed(route.hops))


@dataclass
class Deliveries:
    """How the packets of one station reached us: how many came direct (and when the latest did), how many by each route (the hops, in order) and how many were third-party packets (counted, never a route to send by). At most ROUTES_KEPT routes are counted; when a new one comes and there is no room
    the route with the fewest packets goes, the one longest unheard first."""

    direct: int = 0
    last_direct_at: datetime | None = None          # when the latest packet that came direct was heard
    gated: int = 0
    by_route: dict[tuple[str, ...], int] = field(default_factory=dict)      # in the order of their latest packet, the oldest first
    times: dict[tuple[str, ...], list[datetime]] = field(default_factory=dict)      # the times of the latest TIMES_KEPT packets of each route, the oldest first; direct is under the empty route

    def note(self, route: Route, count: int = 1, at: datetime | None = None, before: datetime | None = None) -> None:
        """Counts `count` packets that came by the route, the latest of them heard at `at` and the one before it at `before` (the time of a direct packet is kept for `last_direct_at`, the times of the latest
        of any route for `heard_path`)."""
        if route.direct:
            self.direct += count
            if at is not None and (self.last_direct_at is None or at > self.last_direct_at):
                self.last_direct_at = at
            self._times(route.hops, at, before)
            return
        if route.gate:
            self.gated += count
            return
        total = self.by_route.pop(route.hops, 0) + count
        if len(self.by_route) >= ROUTES_KEPT:
            gone = min(self.by_route, key=lambda hops: self.by_route[hops])
            del self.by_route[gone]
            self.times.pop(gone, None)
        self.by_route[route.hops] = total
        self._times(route.hops, at, before)

    def _times(self, hops: tuple[str, ...], at: datetime | None, before: datetime | None) -> None:
        kept = self.times.setdefault(hops, [])
        kept.extend(when for when in (before, at) if when is not None)
        kept.sort()
        del kept[:-TIMES_KEPT]
        if not kept:
            del self.times[hops]

    def recent(self, hops: tuple[str, ...], now: datetime) -> tuple[int, datetime | None]:
        """(how many of the latest packets by the route were heard within HEARD_PATH_WINDOW_MIN of `now` (at most TIMES_KEPT), when the latest was heard); the empty route is direct."""
        kept = self.times.get(hops, [])
        return sum(1 for when in kept if now - when <= timedelta(minutes=HEARD_PATH_WINDOW_MIN)), (kept[-1] if kept else None)

    def best(self) -> Route | None:
        """The route most packets came by, direct included; of equal counts the one with fewer hops, then the one heard last. None before any packet."""
        best: Route | None = None
        most = (0, 0)
        for hops, count in reversed(self.by_route.items()):
            if (count, -len(hops)) > most:
                best, most = _route_of_hops(hops), (count, -len(hops))
        if self.direct and (self.direct, 0) >= most:
            return Route((), None, True)
        return best

    def heard_via(self) -> list[tuple[str, int]]:
        """(the station we heard, packets) for each station that repeated them, the most first; "?" is a hop with no call."""
        counts: dict[str, int] = {}
        for hops, count in self.by_route.items():
            counts[hops[-1]] = counts.get(hops[-1], 0) + count
        return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def _route_of_hops(hops: tuple[str, ...]) -> Route:
    return Route(hops, None if hops[-1] == UNKNOWN else hops[-1], False, hops.count(UNKNOWN))


def heard_path(deliveries: Deliveries, now: datetime) -> tuple[str, ...] | None:
    """The path that has lately been shown to reach the station, or None when there is none: the empty path (direct) if at least HEARD_PATH_MIN_PACKETS of its packets came direct within
    HEARD_PATH_WINDOW_MIN of `now`; else its most recent named route (no anonymous hop, no gate, no marker, at most HEARD_PATH_MAX_DIGIPEATERS digipeaters) with that many packets within the window, turned
    round (heard via A -> B, send by B,A)."""
    if deliveries.recent((), now)[0] >= HEARD_PATH_MIN_PACKETS:
        return ()
    best: tuple[datetime, tuple[str, ...]] | None = None
    for hops in deliveries.by_route:
        if not hops or len(hops) > HEARD_PATH_MAX_DIGIPEATERS or UNKNOWN in hops or any(is_marker(hop) for hop in hops):
            continue
        recent, latest = deliveries.recent(hops, now)
        if recent >= HEARD_PATH_MIN_PACKETS and latest is not None and (best is None or latest > best[0]):
            best = (latest, hops)
    return None if best is None else tuple(reversed(best[1]))


def automatic_path(deliveries: Deliveries | None, now: datetime, attempt: int) -> tuple[str, ...] | None:
    """The path attempt number `attempt` (1 for the first) of a message to a station goes by when the operator has set none: the heard path for the attempts up to HEARD_PATH_ATTEMPTS, None (the path of the
    setting `beacon/path`) for the later ones and when no path has lately been heard."""
    if deliveries is None or attempt > HEARD_PATH_ATTEMPTS:
        return None
    return heard_path(deliveries, now)
