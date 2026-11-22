"""Limits on frames sent again for other stations: a burst limit, or a budget for a slow radio."""
from collections import deque
from datetime import datetime, timedelta
from typing import Literal

from neoaprs import bulletin, message
from neoaprs.callsign import normal_name
from neoaprs.mercury import FRAME_SEC
from neoaprs.packet import Message, Packet
from neoaprs.radiotype import RadioId
from neoaprs.services.pace import within

# L1: frames a fast radio sends again per window.
BURST_MAX = 4
BURST_WINDOW_SEC = 10.0
# L2: frames a slow radio takes from the pairs per window.
SLOW_PASS_MAX = 4
SLOW_PASS_OTHER_MAX = 2
SLOW_PASS_PER_SOURCE = 2
SLOW_PASS_WINDOW_SEC = 300.0
# L4: least time between two frames handed to a slow radio.
SLOW_HANDOVER_SEC = FRAME_SEC

PassKind = Literal["message", "ack", "other"]
HoldReason = Literal["budget", "share", "floor"]


class Burst:
    """At most `most` frames sent again per radio per `window` seconds (L1)."""

    def __init__(self, most: int, window: float) -> None:
        self.most = most
        self.window = window
        self._sent: dict[RadioId, deque[datetime]] = {}

    def full(self, radio: RadioId, now: datetime) -> bool:
        """Return whether the radio has reached the limit."""
        sent = self._sent.setdefault(radio, deque(maxlen=self.most))
        while sent and not within(sent[0], now, self.window):
            sent.popleft()
        return len(sent) >= self.most

    def take(self, radio: RadioId, now: datetime) -> None:
        """Record a frame sent on the radio."""
        self._sent.setdefault(radio, deque(maxlen=self.most)).append(now)


def pass_kind(packet: Packet) -> PassKind:
    """Return the kind the slow-radio limits count the packet as."""
    decoded = packet.decoded
    if not isinstance(decoded, Message) or bulletin.board_slot(decoded.addressee) is not None:
        return "other"
    if decoded.ack_id is not None or decoded.rej_id is not None:
        return "ack"
    if decoded.text and not message.is_telemetry_definition(decoded.text):
        return "message"
    return "other"


def source_name(source: str) -> str:
    """Return the normal name, or the upper-cased text if it is not a valid name."""
    try:
        return normal_name(source)
    except ValueError:
        return source.strip().upper()


class SlowBudget:
    """What one slow radio takes from the pairs: the window limits (L2) and the floor (L3)."""

    def __init__(self, floor_min: int) -> None:
        self._floor = timedelta(minutes=floor_min)
        self._window = timedelta(seconds=SLOW_PASS_WINDOW_SEC)
        self._taken: deque[tuple[datetime, str, PassKind]] = deque()
        self._others: dict[str, datetime] = {}

    def _prune(self, now: datetime) -> None:
        while self._taken and now - self._taken[0][0] >= self._window:
            self._taken.popleft()
        for name in [n for n, at in self._others.items() if now - at >= self._floor]:
            del self._others[name]

    def refusal(self, source: str, kind: PassKind, now: datetime) -> HoldReason | None:
        """Return what holds the frame, or None if it may go. Records nothing."""
        self._prune(now)
        name = source_name(source)
        if len(self._taken) >= SLOW_PASS_MAX:
            return "budget"
        if kind == "other":
            if sum(1 for _, _, k in self._taken if k == "other") >= SLOW_PASS_OTHER_MAX:
                return "budget"
            return "floor" if name in self._others else None
        if kind == "message" and sum(1 for _, n, k in self._taken if k == "message" and n == name) >= SLOW_PASS_PER_SOURCE:
            return "share"
        return None

    def take(self, source: str, kind: PassKind, now: datetime) -> None:
        """Record a frame of that source and kind as sent."""
        self._prune(now)
        name = source_name(source)
        self._taken.append((now, name, kind))
        if kind == "other":
            self._others[name] = now
