"""The fill-in digipeater: a packet heard on a radio is sent again, once, if its path asks for us.

Never repeated: our own packets, internet packets and duplicates. Nothing goes while the
interlock refuses or the radio is unusable; a burst limit applies per outgoing radio.
"""

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

TICK_SEC = 1.0
FILL_IN = ("WIDE1", 1)


@dataclass(frozen=True)
class DigiRow:
    """One row: what is heard on radio `heard` is sent again on radio `sent`."""

    heard: RadioId
    sent: RadioId


def repeats(radio: AirRadio) -> bool:
    """Whether the radio's type may digipeat and its `digipeat` setting is on."""
    if not radio.allowed.digipeat:
        return False
    try:
        return bool(radio.choice("digipeat"))
    except RadioError:
        return False


def digi_rows(radios: Iterable[AirRadio]) -> tuple[DigiRow, ...]:
    """Return a "heard on A, sent on A" row for each of these radios that repeats."""
    return tuple(DigiRow(radio.id, radio.id) for radio in radios if repeats(radio))


def repeat(frame: ax25.Frame, ours: tuple[str, int]) -> ax25.Frame | None:
    """Return the frame as we repeat it (only the path differs), or None; no duplicate check."""
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
    return replace(frame, path=path[:at] + (used,) + path[at + 1 :])


class Digipeater:
    def __init__(self, radios: RadioPick, config: ConfigSource, clock: Clock = utcnow) -> None:
        self._radios = radios
        self._config = config
        self._interlock = Interlock(config)
        self.clock = clock
        self._seen: dict[RadioId, Recent[DuplicateKey]] = {}
        self.burst = Burst(BURST_MAX, BURST_WINDOW_SEC)
        self.counted: Signal[[RadioId]] = Signal("digipeater.counted")
        self.passer = Passer(radios, config, self._interlock, self.burst, self.counted, lambda: self.clock())
        self.tasks = TaskSet(log, "digipeater")

    async def start(self) -> None:
        """Start the timer for frames waiting on a slow radio."""
        self.tasks.spawn(every(TICK_SEC, self.passer.tick, "the digipeater's wait"), "digipeater-wait")

    async def stop(self) -> None:
        """Stop the timer and drop waiting frames without counting them."""
        await self.tasks.cancel_all()
        self.passer.drop_waiting()

    def seen_on(self, radio: RadioId) -> Recent[DuplicateKey]:
        """The outgoing radio's table of packets heard or sent lately."""
        return self._seen.setdefault(radio, Recent(DIGI_DUPLICATE_SEC))

    def rows(self) -> tuple[DigiRow, ...]:
        """The rows in force for the enabled radios."""
        return digi_rows(self._radios.enabled())

    def on_packet(self, packet: Packet) -> None:
        """Note a packet for each row's duplicate check and repeat it if it asks for us."""
        if not packet.on_air:
            return
        came = FM_ID if packet.radio_id is None else packet.radio_id
        for row in self.rows():
            if row.heard == came and (radio := self._radios.get(row.sent)) is not None:
                self._row(radio, packet)
        self.passer.on_packet(packet)

    def _row(self, radio: AirRadio, packet: Packet) -> None:
        """Run the packet through one row, `radio` being its outgoing radio."""
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

    def _send(
        self, radio: AirRadio, heard: ax25.Frame, frame: ax25.Frame, raw: bytes, packet: Packet, now: datetime
    ) -> None:
        if not radio.usable:
            log.debug("not digipeating %s: %s", heard.tnc2(), radio.why_unusable())
            return
        if self.burst.full(radio.id, now):
            log.debug(
                "not digipeating %s: %d frames went out in the last %g s", heard.tnc2(), BURST_MAX, BURST_WINDOW_SEC
            )
            radio.stats.digipeat_held += 1
            return
        if not radio.send_frame(frame, raw):
            log.warning("the digipeated frame of %s was not sent: the TNC would not take it", heard.source)
            return
        self.burst.take(radio.id, now)
        radio.stats.digipeated += 1
        radio.stats.digipeated_at = now
        log.info(
            "digipeated %s>%s: the path %s is sent as %s",
            heard.source,
            heard.destination,
            heard.path_text,
            frame.path_text,
        )
        self.passer.sent_on(radio, frame, raw, packet)
