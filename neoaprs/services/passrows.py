"""The rows between two radios of the digipeater: a packet heard on one radio of a pair goes out once on the other when its path names the pair's call (aprs-reference/cross-radio-digipeat-plan.md section 3),
with each radio's own table of what it heard and sent, the limits of the radio it goes out on, one frame that waits for a slow radio keyed, busy or just handed a frame, the ack of a message passed going back
once, and the counts by pair and direction in the radio's stats.

A pair passes only while its Enable is on, both its radios are among the senders, they may still pair (both transmit, both Dummy or both real), the station call parses and the pair's call is neither the
station call nor another enabled pair's (`rows_in_force`). What is never passed, the request and its step are crossrule.py's; the limits and the kinds they count are passlimits.py's, the messages whose ack goes
back passback.py's. Nothing here is told at WARNING: the operator can do nothing about a frame held, too long or not taken (the first of each reason for each direction is told at INFO).

The one case the rows cannot guard: a frame of our own (an ack that Acks.flush sends, a message attempt of Retries.tick) handed to a slow radio right after a passed frame. Those go on the services' own pace,
which the gap after a handover (SLOW_HANDOVER_SEC) does not hold back; the gap holds only what the rows send."""
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

WAITS_FOR = frozenset({"radio.transmitting", "radio.channel_busy"})   # the codes of why a slow radio takes no frame now that one passed frame waits out (mercurychannel.TRANSMITTING, CHANNEL_BUSY)
HELD_WORDS = {"budget": "the radio took the most frames it takes from the pairs in 5 minutes", "share": "the station's share of messages in 5 minutes went out",
              "floor": "a packet of the station that is no message went out within the radio's floor", "burst": "the most frames the radio sends again in a burst went out",
              "busy": "the radio was keyed or busy for too long, or another frame waits for it"}

Ready = Literal["now", "wait", "no"]


@dataclass(frozen=True)
class PairRow:
    """One direction of a pair: what is heard on `heard` and names `call` goes out on `sent`."""
    heard: RadioId
    sent: RadioId
    call: tuple[str, int]


@dataclass(frozen=True)
class _Offer:
    """A frame a row would send: what goes out (its frame and bytes), the packet it was made of, its duplicate key, and the path it had on the radio it came from (for the log)."""
    row: PairRow
    frame: ax25.Frame
    raw: bytes
    packet: Packet
    key: DuplicateKey
    was: str


def _passes(pair: PairSpec, config: Config, on: Collection[RadioId], own_ssid: int, ssids: Counter[int | None]) -> bool:
    """Whether the enabled pair passes now: both radios send, they may pair, and its SSID is neither the station's nor another enabled pair's."""
    low, high = config.radio(pair.low), config.radio(pair.high)
    if pair.ssid in (None, own_ssid) or ssids[pair.ssid] > 1 or pair.low not in on or pair.high not in on:
        return False
    return low is not None and high is not None and may_pair(low, high)


def rows_in_force(config: Config, senders: Sequence[AirRadio]) -> tuple[PairRow, ...]:
    """The rows in force: both directions of each pair that passes now (section 1.1 of the contract), in the order of the pairs (low, high), low to high first."""
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


def _calls(calls: Collection[str]) -> set[tuple[str, int]]:
    """The calls as (call, SSID), those that do not parse left out."""
    out: set[tuple[str, int]] = set()
    for call in calls:
        try:
            out.add(parse_call(call))
        except ValueError:
            pass
    return out


def _answered(packet: Packet) -> str | None:
    """The message id an ack or a rej answers; None for any other packet."""
    decoded = packet.decoded
    if not isinstance(decoded, Message):
        return None
    return decoded.ack_id if decoded.ack_id is not None else decoded.rej_id


