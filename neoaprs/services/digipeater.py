"""The fill-in digipeater, switched on for each radio by its own `digipeat` (radio 1's is `digi/enabled`; off unless the operator turns it on): a packet heard on the radio is sent again, once, when its path asks for a hop that we can be.

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

The digipeater is a table of rows "heard on radio A, sent on radio B" (`DigiRow`, plan rule 3.4). Only A to A is made: one row for each enabled radio whose type may repeat (`allowed.digipeat`: no digipeater
on HF, where every station hears every frame and a repeat would only fill the channel) and whose own `digipeat` the operator turned on (radio 1's is `digi/enabled`). A packet heard on a radio is repeated by
the rows of that radio, and the duplicate check, the burst limit and the counts (the radio's `stats`) are each outgoing radio's own. The rows from one radio to another are services/passrows.py's."""
import logging
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime

from neoaprs import ax25
from neoaprs.clock import Clock, utcnow
from neoaprs.crossrule import spliced
from neoaprs.interlock import Interlock
from neoaprs.packet import DuplicateKey, Packet, duplicate_key
from neoaprs.policy import DIGI_DUPLICATE_SEC
from neoaprs.radiospec import RadioError
from neoaprs.radiotype import FM_ID, RadioId
from neoaprs.recent import Recent
from neoaprs.route import INTERNET_MARKERS
from neoaprs.services.common import ConfigSource
from neoaprs.services.passlimits import BURST_MAX, BURST_WINDOW_SEC, Burst
from neoaprs.services.passrows import Passer, own_call
from neoaprs.services.radioset import AirRadio, RadioPick
from neoaprs.signal import Signal
from neoaprs.tasks import TaskSet, every

log = logging.getLogger("neoaprs.digipeater")

TICK_SEC = 1.0                         # how often the frame that waits for a slow radio is looked at (services/passrows.py)
FILL_IN = ("WIDE1", 1)


@dataclass(frozen=True)
class DigiRow:
    """One row of the digipeater: what is heard on the radio `heard` is sent again on the radio `sent` (today always the same radio)."""
    heard: RadioId
    sent: RadioId


def repeats(radio: AirRadio) -> bool:
    """Whether the radio repeats what it hears: its type may digipeat and its own `digipeat` is on (a type that may has the setting; a radio that cannot read it repeats nothing)."""
    if not radio.allowed.digipeat:
        return False
    try:
        return bool(radio.choice("digipeat"))
    except RadioError:
        return False


def digi_rows(radios: Iterable[AirRadio]) -> tuple[DigiRow, ...]:
    """The rows of the digipeater for these radios (the enabled ones), in their order: "heard on A, sent on A" for each radio that repeats."""
    return tuple(DigiRow(radio.id, radio.id) for radio in radios if repeats(radio))


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


class Digipeater:
    def __init__(self, radios: RadioPick, config: ConfigSource, clock: Clock = utcnow) -> None:
        self._radios = radios                                       # the station's radios (the registry): each radio's counters are its `stats`
        self._config = config
        self._interlock = Interlock(config)
        self.clock = clock
        self._seen: dict[RadioId, Recent[DuplicateKey]] = {}          # by outgoing radio: the packets heard or sent on it lately, for the duplicate check
        self.burst = Burst(BURST_MAX, BURST_WINDOW_SEC)             # by outgoing radio: the frames it sent again lately, the fill-in's and the pairs' (L1)
        self.counted: Signal[[RadioId]] = Signal("digipeater.counted")     # a radio's counts of the pairs changed (a held frame changes no counter of the line)
        self.passer = Passer(radios, config, self._interlock, self.burst, self.counted, lambda: self.clock())
        self.tasks = TaskSet(log, "digipeater")

    async def start(self) -> None:
        """The timer of the frame that waits for a slow radio (services/passrows.py)."""
        self.tasks.spawn(every(TICK_SEC, self.passer.tick, "the digipeater's wait"), "digipeater-wait")

    async def stop(self) -> None:
        """The timer ends; a frame that waits is dropped, counted nothing."""
        await self.tasks.cancel_all()
        self.passer.drop_waiting()

    def seen_on(self, radio: RadioId) -> Recent[DuplicateKey]:
        """The outgoing radio's table of what was heard or sent on it lately."""
        return self._seen.setdefault(radio, Recent(DIGI_DUPLICATE_SEC))

    def rows(self) -> tuple[DigiRow, ...]:
        """The rows in force: one "heard on A, sent on A" for each enabled radio that repeats (`digi_rows`)."""
        return digi_rows(self._radios.enabled())

    def on_packet(self, packet: Packet) -> None:
        """A radio heard a packet, or sent one: each row of that radio remembers it for the duplicate check of its outgoing radio, and repeats it there when it asks for us (ours is never repeated)."""
        if not packet.on_air:                                       # (a packet from the internet was never on the air: there is nothing to repeat)
            return
        came = FM_ID if packet.radio_id is None else packet.radio_id
        for row in self.rows():
            if row.heard == came and (radio := self._radios.get(row.sent)) is not None:
                self._row(radio, packet)
        self.passer.on_packet(packet)                               # (the rows between two radios after the fill-in's)

    def _row(self, radio: AirRadio, packet: Packet) -> None:
        """The packet through one row, `radio` its outgoing radio."""
        config = self._config()
        now = self.clock()
        duplicate = self.seen_on(radio.id).seen(duplicate_key(packet.source, packet.destination, packet.info), now)
        if packet.direction != "in" or duplicate:
            return
        ours = own_call(config.station_call)
        if ours is None:
            self._interlock.refused("digipeat")
            return
        try:
            heard = ax25.decode(packet.raw)
        except ax25.Ax25Error:
            return
        if (frame := repeat(heard, ours)) is None or self._interlock.refused("digipeat"):
            return
        self._send(radio, heard, frame, spliced(packet.raw, heard, frame), packet, now)

    def _send(self, radio: AirRadio, heard: ax25.Frame, frame: ax25.Frame, raw: bytes, packet: Packet, now: datetime) -> None:
        if not radio.usable:
            log.debug("not digipeating %s: %s", heard.tnc2(), radio.why_unusable())
            return
        if self.burst.full(radio.id, now):
            log.debug("not digipeating %s: %d frames went out in the last %g s", heard.tnc2(), BURST_MAX, BURST_WINDOW_SEC)
            radio.stats.digipeat_held += 1
            return
        if not radio.send_frame(frame, raw):
            log.warning("the digipeated frame of %s was not sent: the TNC would not take it", heard.source)
            return
        self.burst.take(radio.id, now)
        radio.stats.digipeated += 1
        radio.stats.digipeated_at = now
        log.info("digipeated %s>%s: the path %s is sent as %s", heard.source, heard.destination, heard.path_text, frame.path_text)
        self.passer.sent_on(radio, frame, raw, packet)              # (a frame sent again whose next hop is a pair's call crosses too: P6)


