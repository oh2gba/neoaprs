"""Asking around: the general queries of APRS 1.0.1 (chapter 15) sent from here at the operator's request (the ones we hear are answered, or not, by services/queries.py).

`ask` sends one UI frame from our call to our tocall whose information field is the query and nothing else: `?APRS?` (all stations: who is around? each answers with its position, and its status if it has one), `?IGATE?`
(the iGates answer with their capabilities) or `?WX?` (the weather stations answer with their weather). It goes once, by the path the operator gives (aliases such as WIDE1-1,WIDE2-1, explicit digipeaters such as
OH2RDK-7,OH2RCH-2 for a station that reaches the network only through a fill-in digipeater that relays it when it is named, DIRECT for none; none given is the radio's own path) with RFONLY after it unless the operator
says otherwise, so that the iGates keep it off APRS-IS and the stations in radio range answer by radio. It is refused under the transmit interlock (RX only, no call), while the radio is away, and within
ASK_EVERY_SEC of the query of the same kind (`general.too_soon`, with the seconds that are left): a query makes every station that hears it transmit, and the channel is shared.

The answers are ordinary packets (positions, capabilities, weather) and need nothing here. A station that answers does not say that it answers, so what is kept for the page is only what can be told: the last
query of each kind, when it went and by what path, and the stations heard on the radio (not a third-party packet, not from the internet, not us) in the COUNT_FOR after it that the station book had not heard on
the radio in the QUIET_BEFORE before it. Those are the stations that were quiet and spoke after the query: most will be answers, but a station whose own beacon fell in those two minutes counts too, and the answer of
a station heard a minute before the query does not. It is all forgotten when the daemon stops.

Asking around has a Send on of its own (each radio's "ask" tick, read by beaconrule.send_on_radios: with one radio that can send, that one): a press sends one query on each ticked radio
that takes frames now, each by the path that radio carries (the one given where it may carry a path, else its own). The minute between two queries of a kind is each radio's, and a press is all or nothing:
while a ticked radio is inside its minute for the kind, or a path makes no frame on one of them, nothing goes on any (`general.too_soon` with the longest wait). The record of a press holds its radios, and
the stations counted after it are those one of its radios heard that this radio had not heard in the QUIET_BEFORE (a packet that names no radio counts where every radio of the press had been quiet), each
once whatever number of radios heard it. The log names the radio while more than one is on."""
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Literal, Protocol

from neoaprs.coded import CodedError
from neoaprs.clock import Clock, utcnow
from neoaprs.message import QUERY_TEXT, MessagingError, request_path, same_call
from neoaprs.packet import RF_GATED, Packet
from neoaprs.radiotype import RadioId
from neoaprs import ax25
from neoaprs.services.common import FRAME_ERRORS, ConfigSource, Radio, asked_radios, on_words, our_call, our_frame, send_on, sent_on
from neoaprs.services.radioset import AirRadio, RadioPick, path_on
from neoaprs.signal import Signal
from neoaprs.station import Station

log = logging.getLogger("neoaprs.queries")

Kind = Literal["aprs", "igate", "wx"]
QUERIES: dict[Kind, str] = {"aprs": QUERY_TEXT["aprs"], "igate": QUERY_TEXT["igate"], "wx": QUERY_TEXT["wx"]}       # the information field of each kind, exactly
ASK_EVERY_SEC = 60                      # one query of a kind in this time
COUNT_FOR = timedelta(minutes=2)        # how long after a query the stations that speak are counted
QUIET_BEFORE = timedelta(minutes=10)    # a station heard on the radio this long before the query is no newcomer
NEW_MAX = 200                           # the most calls kept for one query


class Stations(Protocol):
    """What asking around needs of the station book."""
    def stations(self) -> list[Station]: ...


@dataclass(frozen=True, slots=True)
class GeneralAsked:
    """A press of Ask: the kind of query, when, the radios it went on, the path it went by (RFONLY included when it was RF only; None when its radios that carry a path went each by its own and those
    differ) and the calls of the stations that were quiet before it and were heard after it, in the order heard, each once."""
    kind: Kind
    at: datetime
    path: tuple[str, ...] | None
    new: tuple[str, ...] = ()
    heard_before: Mapping[RadioId, frozenset[str]] = field(default_factory=dict, repr=False)      # for each of its radios, the stations heard on it in the QUIET_BEFORE before the press
    radios: tuple[RadioId, ...] = ()

    def counts(self, packet: Packet) -> bool:
        """Whether a packet heard in its time is a newcomer's: one of its radios heard it (a packet that names no radio is every radio's) and had not heard its sender before the press."""
        heard = self.radios if packet.radio_id is None else tuple(id for id in self.radios if id == packet.radio_id)
        quiet = [packet.sender not in self.heard_before.get(id, frozenset()) for id in heard]
        return bool(quiet) and (all(quiet) if packet.radio_id is None else quiet[0])

    @property
    def query(self) -> str:
        return QUERIES[self.kind]

    @property
    def until(self) -> datetime:
        """When the counting of `new` ends."""
        return self.at + COUNT_FOR


@dataclass(frozen=True, slots=True)
class SentOn:
    """The last query of a kind on one radio: the minute before the next of that kind is counted from it."""
    kind: Kind
    radio: RadioId
    at: datetime


