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
delay of PERSIST and SLOTTIME, still decides when a frame is on the air: a software fill-in is never as quick as one in the TNC).

The radios are the station's (services/radioset.py's `RadioPick`): a packet heard on a radio is repeated on that radio, and the duplicate check, the burst limit and the counts (the radio's `stats`) are each
radio's own. Only radio 1, the FM radio, repeats, where its type allows it (no digipeater on HF: every station hears every frame, a repeat would only fill the channel) and `digi/enabled` is on."""
import logging
from collections import deque
from dataclasses import replace
from datetime import datetime

from neoaprs import ax25
from neoaprs.callsign import parse_call
from neoaprs.clock import Clock, utcnow
from neoaprs.interlock import Interlock
from neoaprs.config import Config
from neoaprs.packet import DuplicateKey, Packet, duplicate_key
from neoaprs.policy import DIGI_DUPLICATE_SEC
from neoaprs.radiotype import FM_ID, RadioId
from neoaprs.recent import Recent
from neoaprs.route import INTERNET_MARKERS
from neoaprs.services.common import ConfigSource
from neoaprs.services.radioset import AirRadio, RadioPick

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
    def __init__(self, radios: RadioPick, config: ConfigSource, clock: Clock = utcnow) -> None:
        self._radios = radios                                       # the station's radios (the registry): each radio's counters are its `stats`
        self._config = config
        self._interlock = Interlock(config)
        self.clock = clock
        self._seen: dict[RadioId, Recent[DuplicateKey]] = {}          # by radio: the packets heard or sent on it lately, for the duplicate check
        self._sent: dict[RadioId, deque[datetime]] = {}             # by radio: when the latest frames it digipeated went out

    def seen_on(self, radio: RadioId) -> Recent[DuplicateKey]:
        """The radio's table of what was heard or sent on it lately."""
        return self._seen.setdefault(radio, Recent(DIGI_DUPLICATE_SEC))

    def on_packet(self, packet: Packet) -> None:
        """A radio heard a packet, or sent one (it is remembered for the duplicate check of that radio, and ours is never repeated)."""
        config = self._config()
        radio = self._radios.get(FM_ID if packet.radio_id is None else packet.radio_id) if packet.on_air else None
        if radio is None or not self._repeats(radio, config):     # (a packet from the internet was never on the air: there is nothing to repeat)
            return
        now = self.clock()
        duplicate = self.seen_on(radio.id).seen(duplicate_key(packet.source, packet.destination, packet.info), now)
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
        self._send(radio, heard, frame, spliced(packet.raw, heard, frame), now)

    @staticmethod
    def _repeats(radio: AirRadio, config: Config) -> bool:
        """Whether this radio repeats what it hears: radio 1 (the FM radio) alone, while its type allows a digipeater and digi/enabled is on."""
        return radio.id == FM_ID and radio.allowed.digipeat and config.digi_enabled

    def _send(self, radio: AirRadio, heard: ax25.Frame, frame: ax25.Frame, raw: bytes, now: datetime) -> None:
        if not radio.usable:
            log.debug("not digipeating %s: %s", heard.tnc2(), radio.why_unusable())
            return
        sent = self._sent.setdefault(radio.id, deque(maxlen=BURST_MAX))
        while sent and (now - sent[0]).total_seconds() >= BURST_WINDOW_SEC:
            sent.popleft()
        if len(sent) >= BURST_MAX:
            log.debug("not digipeating %s: %d frames went out in the last %g s", heard.tnc2(), BURST_MAX, BURST_WINDOW_SEC)
            radio.stats.digipeat_held += 1
            return
        if not radio.send_frame(frame, raw):
            log.warning("the digipeated frame of %s was not sent: the TNC would not take it", heard.source)
            return
        sent.append(now)
        radio.stats.digipeated += 1
        radio.stats.digipeated_at = now
        log.info("digipeated %s>%s: the path %s is sent as %s", heard.source, heard.destination, heard.path_text, frame.path_text)


def _own(call: str) -> tuple[str, int] | None:
    try:
        return parse_call(call)
    except ValueError:
        return None
