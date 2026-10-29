"""The delivery chain of a message we sent: what each attempt was, and which hops of its path we heard come back.

Every attempt is a transmission by a path (`Attempt`). When a copy of our own message is heard again (by RF with some of the path's has-been-repeated bits set, or wrapped by an iGate as a third-party
packet) it belongs to the latest attempt sent before it was heard, and it shows which hops of that attempt's path did their work: `hops_used` reads the starred addresses of the heard path against the path
we sent. A digipeater that repeats an alias (WIDE1-1) puts its own call in its place, so the call heard is the one recorded for that hop. A hop that was used implies the hops before it were (a digipeater
works the first unused address), so the heard path `OH2RCH-2,OH2RDG*` shows both. What was heard is a `HopSeen`: position 1 to 8 is the hop of the path; position 0 is a copy that came back over the
internet whose own path names no hop, with the iGate's call.

Pure code."""
from dataclasses import dataclass, replace
from datetime import datetime

from neoaprs.route import digipeaters, is_alias, is_marker

AT_GATE = 0                                         # the position of "a copy came back over the internet, by this iGate"


@dataclass(frozen=True, slots=True)
class HopSeen:
    position: int                                   # 1 for the first digipeater of the path we used; AT_GATE (0) for a copy gated back whose path names no hop
    call: str                                       # the call that did it (an alias of the path is replaced by the call heard); the iGate's call at position 0
    heard_at: datetime                              # when the first copy that showed it was heard
    via_internet: bool                              # seen in a third-party copy, not by RF


@dataclass(frozen=True, slots=True)
class Attempt:
    number: int                                     # 1 for the first transmission of the message
    sent_at: datetime
    path: tuple[str, ...]                           # the digipeaters it went by, as sent (WIDE1-1 stays WIDE1-1)
    seen: tuple[HopSeen, ...] = ()

    def with_seen(self, found: HopSeen) -> "Attempt":
        return replace(self, seen=(*self.seen, found))

    def has(self, position: int, via_internet: bool) -> bool:
        return any(s.position == position and s.via_internet == via_internet for s in self.seen)


def hops_used(sent: tuple[str, ...], heard: tuple[str, ...]) -> list[tuple[int, str]]:
    """(position, call) of each hop of the path `sent` (calls, no stars) that the heard path shows used, positions from 1: those up to the furthest starred one. A hop that is an alias takes the next
    starred call as its own; a hop that is a call is found by its call (calls heard between are digipeaters an alias such as WIDE2-2 brought in)."""
    sent = digipeaters(sent)                                    # (RFONLY, NOGATE, TCPIP and the q-constructs are no hops)
    used = [address[:-1] for address in digipeaters(heard) if address.endswith("*")]
    found: dict[int, str] = {}
    k = 0
    for index, hop in enumerate(sent):
        if k >= len(used):
            break
        if is_alias(hop):
            if used[k] not in sent[index + 1:]:                 # (a call the path names further on is that hop's, not this alias's)
                found[index + 1] = used[k]
                k += 1
        elif hop in used[k:]:
            k = used.index(hop, k) + 1
            found[index + 1] = hop
    return [(position, found.get(position, sent[position - 1])) for position in range(1, max(found, default=0) + 1)]


def internet_hops(sent: tuple[str, ...], inner: tuple[str, ...], gate: str) -> list[tuple[int, str]]:
    """The same for the path a third-party packet carried inside the iGate's frame: the pieces that are the internet's own (TCPIP, qAR, the gate) are not digipeaters of ours."""
    path = tuple(piece for piece in inner if not is_marker(piece) and piece.rstrip("*") != gate)
    return hops_used(sent, path)


def attempt_before(attempts: list[Attempt], at: datetime) -> Attempt | None:
    """The latest attempt sent at or before `at`; None when none was."""
    sent = [a for a in attempts if a.sent_at <= at]
    return max(sent, key=lambda a: (a.sent_at, a.number), default=None)
