"""Digipeating between the two radios of a pair.

A packet heard on one radio of a pair goes out once on the other when its path names the pair's
call. The target radio's limits apply and the ack of a passed message goes back once."""
import logging
from collections import Counter
from collections.abc import Collection, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal

from neoaprs import ax25
from neoaprs.callsign import parse_call
from neoaprs.clock import Clock, utcnow
from neoaprs.config import Config
from neoaprs.crossrule import back_path, cross, message_id, not_to_pass, slow_channel, spliced
from neoaprs.interlock import Interlock
from neoaprs.packet import DuplicateKey, Message, Packet, duplicate_key
from neoaprs.pairsetting import PairSpec, may_pair, own_calls
from neoaprs.policy import DIGI_DUPLICATE_SEC
from neoaprs.radiotype import RadioId
from neoaprs.recent import Recent
from neoaprs.route import INTERNET_MARKERS
from neoaprs.services.common import ConfigSource
from neoaprs.services.passback import Passed, PassedMessages
from neoaprs.services.passlimits import SLOW_HANDOVER_SEC, Burst, SlowBudget, pass_kind
from neoaprs.services.radioset import AirRadio, RadioPick
from neoaprs.signal import Signal
from neoaprs.tnc2line import text_of
from neoaprs.tncwatchdog import PassCount

log = logging.getLogger("neoaprs.digipeater")

# Reasons a slow radio takes no frame that a waiting frame sits out.
WAITS_FOR = frozenset({"radio.transmitting", "radio.channel_busy"})
HELD_WORDS = {"budget": "the radio took the most frames it takes from the pairs in 5 minutes", "share": "the station's share of messages in 5 minutes went out",
              "floor": "a packet of the station that is no message went out within the radio's floor", "burst": "the most frames the radio sends again in a burst went out",
              "busy": "the radio was keyed or busy for too long, or another frame waits for it"}

Ready = Literal["now", "wait", "no"]


@dataclass(frozen=True)
class PairRow:
    """One direction of a pair: a packet heard on `heard` naming `call` goes out on `sent`."""
    heard: RadioId
    sent: RadioId
    call: tuple[str, int]


@dataclass(frozen=True)
class _Offer:
    """A frame a row would send, with its source packet, duplicate key and original path."""
    row: PairRow
    frame: ax25.Frame
    raw: bytes
    packet: Packet
    key: DuplicateKey
    was: str


def _passes(pair: PairSpec, config: Config, on: Collection[RadioId], own_ssid: int, ssids: Counter[int | None]) -> bool:
    """Return whether the enabled pair passes now: it has a distinct SSID and both radios are on."""
    low, high = config.radio(pair.low), config.radio(pair.high)
    if pair.ssid in (None, own_ssid) or ssids[pair.ssid] > 1 or pair.low not in on or pair.high not in on:
        return False
    return low is not None and high is not None and may_pair(low, high)


def rows_in_force(config: Config, senders: Sequence[AirRadio]) -> tuple[PairRow, ...]:
    """Return both directions of each passing pair (contract 1.1), ordered by (low, high)."""
    try:
        base, own_ssid = parse_call(config.station_call)
    except ValueError:
        return ()
    on = {radio.id for radio in senders}
    enabled = sorted((pair for pair in config.pairs if pair.enabled), key=lambda pair: (pair.low, pair.high))
    ssids = Counter(pair.ssid for pair in enabled)
    rows: list[PairRow] = []
    for pair in enabled:
        if pair.ssid is not None and _passes(pair, config, on, own_ssid, ssids):
            rows += [PairRow(pair.low, pair.high, (base, pair.ssid)), PairRow(pair.high, pair.low, (base, pair.ssid))]
    return tuple(rows)


def _key(packet: Packet) -> DuplicateKey:
    return duplicate_key(packet.source, packet.destination, packet.info)


def own_call(call: str) -> tuple[str, int] | None:
    """Return the call as (call, SSID), or None if it does not parse."""
    try:
        return parse_call(call)
    except ValueError:
        return None


