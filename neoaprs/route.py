"""How a packet reached us: the route read from its AX.25 path, and a station's route counts."""
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import NamedTuple

from neoaprs.policy import HEARD_PATH_ATTEMPTS, HEARD_PATH_MAX_DIGIPEATERS, HEARD_PATH_MIN_PACKETS, HEARD_PATH_WINDOW_MIN
from neoaprs.symbols import is_mobile

UNKNOWN = "?"
WIDE_PATH = "WIDE1-1,WIDE2-1"
FIXED_PATH = "WIDE2-2"
# a path setting meaning no digipeaters at all
DIRECT_ONLY = "DIRECT"
TIMES_KEPT = 2
ROUTES_KEPT = 8
RF_ONLY = "RFONLY"
NO_GATE = "NOGATE"
INTERNET_MARKERS = frozenset({"TCPIP", "TCPXX"})
NO_GATE_MARKERS = frozenset({NO_GATE, RF_ONLY})
# q-constructs: an iGate heard it / a client sent it in
IGATE_QS = frozenset({"qAR", "qAr", "qAO", "qAo"})
CLIENT_QS = frozenset({"qAC", "qAS", "qAX", "qAU"})
_MARKERS = (*sorted(INTERNET_MARKERS), *sorted(NO_GATE_MARKERS), "NOTCP", "qA")
_WORD_ALIAS = "WIDE|TRACE|RELAY|ECHO|GATE|TEMP|TRACK|SAR|ARISS|APRSAT"
# WIDE2-1, TRACE3-3, RELAY, ARISS, and regional New-N aliases (SS3-3)
_ALIAS = re.compile(rf"(?:({_WORD_ALIAS})|([A-Z]{{2,3}}(?=\d)))(\d?)(?:-(\d{{1,2}}))?")
_Q_CONSTRUCT = re.compile(r"q[A-Z]{2}", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Route:
    # the starred addresses in order; an alias is "?"
    hops: tuple[str, ...]
    # the last hop, the station we heard; None if direct or an alias
    heard_from: str | None
    direct: bool
    anonymous: int = 0
    gate: str = ""
    written: tuple[str, ...] = field(default=(), compare=False)


class Alias(NamedTuple):
    """A path element standing for whichever digipeater answers it."""
    prefix: str
    n: int | None
    left: int | None

    @property
    def hops(self) -> int:
        if self.n is None:
            return 1
        return self.n if self.left is None else self.left


def parse_alias(address: str) -> Alias | None:
    """Return the alias a path element is (WIDE2-1, RELAY; a star is ignored), else None."""
    found = _ALIAS.fullmatch(address.removesuffix("*"))
    if found is None:
        return None
    prefix, digit, left = found.group(1) or found.group(2), found.group(3), found.group(4)
    return Alias(prefix, int(digit) if digit else None, int(left) if left else None)


def is_alias(address: str) -> bool:
    return parse_alias(address) is not None


def is_q_construct(element: str) -> bool:
    """Return whether a path element is an APRS-IS q-construct (`qAR` ...)."""
    return _Q_CONSTRUCT.fullmatch(element) is not None


def is_marker(address: str) -> bool:
    """Return whether a path element is an iGate or internet marker (TCPIP, qAR ...)."""
    return address.rstrip("*").startswith(_MARKERS)


def digipeaters(path: tuple[str, ...]) -> tuple[str, ...]:
    """Return the path without its markers."""
    return tuple(address for address in path if not is_marker(address))


def used_path(path: tuple[str, ...]) -> tuple[str, ...]:
    """Return the path with every element up to the last starred one starred (APRS-IS style)."""
    last = max((i for i, address in enumerate(path) if address.endswith("*")), default=-1)
    return tuple(address if address.endswith("*") or i > last else address + "*" for i, address in enumerate(path))


def rf_only_path(path: tuple[str, ...]) -> tuple[str, ...]:
    """Return the path with RFONLY last, unless it has RFONLY or NOGATE."""
    return path if any(address.rstrip("*") in NO_GATE_MARKERS for address in path) else (*path, RF_ONLY)


def route_of(path: tuple[str, ...], gate: str = "") -> Route:
    """Return the route of a received packet; `gate` is a third-party packet's iGate."""
    written = tuple(address[:-1] for address in path if address.endswith("*"))
    hops = tuple(UNKNOWN if is_alias(address) else address for address in written)
    last = hops[-1] if hops else (gate or None)
    return Route(hops, None if last == UNKNOWN else last, not hops and not gate, hops.count(UNKNOWN), gate, written)


def route_text(route: Route) -> str:
    """Return the route as text: "direct", "via A → B", "via GATE (internet) → B"."""
    if route.direct:
        return "direct"
    return "via " + " → ".join(([f"{route.gate} (internet)"] if route.gate else []) + list(route.hops))


def received_text(path: tuple[str, ...], gate: str = "") -> str:
    """Return the route text of a heard packet."""
    return route_text(route_of(path, gate))


def recommended_path(table: str, code: str) -> str:
    """Return the recommended path: WIDE1-1,WIDE2-1 if mobile, else WIDE2-2."""
    return WIDE_PATH if is_mobile(table, code) else FIXED_PATH


def suggested_path(route: Route) -> str:
    """Return the digipeaters to send by: the route turned round (WIDE1-1,WIDE2-1 if anonymous)."""
    if route.direct:
        return ""
    if route.anonymous:
        return WIDE_PATH
    return ",".join(reversed(route.hops))


@dataclass
class Deliveries:
    """How a station's packets reached us: direct, by each route, or third-party (ROUTES_KEPT)."""

    direct: int = 0
    last_direct_at: datetime | None = None
    gated: int = 0
    by_route: dict[tuple[str, ...], int] = field(default_factory=dict)
    times: dict[tuple[str, ...], list[datetime]] = field(default_factory=dict)

    def note(self, route: Route, count: int = 1, at: datetime | None = None, before: datetime | None = None) -> None:
        """Count `count` packets by the route, the latest at `at`, the one before at `before`."""
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
        """Return (packets of the route in the window, time of the latest); () is direct."""
        kept = self.times.get(hops, [])
        return sum(1 for when in kept if now - when <= timedelta(minutes=HEARD_PATH_WINDOW_MIN)), (kept[-1] if kept else None)

    def best(self) -> Route | None:
        """Return the route most packets came by, direct included; ties: fewer hops."""
        best: Route | None = None
        most = (0, 0)
        for hops, count in reversed(self.by_route.items()):
            if (count, -len(hops)) > most:
                best, most = _route_of_hops(hops), (count, -len(hops))
        if self.direct and (self.direct, 0) >= most:
            return Route((), None, True)
        return best

    def heard_via(self) -> list[tuple[str, int]]:
        """Return (the station we heard, packets) per repeater, the most first."""
        counts: dict[str, int] = {}
        for hops, count in self.by_route.items():
            counts[hops[-1]] = counts.get(hops[-1], 0) + count
        return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def _route_of_hops(hops: tuple[str, ...]) -> Route:
    return Route(hops, None if hops[-1] == UNKNOWN else hops[-1], False, hops.count(UNKNOWN))


def heard_path(deliveries: Deliveries, now: datetime) -> tuple[str, ...] | None:
    """Return the path lately shown to reach the station (direct, or a named route turned round)."""
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
    """Return the heard path up to attempt HEARD_PATH_ATTEMPTS; else None."""
    if deliveries is None or attempt > HEARD_PATH_ATTEMPTS:
        return None
    return heard_path(deliveries, now)