class GeneralAsk:
    def __init__(self, radios: RadioPick | Radio, config: ConfigSource, book: Stations, clock: Clock = utcnow) -> None:
        self._given = radios                                    # the station's radios (the registry; which app.py gives; an old shape of a test's): a query goes on those of its Send on
        self._config = config
        self._book = book
        self.clock = clock
        self.changed: Signal[[]] = Signal("general_changed")
        self._asked: dict[Kind, GeneralAsked] = {}              # the last press of each kind
        self._sent: dict[tuple[RadioId, Kind], datetime] = {}   # when the last query of each kind went on each radio

    def asked(self) -> list[GeneralAsked]:
        """The last press of each kind, the oldest first (what the page shows)."""
        return sorted(self._asked.values(), key=lambda a: a.at)

    def sent_on(self) -> list[SentOn]:
        """The last query of each kind on each radio, the oldest first: what the wait before the next press is counted from."""
        return sorted((SentOn(kind, radio, at) for (radio, kind), at in self._sent.items()), key=lambda s: (s.at, s.radio))

    def ask(self, kind: Kind, path: str | None = None, rf_only: bool = True) -> GeneralAsked:
        """Sends the query of the kind once on each radio of asking around's Send on that takes frames now, by `path` (None or empty is each radio's own path) with RFONLY after it when `rf_only`, all or
        nothing. Raises MessagingError, and nothing is sent, when the kind is none, nothing may be transmitted (RX only, no call), there is no radio or none of them takes frames now, the query of this
        kind went on one of the ticked radios less than ASK_EVERY_SEC ago (`general.too_soon`, with the seconds that are left: the longest), the path is no path or too long with RFONLY, or no radio
        takes the frame."""
        our_call(self._config())
        if kind not in QUERIES:
            raise MessagingError(f"{kind!r} is not aprs, igate or wx", "failed")
        query = QUERIES[kind]
        on = asked_radios(self._given, self._config, "ask")
        now = self.clock()
        if (wait := max((self._wait(radio.id, kind, now) for radio in send_on(self._given, self._config, "ask")), default=0.0)) > 0:
            seconds = max(1, round(wait))
            raise MessagingError(f"too soon for another {query}: wait {seconds} s", "general.too_soon", query=query, seconds=seconds)
        frames = [(radio, self._frame(radio, query, path, rf_only)) for radio in on]          # (every frame is made before one is sent: a path that is none on one radio sends nothing on any)
        went = sent_on(frames, "asking around")
        asked = self._asked[kind] = GeneralAsked(kind, now, _shared_path(went), heard_before=self._heard_before([radio.id for radio, _ in went], now), radios=tuple(radio.id for radio, _ in went))
        for radio, frame in went:
            self._sent[(radio.id, kind)] = now
            log.info("asked around: %s by %s%s", query, frame.path_text or "no digipeaters", on_words(radio, self._given, self._config))
        self.changed.emit()
        return asked

    def _heard_before(self, radios: list[RadioId], now: datetime) -> dict[RadioId, frozenset[str]]:
        """For each radio, the stations it heard in the QUIET_BEFORE before `now`: no newcomers there."""
        stations = [s for s in self._book.stations() if s.kind == "station"]
        return {radio: frozenset(s.call for s in stations if _heard_lately(s, radio, now)) for radio in radios}

    def _wait(self, radio: RadioId, kind: Kind, now: datetime) -> float:
        """The seconds before a query of the kind may go on the radio again: ASK_EVERY_SEC after the last one there."""
        before = self._sent.get((radio, kind))
        return 0.0 if before is None else ASK_EVERY_SEC - (now - before).total_seconds()

    def _frame(self, radio: AirRadio, query: str, path: str | None, rf_only: bool) -> ax25.Frame:
        """The query as our frame for the radio, by the path it carries: the one given, else its own, with RFONLY; none where it may carry none."""
        config = self._config()
        try:
            calls = path_on(radio, config, request_path(path, path_on(radio, config, None), rf_only))      # (none given: the path of the radio it goes on, not radio 1's)
        except CodedError as e:
            raise MessagingError(str(e), e.code, **e.params) from None
        try:
            return our_frame(config, calls, query.encode("ascii"))
        except FRAME_ERRORS as e:
            raise MessagingError.of(e, f"the query {query} makes no frame: {e}") from None

    def on_packet(self, packet: Packet) -> None:
        """A station heard on a radio of a press within COUNT_FOR of it, and not heard on that radio in the QUIET_BEFORE before it, is noted with the press, once."""
        if packet.direction != "in" or not packet.on_air or packet.via == RF_GATED or not self._asked:
            return
        call = packet.sender
        if same_call(call, self._config().station_call):
            return                                                  # (our own query, repeated by a digipeater)
        told = False
        for kind, asked in self._asked.items():
            if asked.at <= packet.heard_at <= asked.until and call not in asked.new and len(asked.new) < NEW_MAX and asked.counts(packet):
                self._asked[kind] = replace(asked, new=(*asked.new, call))
                told = True
        if told:
            self.changed.emit()


def _shared_path(went: list[tuple[AirRadio, ax25.Frame]]) -> tuple[str, ...] | None:
    """The path a press went by: the one path of its radios that carry a path; () when none of them carries one; None when they went each by its own and those differ."""
    paths = {tuple(str(hop) for hop in frame.path) for radio, frame in went if radio.allowed.paths}
    return None if len(paths) > 1 else next(iter(paths), ())


def _heard_lately(station: Station, radio: RadioId, now: datetime) -> bool:
    """Whether the station was on the air in the QUIET_BEFORE before `now` (not as a third-party packet) and the radio heard it in that time (what a packet that named no radio brought is radio 1's)."""
    on_air, there = station.last_on_air_at, station.heard_on(radio).last_at
    return on_air is not None and there is not None and timedelta(0) <= now - on_air <= QUIET_BEFORE and timedelta(0) <= now - there <= QUIET_BEFORE
