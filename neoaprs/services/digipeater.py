"""The fill-in digipeater, switched on by `digi/enabled` (off unless the operator turns it on): a packet heard on the radio is sent again, once, when its path asks for a hop that we can be.

The first digipeater of the path that has not been used yet decides. `WIDE1-1` (the fill-in hop) is replaced by our call marked as used: `OH2XYZ>APRS,WIDE1-1,WIDE2-1` goes out as `OH2XYZ>APRS,OH2GBA*,WIDE2-1`.
Our own call, with our SSID (a station that routes through us on purpose), is marked as used where it stands. Any other first hop (WIDE2-1, WIDE2-2, another station's call) is not ours to be, and a path with
no unused hop is finished: nothing is sent. Never sent again: a packet from our own call, one that already shows our call as a used hop, one whose own path says it came from the internet (TCPIP or TCPXX;
NOGATE and RFONLY only ask iGates to keep it off the internet, so they are digipeated), and a duplicate: the same source, destination and information field heard or sent by us
within the last DUPLICATE_SEC, whatever the path and the destination's SSID (WB2OSZ's digipeater algorithm: source, destination without its SSID and information field). A third-party packet (`}`, an iGate putting internet traffic on the air) is repeated like any other: only the path
before the `}` counts (APRS 1.2, chapter 17), so the TCPIP inside it does not. The frame is the one that was heard with only the path changed: the bytes of the destination and the source (their command/response
and reserved bits too), control, PID and information field are the bytes that arrived, and only the path is encoded again.

Nothing goes while the interlock refuses (no call set: config.can_transmit) or the radio is not usable. A fill-in is of use only at once, so it does not wait for the sender's pause (services/sender.py) of
ten seconds between our scheduled frames; instead at most BURST_MAX digipeated frames go out in any BURST_WINDOW_SEC and the rest are dropped (the TNC's own channel access, its random
delay of PERSIST and SLOTTIME, still decides when a frame is on the air: a software fill-in is never as quick as one in the TNC)."""
import logging
from collections import deque
from dataclasses import replace
from datetime import datetime

from neoaprs import ax25
from neoaprs.callsign import parse_call
from neoaprs.clock import Clock, utcnow
from neoaprs.interlock import Interlock
from neoaprs.packet import DuplicateKey, Packet, duplicate_key
from neoaprs.policy import DIGI_DUPLICATE_SEC
from neoaprs.recent import Recent
from neoaprs.route import INTERNET_MARKERS
from neoaprs.services.common import ConfigSource, Radio
from neoaprs.tncwatchdog import TncStats

log = logging.getLogger("neoaprs.digipeater")

BURST_MAX = 4
BURST_WINDOW_SEC = 10.0
FILL_IN = ("WIDE1", 1)
ADDRESS_LEN = 7


def repeat(frame: ax25.Frame, ours: tuple[str, int]) -> ax25.Frame | None:
    """The frame as we send it again (only the path differs), or None when it is not ours to repeat: the rules of the module's head, except the duplicate check."""
    if not frame.is_ui or (frame.source.call, frame.source.ssid) == ours:
        return None
    path = frame.path
    if any(hop.call in INTERNET_MARKERS or (hop.repeated and (hop.call, hop.ssid) == ours) for hop in path):
        return None
    at = next((i for i, hop in enumerate(path) if not hop.repeated), None)
    if at is None:
        return None
    hop = (path[at].call, path[at].ssid)
    if hop != FILL_IN and hop != ours:
        return None
    used = ax25.Address(ours[0], ours[1], repeated=True)
    return replace(frame, path=path[:at] + (used,) + path[at + 1:])


def spliced(raw: bytes, heard: ax25.Frame, frame: ax25.Frame) -> bytes:
    """The bytes that were heard (`heard` is what they decode to) with the path of `frame` in place of theirs; everything else is as it arrived."""
    start = 2 * ADDRESS_LEN
    return raw[:start] + ax25.encode_path(frame.path) + raw[start + ADDRESS_LEN * len(heard.path):]


class Digipeater:
    def __init__(self, tnc: Radio, config: ConfigSource, clock: Clock = utcnow, stats: TncStats | None = None) -> None:
        self._tnc = tnc
        self._config = config
        self._interlock = Interlock(config)
        self.clock = clock
        self._stats = stats                                          # the Tnc's counters: `digipeated` counts what went out
        self._seen: Recent[DuplicateKey] = Recent(DIGI_DUPLICATE_SEC)              # the packets heard or sent lately, for the duplicate check
        self._sent: deque[datetime] = deque(maxlen=BURST_MAX)        # when the latest digipeated frames went out

    def on_packet(self, packet: Packet) -> None:
        """The Tnc heard a packet, or sent one (it is remembered for the duplicate check, and ours is never repeated)."""
        config = self._config()
        if not config.digi_enabled or not packet.on_air:
            return                                                   # (a packet from the internet was never on the air: there is nothing to repeat)
        now = self.clock()
        duplicate = self._seen.seen(duplicate_key(packet.source, packet.destination, packet.info), now)
        if packet.direction != "in" or duplicate:
            return
        ours = _own(config.station_call)
        if ours is None:
            self._interlock.refused("digipeat")
            return
        try:
            heard = ax25.decode(packet.raw)
        except ax25.Ax25Error:
            return
        if (frame := repeat(heard, ours)) is None or self._interlock.refused("digipeat"):
            return
        self._send(heard, frame, spliced(packet.raw, heard, frame), now)

    def _send(self, heard: ax25.Frame, frame: ax25.Frame, raw: bytes, now: datetime) -> None:
        if not self._tnc.usable:
            log.debug("not digipeating %s: %s", heard.tnc2(), self._tnc.why_unusable())
            return
        while self._sent and (now - self._sent[0]).total_seconds() >= BURST_WINDOW_SEC:
            self._sent.popleft()
        if len(self._sent) >= BURST_MAX:
            log.debug("not digipeating %s: %d frames went out in the last %g s", heard.tnc2(), BURST_MAX, BURST_WINDOW_SEC)
            if self._stats is not None:
                self._stats.digipeat_held += 1
            return
        if not self._tnc.send_frame(frame, raw):
            log.warning("the digipeated frame of %s was not sent: the TNC would not take it", heard.source)
            return
        self._sent.append(now)
        if self._stats is not None:
            self._stats.digipeated += 1
            self._stats.digipeated_at = now
        log.info("digipeated %s>%s: the path %s is sent as %s", heard.source, heard.destination, heard.path_text, frame.path_text)


def _own(call: str) -> tuple[str, int] | None:
    try:
        return parse_call(call)
    except ValueError:
        return None