class Passer:
    def __init__(self, radios: RadioPick, config: ConfigSource, interlock: Interlock, burst: Burst, counted: Signal[[RadioId]], clock: Clock = utcnow) -> None:
        self._radios = radios
        self._config = config
        self._interlock = interlock                     # the Digipeater's own: the fill-in and the pairs share the one warning line
        self._burst = burst                             # the Digipeater's own: a fast radio's burst is the fill-in's and the pairs' together (L1)
        self._counted = counted
        self._clock = clock
        self._tables: dict[RadioId, Recent[DuplicateKey]] = {}       # by radio: what it heard and sent lately (N3)
        self._kept: dict[RadioId, Recent[DuplicateKey]] = {}         # by radio: the packets its limits held lately, so a copy of one counts nothing
        self._handed: dict[RadioId, datetime] = {}                   # by radio: when the latest frame was handed to it (L4's gap)
        self._waiting: dict[RadioId, _Offer] = {}                    # by slow radio: the one frame that waits for it (L4)
        self._budgets: dict[RadioId, tuple[int, SlowBudget]] = {}     # by slow radio: its floor and its budget (L2, L3)
        self._passed = PassedMessages()                               # the messages passed lately, for their acks (M2)
        self._told: set[tuple[RadioId, RadioId, str]] = set()         # (heard, sent, reason) told at INFO once

    def table(self, radio: RadioId) -> Recent[DuplicateKey]:
        """The radio's own table of what it heard and sent lately (N3)."""
        return self._tables.setdefault(radio, Recent(DIGI_DUPLICATE_SEC))

    def _held_table(self, radio: RadioId) -> Recent[DuplicateKey]:
        return self._kept.setdefault(radio, Recent(DIGI_DUPLICATE_SEC))

    def on_packet(self, packet: Packet) -> None:
        """Every on-air packet with a radio is noted in that radio's table, and an `out` one as that radio's latest handover; one heard is passed by the row whose call its path names, or, when none does and it
        is the ack of a message passed, back once (M2)."""
        if not packet.on_air or packet.radio_id is None:          # (a packet with no radio is no request: N8)
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
        """A frame the station sent again on the radio (the fill-in's or a pair's): offered to that radio's rows as if heard there (P6; never to M2)."""
        if packet.on_air:                                         # (a packet from the internet was never on the air: nothing of it crosses)
            self._request(radio.id, frame, raw, packet, self._clock())

    def tick(self) -> None:
        """The frame that waits for a slow radio goes when the radio can take it, within DIGI_DUPLICATE_SEC of when it was heard and while its row and the interlock still allow it; after that it is held (L4)."""
        now = self._clock()
        for radio in list(self._waiting):
            if (offer := self._waiting.get(radio)) is not None:
                self._try(radio, offer, now)

    def drop_waiting(self) -> None:
        """The frames that wait are dropped, counted nothing (the digipeater stops)."""
        self._waiting.clear()

    # ---- the request (P1) and the ack back (M2)

    def _request(self, heard_on: RadioId, frame: ax25.Frame, raw: bytes, packet: Packet, now: datetime) -> bool:
        """The frame through the rows of the radio it is on: the one whose call is its first unused hop passes it (`cross`). Whether a row found a request in it."""
        config = self._config()
        ours = _calls(own_calls(config.station_call, config.pairs))
        for row in rows_in_force(config, self._radios.senders()):
            if row.heard == heard_on and (out := cross(frame, row.call, ours)) is not None:
                self._offer(_Offer(row, out, spliced(raw, frame, out), packet, _key(packet), frame.path_text), now)
                return True
        return False

    def _back(self, heard_on: RadioId, heard: ax25.Frame, packet: Packet, now: datetime) -> None:
        """An ack or rej heard on a radio for a message a pair passed onto it goes back once to the radio the message came from, with the hops used and the pair's call (M2); N4 does not apply."""
        decoded, answered = packet.decoded, _answered(packet)
        if not isinstance(decoded, Message) or answered is None:
            return
        passed = self._passed.answer(packet.source, decoded.addressee, answered, heard_on, now)
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
        raw = spliced(packet.raw, heard, out) if heard.path else ax25.encode(out)    # (a source that ended the address field must lose that mark)
        self._offer(_Offer(row, out, raw, packet, _key(packet), heard.path_text), now)

    # ---- one offer, through the checks in order

    def _offer(self, offer: _Offer, now: datetime) -> None:
        """What is never passed (N6), the interlock (N9), a duplicate on the target (N3), too long (N7), the target's limits (L1 to L3), and whether it takes the frame now or one waits (L4)."""
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
        """The waiting frame at a tick: dropped (counted nothing) when its row is no longer in force, the interlock refuses or the target heard it meanwhile; held past DIGI_DUPLICATE_SEC or over the
        limits; sent when the target takes it."""
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
        """Whether the radio heard or sent the packet lately, it is the frame that waits for it (N3), or the radio's limits held it lately (a copy counts nothing)."""
        waiting = self._waiting.get(radio)
        return self.table(radio).lately(key, now) or self._held_table(radio).lately(key, now) or (waiting is not None and waiting.key == key)

    def _budget(self, target: AirRadio) -> SlowBudget:
        """The slow radio's budget, made again when its floor changes."""
        floor = target.limits.beacon_min_min
        kept = self._budgets.get(target.id)
        if kept is None or kept[0] != floor:
            kept = self._budgets[target.id] = (floor, SlowBudget(floor))
        return kept[1]

    def _limit(self, target: AirRadio, packet: Packet, now: datetime) -> str | None:
        """What of the target's limits holds the frame now: the budget, a share or the floor of a slow radio, the burst of a fast one; None when it may go."""
        if slow_channel(target.limits):
            return self._budget(target).refusal(packet.source, pass_kind(packet), now)
        return "burst" if self._burst.full(target.id, now) else None

    def _ready(self, target: AirRadio, now: datetime) -> Ready:
        """Whether the target takes the frame now, the frame waits (a slow radio keyed, busy or handed a frame less than SLOW_HANDOVER_SEC ago), or it takes nothing (any other reason)."""
        slow = slow_channel(target.limits)
        if not target.usable:
            return "wait" if slow and getattr(target.why_unusable(), "code", "") in WAITS_FOR else "no"
        handed = self._handed.get(target.id)
        if slow and handed is not None and (now - handed).total_seconds() < SLOW_HANDOVER_SEC:
            return "wait"
        return "now"

    # ---- what went out, and what was held

    def _go(self, target: AirRadio, offer: _Offer, now: datetime) -> None:
        """The frame to the target; when it took it, the target's table, handover, limits and counts, the messages passed, and the frame offered to the target's own rows (P6)."""
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
        """A message passed is kept for its ack (M2); an ack or rej passed uses up the entry of its message."""
        packet, decoded = offer.packet, offer.packet.decoded
        if not isinstance(decoded, Message):
            return
        if (msg_id := message_id(packet)) is not None:
            self._passed.note(Passed(packet.source, decoded.addressee, msg_id, offer.row.heard, offer.row.sent, now))
        elif (answered := _answered(packet)) is not None:
            self._passed.answer(packet.source, decoded.addressee, answered, offer.row.heard, now)

    def _hold(self, offer: _Offer, target: AirRadio, now: datetime, reason: str, words: str = "") -> None:
        """A frame left unsent by the target's limits or its length, counted for the direction; the first of each reason for each direction is told at INFO, the rest at DEBUG."""
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
