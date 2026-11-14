"""Asking around: the general queries of APRS 1.0.1 (chapter 15) sent from here at the operator's request (the ones we hear are answered, or not, by services/queries.py).

`ask` sends one UI frame from our call to our tocall whose information field is the query and nothing else: `?APRS?` (all stations: who is around? each answers with its position, and its status if it has one), `?IGATE?`
(the iGates answer with their capabilities) or `?WX?` (the weather stations answer with their weather). It goes once, by the path the operator gives (aliases such as WIDE1-1,WIDE2-1, explicit digipeaters such as
OH2RDK-7,OH2RCH-2 for a station that reaches the network only through a fill-in digipeater that relays it when it is named, DIRECT for none; none given is `beacon/path`) with RFONLY after it unless the operator
says otherwise, so that the iGates keep it off APRS-IS and the stations in radio range answer by radio. It is refused under the transmit interlock (RX only, no call), while the radio is away, and within
ASK_EVERY_SEC of the query of the same kind (`general.too_soon`, with the seconds that are left): a query makes every station that hears it transmit, and the channel is shared.

The answers are ordinary packets (positions, capabilities, weather) and need nothing here. A station that answers does not say that it answers, so what is kept for the page is only what can be told: the last
query of each kind, when it went and by what path, and the stations heard on the radio (not a third-party packet, not from the internet, not us) in the COUNT_FOR after it that the station book had not heard on
the radio in the QUIET_BEFORE before it. Those are the stations that were quiet and spoke after the query: most will be answers, but a station whose own beacon fell in those two minutes counts too, and the answer of
a station heard a minute before the query does not. It is all forgotten when the daemon stops.

A query goes on one radio (plan rule 3.6): the one the operator names, else the main radio, and the query records it. The minute between two queries of a kind and the stations counted after it are that
radio's: a query of the kind on another radio may go at once, and only what that radio hears (a packet that names no radio counts for every query) of a station that radio had not heard in the QUIET_BEFORE is
counted. The log names the radio while more than one is on."""
import logging
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Literal, Protocol

from neoaprs.coded import CodedError
from neoaprs.clock import Clock, utcnow
from neoaprs.message import QUERY_TEXT, MessagingError, request_path, same_call
from neoaprs.packet import RF_GATED, Packet
from neoaprs.radiotype import RadioId
from neoaprs.services.common import FRAME_ERRORS, ConfigSource, Radio, asked_radio, on_words, our_call, our_frame
from neoaprs.services.radioset import RadioPick, path_on
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
    """A general query we sent: its kind, when, the path it went by (RFONLY included when it was RF only) and the calls of the stations that were quiet before it and were heard after it, in the order heard;
    the radio it went on (None for one made without)."""
    kind: Kind
    at: datetime
    path: tuple[str, ...]
    new: tuple[str, ...] = ()
    heard_before: frozenset[str] = field(default=frozenset(), repr=False)      # the stations heard on the radio in the QUIET_BEFORE before it
    radio: RadioId | None = None

    def counts(self, packet: Packet) -> bool:
        """Whether a packet heard at its time is one of this query's radio (a packet that names no radio is every radio's)."""
        return self.radio is None or packet.radio_id is None or packet.radio_id == self.radio

    @property
    def query(self) -> str:
        return QUERIES[self.kind]

    @property
    def until(self) -> datetime:
        """When the counting of `new` ends."""
        return self.at + COUNT_FOR