def _calls(calls: Collection[str]) -> set[tuple[str, int]]:
    """Return the calls as (call, SSID), skipping those that do not parse."""
    return {parsed for call in calls if (parsed := own_call(call)) is not None}


def _answered(packet: Packet) -> str | None:
    """Return the message id an ack or rej answers; None for any other packet."""
    decoded = packet.decoded
    if not isinstance(decoded, Message):
        return None
    return decoded.ack_id if decoded.ack_id is not None else decoded.rej_id


class Passer:
    def __init__(self, radios: RadioPick, config: ConfigSource, interlock: Interlock, burst: Burst, counted: Signal[[RadioId]], clock: Clock = utcnow) -> None:
        self._radios = radios
        self._config = config
        self._interlock = interlock
        self._burst = burst
        self._counted = counted
        self._clock = clock
        # Per radio: packets heard and sent lately (N3); packets its limits held lately.
        self._tables: dict[RadioId, Recent[DuplicateKey]] = {}
        self._kept: dict[RadioId, Recent[DuplicateKey]] = {}
        # Per radio: when the latest frame was handed to it (L4 gap).
        self._handed: dict[RadioId, datetime] = {}
        # Per slow radio: the one frame waiting for it (L4); floor and budget (L2, L3).
        self._waiting: dict[RadioId, _Offer] = {}
        self._budgets: dict[RadioId, tuple[int, SlowBudget]] = {}
        self._passed = PassedMessages()
        # (heard, sent, reason) already logged at INFO.
        self._told: set[tuple[RadioId, RadioId, str]] = set()

    def table(self, radio: RadioId) -> Recent[DuplicateKey]:
        """Return the radio's table of packets heard and sent lately (N3)."""
        return self._tables.setdefault(radio, Recent(DIGI_DUPLICATE_SEC))

    def _held_table(self, radio: RadioId) -> Recent[DuplicateKey]:
        return self._kept.setdefault(radio, Recent(DIGI_DUPLICATE_SEC))

    def on_packet(self, packet: Packet) -> None:
        """Note an on-air packet in its radio's table; pass a heard one or send its ack back."""
        # A packet with no radio is no request (N8).
        if not packet.on_air or packet.radio_id is None:
            return
        now = self._clock()
        self.table(packet.radio_id).note(_key(packet), now)
        if packet.direction == "out":
            self._handed[packet.radio_id] = now
            return
        try:
            heard = ax25.decode(packet.raw)
        except ax25.Ax25Error:
            return
        if not self._request(packet.radio_id, heard, packet.raw, packet, now):
            self._back(packet.radio_id, heard, packet, now)

    def sent_on(self, radio: AirRadio, frame: ax25.Frame, raw: bytes, packet: Packet) -> None:
        """Offer a frame sent on the radio to its rows as if heard there (P6, not M2)."""
        # A packet from the internet was never on air, so nothing of it crosses.
        if packet.on_air:
            self._request(radio.id, frame, raw, packet, self._clock())

    def tick(self) -> None:
        """Send each waiting frame once its radio can take it (L4), or drop or hold it."""
        now = self._clock()
        for radio in list(self._waiting):
            if (offer := self._waiting.get(radio)) is not None:
                self._try(radio, offer, now)

    def drop_waiting(self) -> None:
        """Drop waiting frames without counting them."""
        self._waiting.clear()

    def _request(self, heard_on: RadioId, frame: ax25.Frame, raw: bytes, packet: Packet, now: datetime) -> bool:
        """Offer the frame to the row whose call is its first unused hop (P1); return if one did."""
        config = self._config()
        ours = _calls(own_calls(config.station_call, config.pairs))
        for row in rows_in_force(config, self._radios.senders()):
            if row.heard == heard_on and (out := cross(frame, row.call, ours)) is not None:
                self._offer(_Offer(row, out, spliced(raw, frame, out), packet, _key(packet), frame.path_text), now)
                return True
        return False

    def _back(self, heard_on: RadioId, heard: ax25.Frame, packet: Packet, now: datetime) -> None:
        """Send an ack or rej for a passed message back once to the radio it came from (M2)."""
        decoded, answered = packet.decoded, _answered(packet)
        if not isinstance(decoded, Message) or answered is None:
            return
        # Not taken yet: only a copy that goes uses the entry up.
        passed = self._passed.answer(packet.source, decoded.addressee, answered, heard_on, now, take=False)
        if passed is None:
            return
        config = self._config()
        row = next((r for r in rows_in_force(config, self._radios.senders()) if (r.heard, r.sent) == (heard_on, passed.heard_on)), None)
        if row is None or (heard.source.call, heard.source.ssid) in _calls(own_calls(config.station_call, config.pairs)):
            return
        if any(hop.call in INTERNET_MARKERS or (hop.repeated and (hop.call, hop.ssid) == row.call) for hop in heard.path):
            return
        path = back_path(heard.path, row.call)
        if len(path) > ax25.MAX_PATH:
            log.debug("the ack of %s is not passed back: its path would have %d hops, AX.25 carries %d", heard.source, len(path), ax25.MAX_PATH)
            return
        out = replace(heard, path=path)
        # With no path the source carried the end-of-address mark, which must not stay.
        raw = spliced(packet.raw, heard, out) if heard.path else ax25.encode(out)
        self._passed.forget(passed)
        self._offer(_Offer(row, out, raw, packet, _key(packet), heard.path_text), now)

    def _offer(self, offer: _Offer, now: datetime) -> None:
        """Check an offer (N6, N9, N3, N7, L1 to L3), then send, wait or hold it (L4)."""
        row, packet = offer.row, offer.packet
        target = self._radios.get(row.sent)
        if target is None:
            return
        config = self._config()
        if not_to_pass(packet, own_calls(config.station_call, config.pairs), target.allowed.paths) or self._interlock.refused("digipeat") is not None:
            return
        if self._duplicate(target.id, offer.key, now):
            return
        if (why := target.limits.too_long(offer.raw, text_of(offer.frame))) is not None:
            self._hold(offer, target, now, "too long", f"too long: {why}")
            return
        if (reason := self._limit(target, packet, now)) is not None:
            self._hold(offer, target, now, reason)
            return
        if target.id in self._waiting:
            self._hold(offer, target, now, "busy")
            return
        ready = self._ready(target, now)
        if ready == "now":
            self._go(target, offer, now)
        elif ready == "wait":
            self._waiting[target.id] = offer
            log.debug("%s: a packet of %s from %s waits: %s", target.name, packet.source, self._name(row.heard), target.why_unusable() or "a frame was handed to it a moment ago")
        else:
            log.debug("%s: a packet of %s from %s is not passed: %s", target.name, packet.source, self._name(row.heard), target.why_unusable())

    def _try(self, radio: RadioId, offer: _Offer, now: datetime) -> None:
        """Handle the waiting frame at a tick: drop it uncounted, hold it, or send it."""
        target, packet = self._radios.get(radio), offer.packet
        if target is None or offer.row not in rows_in_force(self._config(), self._radios.senders()) or self._interlock.refused("digipeat") is not None or self.table(radio).lately(offer.key, now):
            del self._waiting[radio]
            log.debug("a packet of %s waiting for %s is dropped: its pair, the radio or the station no longer passes it, or the radio heard it", packet.source, self._name(radio))
            return
        if (now - packet.heard_at).total_seconds() > DIGI_DUPLICATE_SEC:
            del self._waiting[radio]
            self._hold(offer, target, now, "busy")
            return
        if (reason := self._limit(target, packet, now)) is not None:
            del self._waiting[radio]
            self._hold(offer, target, now, reason)
            return
        ready = self._ready(target, now)
        if ready == "wait":
            return
        del self._waiting[radio]
        if ready == "now":
            self._go(target, offer, now)
        else:
            log.debug("%s: a packet of %s that waited is not passed: %s", target.name, packet.source, target.why_unusable())

    def _duplicate(self, radio: RadioId, key: DuplicateKey, now: datetime) -> bool:
        """Return whether the radio heard, sent, holds or awaits the packet lately (N3)."""
        waiting = self._waiting.get(radio)
        return self.table(radio).lately(key, now) or self._held_table(radio).lately(key, now) or (waiting is not None and waiting.key == key)

    def _budget(self, target: AirRadio) -> SlowBudget:
        """Return the slow radio's budget, recreated when its floor changes."""
        floor = target.limits.beacon_min_min
        kept = self._budgets.get(target.id)
        if kept is None or kept[0] != floor:
            kept = self._budgets[target.id] = (floor, SlowBudget(floor))
        return kept[1]

    def _limit(self, target: AirRadio, packet: Packet, now: datetime) -> str | None:
        """Return the limit holding the frame (budget, share, floor, burst), or None."""
        if slow_channel(target.limits):
            return self._budget(target).refusal(packet.source, pass_kind(packet), now)
        return "burst" if self._burst.full(target.id, now) else None

    def _ready(self, target: AirRadio, now: datetime) -> Ready:
        """Return "now", "wait" (slow radio keyed, busy or just handed a frame) or "no"."""
        slow = slow_channel(target.limits)
        if not target.usable:
            return "wait" if slow and getattr(target.why_unusable(), "code", "") in WAITS_FOR else "no"
        handed = self._handed.get(target.id)
        if slow and handed is not None and (now - handed).total_seconds() < SLOW_HANDOVER_SEC:
            return "wait"
        return "now"

    def _go(self, target: AirRadio, offer: _Offer, now: datetime) -> None:
        """Send the frame; if taken, update tables, limits and counts and offer it to its rows."""
        packet = offer.packet
        if not target.send_frame(offer.frame, offer.raw):
            log.debug("%s: the frame of %s passed from %s was not taken", target.name, packet.source, self._name(offer.row.heard))
            return
        self.table(target.id).note(offer.key, now)
        self._handed[target.id] = now
        if slow_channel(target.limits):
            self._budget(target).take(packet.source, pass_kind(packet), now)
        else:
            self._burst.take(target.id, now)
        target.stats.digipeated += 1
        target.stats.digipeated_at = now
        count = target.stats.passed.setdefault(offer.row.heard, PassCount())
        count.sent += 1
        count.sent_at = now
        self._counted.emit(target.id)
        log.info("passed %s>%s from %s to %s: the path %s is sent as %s", packet.source, packet.destination, self._name(offer.row.heard), target.name, offer.was, offer.frame.path_text)
        self._remember(offer, now)
        self.sent_on(target, offer.frame, offer.raw, packet)

    def _remember(self, offer: _Offer, now: datetime) -> None:
        """Keep a passed message for its ack (M2); a passed ack or rej uses up the entry."""
        packet, decoded = offer.packet, offer.packet.decoded
        if not isinstance(decoded, Message):
            return
        if (msg_id := message_id(packet)) is not None:
            self._passed.note(Passed(packet.source, decoded.addressee, msg_id, offer.row.heard, offer.row.sent, now))
        elif (answered := _answered(packet)) is not None:
            self._passed.answer(packet.source, decoded.addressee, answered, offer.row.heard, now)

    def _hold(self, offer: _Offer, target: AirRadio, now: datetime, reason: str, words: str = "") -> None:
        """Count a frame left unsent; log the first of each reason per direction at INFO."""
        row = offer.row
        self._held_table(target.id).note(offer.key, now)
        count = target.stats.passed.setdefault(row.heard, PassCount())
        if reason == "too long":
            count.too_long += 1
        else:
            count.held += 1
        self._counted.emit(target.id)
        told = (row.heard, row.sent, reason)
        level = logging.DEBUG if told in self._told else logging.INFO
        self._told.add(told)
        log.log(level, "%s: a packet of %s from %s is not passed: %s", target.name, offer.packet.source, self._name(row.heard), words or HELD_WORDS[reason])

    def _name(self, radio: RadioId) -> str:
        found = self._radios.get(radio)
        return found.name if found is not None else f"radio {radio}"
