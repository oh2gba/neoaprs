"""The limits of what the station sends again for other stations, by the radio it goes out on (aprs-reference/cross-radio-digipeat-plan.md section 3.3): the burst of a fast radio, shared by the fill-in and the pairs, and the budget, the shares and the floor of a slow one, with the kinds of packet they count."""
from collections import deque
from datetime import datetime, timedelta
from typing import Literal

from neoaprs import bulletin, message
from neoaprs.callsign import normal_name
from neoaprs.mercury import FRAME_SEC
from neoaprs.packet import Message, Packet
from neoaprs.radiotype import RadioId

BURST_MAX = 4                      # frames a fast radio sends again in any BURST_WINDOW_SEC, the fill-in's and the pairs' together (L1)
BURST_WINDOW_SEC = 10.0
SLOW_PASS_MAX = 4                  # frames a slow radio takes from the pairs in any SLOW_PASS_WINDOW_SEC (L2: 15.2 s of keying in 300 s on Mercury)
SLOW_PASS_OTHER_MAX = 2            # of them of kind "other" (positions, status, objects, telemetry ...), so that messages and acks always keep the rest
SLOW_PASS_PER_SOURCE = 2           # of them messages from one source (L2's share; an ack or rej is not counted in it)
SLOW_PASS_WINDOW_SEC = 300.0
SLOW_HANDOVER_SEC = FRAME_SEC      # the least time between two frames handed to a slow radio (L4: Mercury keys only at PTT ON)

PassKind = Literal["message", "ack", "other"]
HoldReason = Literal["budget", "share", "floor"]


class Burst:
    """At most `most` frames sent again on a radio in any `window` seconds, by radio (L1, and the fill-in's limit)."""

    def __init__(self, most: int, window: float) -> None:
        self.most = most
        self.window = window
        self._sent: dict[RadioId, deque[datetime]] = {}         # by radio: when the latest frames it sent again went out

    def full(self, radio: RadioId, now: datetime) -> bool:
        """Whether the radio has sent `most` frames again in the last `window` seconds."""
        sent = self._sent.setdefault(radio, deque(maxlen=self.most))
        while sent and (now - sent[0]).total_seconds() >= self.window:
            sent.popleft()
        return len(sent) >= self.most

    def take(self, radio: RadioId, now: datetime) -> None:
        """A frame went out on the radio now."""
        self._sent.setdefault(radio, deque(maxlen=self.most)).append(now)


def pass_kind(packet: Packet) -> PassKind:
    """What the limits of a slow radio count the packet as (L2, L3): a message to a station with text, an ack or rej to a station, or anything else (a telemetry definition, a bulletin and a group's message among them)."""
    decoded = packet.decoded
    if not isinstance(decoded, Message) or bulletin.board_slot(decoded.addressee) is not None:
        return "other"
    if decoded.ack_id is not None or decoded.rej_id is not None:
        return "ack"
    if decoded.text and not message.is_telemetry_definition(decoded.text):
        return "message"
    return "other"


def source_name(source: str) -> str:
    """A station's name as the pass modules compare it: callsign.normal_name, or the upper-cased text when that is not a name it knows."""
    try:
        return normal_name(source)
    except ValueError:
        return source.strip().upper()


class SlowBudget:
    """What one slow radio takes from the pairs: at most SLOW_PASS_MAX frames in SLOW_PASS_WINDOW_SEC, SLOW_PASS_OTHER_MAX of them of kind "other" and SLOW_PASS_PER_SOURCE messages from one source (L2), and a frame of kind "other" once per source in the radio's floor (L3)."""

    def __init__(self, floor_min: int) -> None:
        self._floor = timedelta(minutes=floor_min)
        self._window = timedelta(seconds=SLOW_PASS_WINDOW_SEC)
        self._taken: deque[tuple[datetime, str, PassKind]] = deque()    # the frames of the window: when, from whom, of what kind
        self._others: dict[str, datetime] = {}                          # by source: when its latest frame of kind "other" went out

    def _prune(self, now: datetime) -> None:
        while self._taken and now - self._taken[0][0] >= self._window:
            self._taken.popleft()
        for name in [n for n, at in self._others.items() if now - at >= self._floor]:
            del self._others[name]

    def refusal(self, source: str, kind: PassKind, now: datetime) -> HoldReason | None:
        """What holds the frame now, None when it may go; notes nothing."""
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
        """A frame of that source and kind went out."""
        self._prune(now)
        name = source_name(source)
        self._taken.append((now, name, kind))
        if kind == "other":
            self._others[name] = now