class GeneralAsk:
    def __init__(self, radios: RadioPick | Radio, config: ConfigSource, book: Stations, clock: Clock = utcnow) -> None:
        self._given = radios                                    # the station's radios (the registry; which app.py gives; an old shape of a test's): a query goes on the main radio
        self._config = config
        self._book = book
        self.clock = clock
        self.changed: Signal[[]] = Signal("general_changed")
        self._asked: dict[tuple[RadioId, Kind], GeneralAsked] = {}      # the last query of each kind on each radio

    def asked(self) -> list[GeneralAsked]:
        """The last query of each kind, whatever radio it went on, the oldest first (what the page shows: one of each kind, until the page names the radio)."""
        latest: dict[Kind, GeneralAsked] = {}
        for asked in self.asked_by_radio():
            latest[asked.kind] = asked
        return sorted(latest.values(), key=lambda a: a.at)

    def asked_by_radio(self) -> list[GeneralAsked]:
        """The last query of each kind on each radio, the oldest first."""
        return sorted(self._asked.values(), key=lambda a: a.at)

    def ask(self, kind: Kind, path: str | None = None, rf_only: bool = True, *, radio: RadioId | None = None) -> GeneralAsked:
        """Sends the query of the kind on the radio `radio` (None: the main radio) by `path` (None or empty is `beacon/path`) with RFONLY after it when `rf_only`. Raises MessagingError when the kind is none,
        nothing may be transmitted (RX only, no call), the radio is off or away, the query of this kind went on it less than ASK_EVERY_SEC ago (`general.too_soon`, with the seconds that are left), the path
        is no path or too long with RFONLY, or the frame is not taken."""
        config = self._config()
        our_call(config)
        if kind not in QUERIES:
            raise MessagingError(f"{kind!r} is not aprs, igate or wx")
        query = QUERIES[kind]
        on = asked_radio(self._given, self._config, radio)
        now = self.clock()
        before = self._asked.get((on.id, kind))
        if before is not None and (wait := ASK_EVERY_SEC - (now - before.at).total_seconds()) > 0:
            seconds = max(1, round(wait))
            raise MessagingError(f"too soon for another {query}: wait {seconds} s", "general.too_soon", query=query, seconds=seconds)
        try:
            calls = path_on(on, config, request_path(path, config.beacon_path_calls, rf_only))
        except CodedError as e:
            raise MessagingError(str(e), e.code, **e.params) from None
        try:
            frame = our_frame(config, calls, query.encode("ascii"))
        except FRAME_ERRORS as e:
            raise MessagingError(f"the query {query} makes no frame: {e}") from None
        if not on.send_frame(frame):
            raise MessagingError("the TNC would not take the frame")
        heard = frozenset(s.call for s in self._book.stations() if s.kind == "station" and _heard_lately(s, on.id, now))
        asked = self._asked[(on.id, kind)] = GeneralAsked(kind, now, calls, heard_before=heard, radio=on.id)
        log.info("asked around: %s by %s%s", query, ",".join(calls) or "no digipeaters", on_words(on, self._given, self._config))
        self.changed.emit()
        return asked

    def on_packet(self, packet: Packet) -> None:
        """A station heard on the radio of a query within COUNT_FOR of it, and not heard on that radio in the QUIET_BEFORE before it, is noted with the query."""
        if packet.direction != "in" or not packet.on_air or packet.via == RF_GATED or not self._asked:
            return
        call = packet.sender
        if same_call(call, self._config().station_call):
            return                                                  # (our own query, repeated by a digipeater)
        told = False
        for key, asked in self._asked.items():
            if asked.counts(packet) and asked.at <= packet.heard_at <= asked.until and call not in asked.heard_before and call not in asked.new and len(asked.new) < NEW_MAX:
                self._asked[key] = replace(asked, new=(*asked.new, call))
                told = True
        if told:
            self.changed.emit()


def _heard_lately(station: Station, radio: RadioId, now: datetime) -> bool:
    """Whether the station was on the air in the QUIET_BEFORE before `now` (not as a third-party packet) and the radio heard it in that time (what a packet that named no radio brought is radio 1's)."""
    on_air, there = station.last_on_air_at, station.heard_on(radio).last_at
    return on_air is not None and there is not None and timedelta(0) <= now - on_air <= QUIET_BEFORE and timedelta(0) <= now - there <= QUIET_BEFORE
