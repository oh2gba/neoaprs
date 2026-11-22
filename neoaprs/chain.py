"""The delivery chain of a message we sent: each attempt, and the hops heard coming back.

A copy of our message heard again belongs to the latest attempt sent before it; `hops_used`
reads its starred addresses against the path we sent. Pure code.
"""

from dataclasses import dataclass, replace
from datetime import datetime

from neoaprs.radiotype import RadioId
from neoaprs.route import digipeaters, is_alias, is_marker, used_path

AT_GATE = 0  # position of a copy that came back via an iGate


@dataclass(frozen=True, slots=True)
class HopSeen:
    # 1 for the first digipeater of our path; AT_GATE (0) for a copy gated back whose path names
    # no hop
    position: int
    # the call that did it (an alias is replaced by the call heard); the iGate's call at position 0
    call: str
    heard_at: datetime  # when the first copy that showed it was heard
    via_internet: bool  # seen in a third-party copy, not by RF


@dataclass(frozen=True, slots=True)
class Attempt:
    number: int  # 1 for the first transmission of the message
    sent_at: datetime
    path: tuple[str, ...]  # the digipeaters as sent (WIDE1-1 stays)
    seen: tuple[HopSeen, ...] = ()
    radio_id: RadioId | None = None  # the radio it went out on; None if not recorded

    def with_seen(self, found: HopSeen) -> "Attempt":
        return replace(self, seen=(*self.seen, found))

    def has(self, position: int, via_internet: bool) -> bool:
        return any(s.position == position and s.via_internet == via_internet for s in self.seen)


def hops_used(sent: tuple[str, ...], heard: tuple[str, ...]) -> list[tuple[int, str]]:
    """Return (position, call) of each hop of the sent path that the heard path shows used.

    Positions start at 1, up to the furthest starred one; an alias hop takes the next starred call.
    """
    sent = digipeaters(sent)  # RFONLY, NOGATE, TCPIP and the q-constructs are no hops
    used = [address[:-1] for address in used_path(digipeaters(heard)) if address.endswith("*")]
    found: dict[int, str] = {}
    k = 0
    for index, hop in enumerate(sent):
        if k >= len(used):
            break
        if is_alias(hop):
            # a call named further on in the path is that hop's, not this alias's
            if used[k] not in sent[index + 1 :]:
                found[index + 1] = used[k]
                k += 1
        elif hop in used[k:]:
            k = used.index(hop, k) + 1
            found[index + 1] = hop
    return [(position, found.get(position, sent[position - 1])) for position in range(1, max(found, default=0) + 1)]


def internet_hops(sent: tuple[str, ...], inner: tuple[str, ...], gate: str) -> list[tuple[int, str]]:
    """Like `hops_used`, for the path a third-party packet carried inside the iGate's frame.

    The internet's own pieces (TCPIP, qAR, the gate) are not our digipeaters.
    """
    path = tuple(piece for piece in inner if not is_marker(piece) and piece.rstrip("*") != gate)
    return hops_used(sent, path)


def attempt_before(attempts: list[Attempt], at: datetime) -> Attempt | None:
    """Return the latest attempt sent at or before `at`; None if none."""

    sent = [a for a in attempts if a.sent_at <= at]
    return max(sent, key=lambda a: (a.sent_at, a.number), default=None)
