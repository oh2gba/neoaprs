"""Asking around: the general queries of APRS 1.0.1 (chapter 15) sent at the operator's request.

`ask` sends a UI frame holding only the query on each ticked radio, all or nothing, with RFONLY
appended by default. Kept for the page: the last query of each kind and the newcomers after it.
"""
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
QUERIES: dict[Kind, str] = {"aprs": QUERY_TEXT["aprs"], "igate": QUERY_TEXT["igate"], "wx": QUERY_TEXT["wx"]}
ASK_EVERY_SEC = 60
COUNT_FOR = timedelta(minutes=2)        # stations heard this long after a query are counted
QUIET_BEFORE = timedelta(minutes=10)    # a station heard this long before the query is no newcomer
NEW_MAX = 200


class Stations(Protocol):
    def stations(self) -> list[Station]: ...


@dataclass(frozen=True, slots=True)
class GeneralAsked:
    """A press of Ask: kind, time, radios, path and the newcomers heard after it.

    `path` is None when the radios went by different paths.
    """
    kind: Kind
    at: datetime
    path: tuple[str, ...] | None
    new: tuple[str, ...] = ()
    # Per radio: stations heard in QUIET_BEFORE.
    heard_before: Mapping[RadioId, frozenset[str]] = field(default_factory=dict, repr=False)
    radios: tuple[RadioId, ...] = ()

    def counts(self, packet: Packet) -> bool:
        """Whether the packet is a newcomer's: a radio of the press heard it, newly."""
        heard = self.radios if packet.radio_id is None else tuple(id for id in self.radios if id == packet.radio_id)
        quiet = [packet.sender not in self.heard_before.get(id, frozenset()) for id in heard]
        return bool(quiet) and (all(quiet) if packet.radio_id is None else quiet[0])

    @property
    def query(self) -> str:
        return QUERIES[self.kind]

    @property
    def until(self) -> datetime:
        """When counting of `new` ends."""
        return self.at + COUNT_FOR


@dataclass(frozen=True, slots=True)
class SentOn:
    """The last query of a kind on one radio."""
    kind: Kind
    radio: RadioId
    at: datetime


class GeneralAsk:
    def __init__(self, radios: RadioPick | Radio, config: ConfigSource, book: Stations, clock: Clock = utcnow) -> None:
        self._given = radios
        self._config = config
        self._book = book
        self.clock = clock
        self.changed: Signal[[]] = Signal("general_changed")
        self._asked: dict[Kind, GeneralAsked] = {}
        self._sent: dict[tuple[RadioId, Kind], datetime] = {}

    def asked(self) -> list[GeneralAsked]:
        """The last press of each kind, oldest first."""
        return sorted(self._asked.values(), key=lambda a: a.at)

    def sent_on(self) -> list[SentOn]:
        """The last query of each kind on each radio, oldest first."""
        return sorted((SentOn(kind, radio, at) for (radio, kind), at in self._sent.items()), key=lambda s: (s.at, s.radio))

    def ask(self, kind: Kind, path: str | None = None, rf_only: bool = True) -> GeneralAsked:
        """Send the query on each ticked radio, all or nothing; empty `path` is each radio's own.

        Raise MessagingError if a radio is unusable or inside ASK_EVERY_SEC, or input is invalid.
        """
        our_call(self._config())
        if kind not in QUERIES:
            raise MessagingError(f"{kind!r} is not aprs, igate or wx", "failed")
        query = QUERIES[kind]
        on = asked_radios(self._given, self._config, "ask")
        now = self.clock()
        if (wait := max((self._wait(radio.id, kind, now) for radio in send_on(self._given, self._config, "ask")), default=0.0)) > 0:
            seconds = max(1, round(wait))
            raise MessagingError(f"too soon for another {query}: wait {seconds} s", "general.too_soon", query=query, seconds=seconds)
        # All frames are built before any is sent, so a bad path sends nothing.
        frames = [(radio, self._frame(radio, query, path, rf_only)) for radio in on]
        went = sent_on(frames, "asking around")
        asked = self._asked[kind] = GeneralAsked(kind, now, _shared_path(went), heard_before=self._heard_before([radio.id for radio, _ in went], now), radios=tuple(radio.id for radio, _ in went))
        for radio, frame in went:
            self._sent[(radio.id, kind)] = now
            log.info("asked around: %s by %s%s", query, frame.path_text or "no digipeaters", on_words(radio, self._given, self._config))
        self.changed.emit()
        return asked

    def _heard_before(self, radios: list[RadioId], now: datetime) -> dict[RadioId, frozenset[str]]:
        """For each radio, the stations it heard in the QUIET_BEFORE before `now`."""
        stations = [s for s in self._book.stations() if s.kind == "station"]
        return {radio: frozenset(s.call for s in stations if _heard_lately(s, radio, now)) for radio in radios}

    def _wait(self, radio: RadioId, kind: Kind, now: datetime) -> float:
        """Seconds left before the kind may go on the radio again; zero or less if now."""
        before = self._sent.get((radio, kind))
        return 0.0 if before is None else ASK_EVERY_SEC - (now - before).total_seconds()

    def _frame(self, radio: AirRadio, query: str, path: str | None, rf_only: bool) -> ax25.Frame:
        """Build the query frame: the given path, else the radio's own, with RFONLY if asked."""
        config = self._config()
        try:
            calls = path_on(radio, config, request_path(path, path_on(radio, config, None), rf_only))
        except CodedError as e:
            raise MessagingError(str(e), e.code, **e.params) from None
        try:
            return our_frame(config, calls, query.encode("ascii"))
        except FRAME_ERRORS as e:
            raise MessagingError.of(e, f"the query {query} makes no frame: {e}") from None

    def on_packet(self, packet: Packet) -> None:
        """Note a newcomer heard within COUNT_FOR of a press, once."""
        if packet.direction != "in" or not packet.on_air or packet.via == RF_GATED or not self._asked:
            return
        call = packet.sender
        if same_call(call, self._config().station_call):
            return  # our own query, repeated by a digipeater
        told = False
        for kind, asked in self._asked.items():
            if asked.at <= packet.heard_at <= asked.until and call not in asked.new and len(asked.new) < NEW_MAX and asked.counts(packet):
                self._asked[kind] = replace(asked, new=(*asked.new, call))
                told = True
        if told:
            self.changed.emit()


def _shared_path(went: list[tuple[AirRadio, ax25.Frame]]) -> tuple[str, ...] | None:
    """The path a press went by: the common one, () if none carries a path, None if they differ."""
    paths = {tuple(str(hop) for hop in frame.path) for radio, frame in went if radio.allowed.paths}
    return None if len(paths) > 1 else next(iter(paths), ())


def _heard_lately(station: Station, radio: RadioId, now: datetime) -> bool:
    """Whether `radio` heard the station on the air within QUIET_BEFORE."""
    on_air, there = station.last_on_air_at, station.heard_on(radio).last_at
    return on_air is not None and there is not None and timedelta(0) <= now - on_air <= QUIET_BEFORE and timedelta(0) <= now - there <= QUIET_BEFORE
