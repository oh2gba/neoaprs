"""Queries: answers to what other stations ask of us in an APRS message (APRS 1.0.1 chapter 15).

Directed queries (?APRSP, ?APRSS, ?APRSD, ?APRST, ?APRSH, ?APRSO, ?APRSM) and the general
queries ?APRS? and ?IGATE? are answered here; ?WX? is recognised and never answered.
"""
import asyncio
import logging
import random
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from neoaprs import ax25
from neoaprs.aprsmessage import MAX_TEXT, MessageError
from neoaprs.callsign import INTERNET_NAME, CallsignError
from neoaprs.clock import Clock, utcnow
from neoaprs.geo import distance_km
from neoaprs.message import QUERY_TEXT, UNSETTLED, MessageRecord, addressed_to, same_call
from neoaprs.ownobject import OwnObject, info_of
from neoaprs.packet import Message, Other, Packet
from neoaprs.services.beacon import BeaconError
from neoaprs.services.answers import ANSWER_FRAMES_MAX, Answers, AnswerBudget, as_pick
from neoaprs.services.common import ConfigSource, Paths, Radio, our_frame
from neoaprs.services.pace import SPACING_SEC
from neoaprs.services.radioset import AirRadio, RadioPick, answerable
from neoaprs.station import Station
from neoaprs.units import MILE_KM

log = logging.getLogger("neoaprs.queries")

GENERAL = QUERY_TEXT["aprs"]
IGATE_QUERY = QUERY_TEXT["igate"]
GENERAL_DELAY_MAX_SEC = 120.0
GENERAL_EVERY_SEC = 600.0
DIRECT_WINDOW = timedelta(hours=1)
MAX_DIRECT_MESSAGES = 2
# the V is the specification's mark of a positive value
_NUMBER = r"V?\s*([-+]?\d+(?:\.\d+)?)"
_FOOTPRINT = re.compile(rf"\?(?:APRS|IGATE)\?(?:\s*{_NUMBER}\s*[,\s]\s*{_NUMBER}\s*[,\s]\s*(\d{{1,4}}))?", re.IGNORECASE)
# keyed without a trailing "?": ?PING? has one, and a radio may add one to the others
_DIRECTED = {QUERY_TEXT[kind]: kind for kind in ("position", "status", "directs", "path", "objects", "messages")} | {QUERY_TEXT["ping"].removesuffix("?"): "path"}
_PACED = ("objects", "messages")
HEARD_HOURS = 8
_HEARD = re.compile(re.escape(QUERY_TEXT["heard"]) + rf"\s*({INTERNET_NAME.pattern})?")
_NOT_ANSWERED = (QUERY_TEXT["wx"],)


# the radio an answer is built for; None: the beacon's own or the first radio that can send
AnswerRadio = AirRadio | None


class Frames(Protocol):
    def frame(self, radio: AnswerRadio = None) -> ax25.Frame: ...


class Stations(Protocol):
    def stations(self) -> list[Station]: ...
    def get(self, call: str) -> Station | None: ...
    @property
    def me_position(self) -> tuple[float, float] | None: ...


class HeardLog(Protocol):
    async def heard_since(self, call: str, when: datetime) -> list[datetime]: ...


class IgateCounts(Protocol):
    @property
    def state(self) -> str: ...
    gated: int


class Objects(Protocol):
    def records(self) -> list[OwnObject]: ...


class Messages(Protocol):
    def records(self) -> list[MessageRecord]: ...


class _Nothing:
    def records(self) -> list:  # type: ignore[type-arg]
        return []


# stands in for objects and messages when a Queries is made without them
_NOTHING = _Nothing()


def directs_messages(calls: list[str]) -> list[str]:
    """Return "Directs= OH2PU-9 ..." messages: up to MAX_TEXT bytes, MAX_DIRECT_MESSAGES of them."""
    if not calls:
        return ["Directs= none"]
    texts: list[str] = []
    line = "Directs="
    for call in calls:
        if len(line) + 1 + len(call) > MAX_TEXT:
            texts.append(line)
            if len(texts) == MAX_DIRECT_MESSAGES:
                return texts
            line = "Directs="
        line += " " + call
    return [*texts, line]


def path_text(packet: Packet) -> str:
    """Return the header as heard, "OH2GBA>APZNEO,OH2RCH-2*:", dropping hops beyond MAX_TEXT."""
    head = f"{packet.source}>{packet.destination}"
    hops = list(packet.path)
    while hops and len(f"{head},{','.join(hops)}:".encode()) > MAX_TEXT:
        hops.pop()
    return f"{head},{','.join(hops)}:" if hops else f"{head}:"


@dataclass(frozen=True)
class Footprint:
    """The circle of stations a general query addresses: centre in degrees, radius in miles."""
    lat: float
    lon: float
    miles: int

    def contains(self, lat: float, lon: float) -> bool:
        return distance_km(self.lat, self.lon, lat, lon) / MILE_KM <= self.miles


def general_kind(text: str) -> str | None:
    """Return GENERAL or IGATE_QUERY if the text is that query, else None."""
    head = text.strip().upper()
    return next((kind for kind in (GENERAL, IGATE_QUERY) if head.startswith(kind)), None)


def footprint_of(text: str) -> Footprint | None:
    """Return the query's footprint, None if plain; raise ValueError if malformed or off Earth."""
    found = _FOOTPRINT.fullmatch(text.strip())
    if found is None:
        raise ValueError(f"{text.strip()!r} is not a general query with a footprint")
    if found.group(1) is None:
        return None
    lat, lon = float(found.group(1)), float(found.group(2))
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ValueError(f"the footprint {lat:g}, {lon:g} is not on the earth")
    return Footprint(lat, lon, int(found.group(3)))


def capabilities_info(local: int, uploaded: int) -> bytes:
    """Return the information field answering ?IGATE?; MSG_CNT is 0, nothing is gated to RF."""
    return f"<IGATE,MSG_CNT=0,LOC_CNT={local},UPL_CNT={uploaded}".encode("ascii")


def hourly_counts(times: Sequence[datetime], now: datetime) -> list[int]:
    """Return the times counted per hour over the last HEARD_HOURS hours, latest first."""
    counts = [0] * HEARD_HOURS
    for when in times:
        hours = int((now - when).total_seconds() // 3600)
        if 0 <= hours < HEARD_HOURS:
            counts[hours] += 1
    return counts


def direct_on(station: Station, radio: AirRadio | None, now: datetime) -> datetime | None:
    """Return when the station was last heard direct within DIRECT_WINDOW of `now`, else None.

    A radio that carries no paths counts its last hearing, unless the packet shows a used hop."""
    if radio is None:
        at = station.last_direct_at
    elif not radio.allowed.paths:
        at = None if any(hop.endswith("*") for hop in station.heard_on(radio.id).last_path) else station.heard_on(radio.id).last_at
    else:
        routes = station.routes_on(radio.id)
        at = None if routes is None else routes.last_direct_at
    return at if at is not None and now - at <= DIRECT_WINDOW else None


def heard_text(call: str, counts: Sequence[int] | None) -> str:
    """Return the ?APRSH answer, "N0QBF HEARD: 1 3 2 . . 4 5 6", or "N0QBF NOT HEARD" for None."""
    if counts is None:
        return f"{call} NOT HEARD"
    return f"{call} HEARD: " + " ".join(str(min(n, 9999)) if n else "." for n in counts)


class Queries:
    def __init__(self, radios: RadioPick | Radio, config: ConfigSource, beacon: Frames, status: Callable[[AnswerRadio], ax25.Frame | None], book: Stations, paths: Paths,
                 clock: Clock = utcnow, delay: Callable[[], float] = lambda: random.uniform(0.0, GENERAL_DELAY_MAX_SEC), objects: Objects = _NOTHING, messages: Messages = _NOTHING,  # noqa: S311  (pause before an answer, no secret)
                 spacing_sec: float = SPACING_SEC, heard: HeardLog | None = None, igate: IgateCounts | None = None, budget: AnswerBudget | None = None) -> None:
        self._config = config
        self._given = radios
        self._answers = Answers(radios, config, paths, spacing_sec, budget if budget is not None else AnswerBudget(clock))
        self._beacon = beacon
        self._status = status
        self._book = book
        self.clock = clock
        self._delay = delay
        self._objects, self._messages, self._heard = objects, messages, heard
        self._igate = igate
        # no general query of a kind is taken before this
        self._general_until: dict[str, datetime] = {}

    async def stop(self) -> None:
        await self._answers.stop()

    # ---- what is asked
    def on_packet(self, packet: Packet) -> None:
        """Answer a query addressed to us, or a general query."""
        if packet.direction != "in" or not packet.on_air or same_call(packet.sender, self._config().station_call):
            # an internet query gets no answer: it would go by radio to a station not here
            return
        decoded = packet.decoded
        if isinstance(decoded, Message):
            if decoded.ack_id is None and decoded.rej_id is None and addressed_to(decoded.addressee, self._config().station_call):
                self._to_us(packet, decoded.text.strip().upper())
        elif isinstance(decoded, Other) and decoded.kind == "query":
            if (kind := general_kind(decoded.text)) is not None:
                self._general(packet, decoded.text, kind)
            elif decoded.text.strip().upper().startswith(_NOT_ANSWERED):
                log.debug("the general query %s of %s has nothing to be answered with here", decoded.text.strip(), packet.sender)

    def _to_us(self, packet: Packet, text: str) -> None:
        """Answer the upper-case message text if it is a directed query, trailing `?` optional."""
        text = text.removesuffix("?")
        if text in _DIRECTED:
            self._directed(packet, _DIRECTED[text])
        elif (found := _HEARD.fullmatch(text)) is not None:
            self._directed(packet, "heard", found.group(1))

    def _directed(self, packet: Packet, query: str, argument: str | None = None) -> None:
        asker, key = packet.sender, query if argument is None else f"{query} {argument}"
        if self._answers.refused() or not answerable(as_pick(self._given, self._config), packet):
            return
        if self._answers.lately(asker, key, packet.heard_at):
            log.debug("the %s query of %s was answered a moment ago", key, asker)
            return
        if query == "heard":
            if self._starts_heard(packet, key, argument):
                # a radio switched off while the log is read answers nothing, and no other does
                self._answers.tasks.spawn(self._heard_answer(packet, key, argument, self._came_on(packet)), "query-heard")
            return
        radio = self._came_on(packet)
        try:
            frames = [frame for frame in self._answer(packet, query, radio) if frame is not None]
            self._answers.deliver(asker, key, frames, packet.heard_at, query in _PACED, radio=radio)
        except (BeaconError, ax25.Ax25Error, CallsignError, MessageError, ValueError) as e:
            log.warning("the %s query of %s was not answered: %s", key, asker, e)

    def _came_on(self, packet: Packet) -> AirRadio | None:
        return as_pick(self._given, self._config).for_packet(packet)

    def _answer(self, packet: Packet, query: str, radio: AirRadio | None) -> Sequence[ax25.Frame | None]:
        """Return the answer frames (None: no status yet); raise BeaconError if none can be made."""
        asker = packet.sender
        if query == "position":
            return [self._beacon.frame(radio)]
        if query == "status":
            return [self._status(radio)]
        if query == "directs":
            return [self._answers.message(asker, text) for text in directs_messages(self._directs(packet.heard_at, radio))]
        if query == "objects":
            return [our_frame(self._config(), (), info_of(o, self.clock())) for o in self._objects.records() if o.alive][:ANSWER_FRAMES_MAX]
        if query == "messages":
            # a sealed message goes again as it went on the air, never as written
            return [self._answers.message(asker, r.wire if r.wire is not None else r.text, r.msg_id) for r in self._unsettled(asker)]
        return [self._answers.message(asker, path_text(packet))]

    def _unsettled(self, asker: str) -> list[MessageRecord]:
        """Return the latest ANSWER_FRAMES_MAX unsettled messages to the asker, oldest first."""
        ours = [r for r in self._messages.records() if r.direction == "out" and r.msg_id is not None and r.state in UNSETTLED and same_call(r.to_call, asker)]
        return sorted(ours, key=lambda r: r.id)[-ANSWER_FRAMES_MAX:]

    # ---- ?APRSH
    def _starts_heard(self, packet: Packet, key: str, call: str | None) -> bool:
        """Return whether ?APRSH is answered (log exists, call not ours); copies count too."""
        if self._heard is None or call is None or same_call(call, self._config().station_call):
            log.debug("the heard query of %s is not answered: %s", packet.sender, "no call" if call is None else "nothing to look in" if self._heard is None else "it is about us")
            return False
        self._answers.note(packet.sender, key, packet.heard_at)
        return True

    async def _heard_answer(self, packet: Packet, key: str, call: str | None, radio: AirRadio | None) -> None:
        """Answer ?APRSH from the packet log."""
        assert self._heard is not None and call is not None
        times = await self._heard.heard_since(call, packet.heard_at - timedelta(hours=HEARD_HOURS))
        counts = hourly_counts(times, packet.heard_at)
        found = self._book.get(call)
        # a station known from the internet alone was never heard on the air
        known = any(counts) or (found is not None and not found.internet_only)
        try:
            self._answers.deliver(packet.sender, key, [self._answers.message(packet.sender, heard_text(call, counts if known else None))], packet.heard_at, False, radio=radio)
        except (ax25.Ax25Error, CallsignError, MessageError, ValueError) as e:
            log.warning("the %s query of %s was not answered: %s", key, packet.sender, e)

    # ---- ?APRS? and ?IGATE?
    def _general(self, packet: Packet, text: str, kind: str) -> None:
        """Answer after a random wait if in the footprint; one per kind per GENERAL_EVERY_SEC."""
        if self._answers.refused() or not answerable(as_pick(self._given, self._config), packet):
            return
        if kind == IGATE_QUERY and (why := self._no_igate()):
            log.debug("the general query %s of %s is not answered: %s", IGATE_QUERY, packet.sender, why)
            return
        try:
            footprint = footprint_of(text)
        except ValueError as e:
            log.debug("the general query of %s is not answered: %s", packet.sender, e)
            return
        here = self._book.me_position
        if footprint is not None and (here is None or not footprint.contains(*here)):
            log.debug("the general query of %s is for a footprint we are not in", packet.sender)
            return
        until = self._general_until.get(kind)
        if until is not None and packet.heard_at < until:
            log.debug("the general query %s of %s is not taken: one was taken less than %d s ago", kind, packet.sender, GENERAL_EVERY_SEC)
            return
        self._general_until[kind] = packet.heard_at + timedelta(seconds=GENERAL_EVERY_SEC)
        delay = self._delay()
        log.info("the general query %s of %s: our %s go out in %.0f s", kind, packet.sender, "position and status" if kind == GENERAL else "capabilities", delay)
        self._answers.tasks.spawn(self._later(delay, packet.sender, kind, self._came_on(packet)), "query-general")

    def _no_igate(self) -> str:
        """Return why ?IGATE? cannot be answered now; empty while the iGate is connected."""
        if self._igate is None:
            return "there is no iGate"
        state = self._igate.state
        return "" if state == "connected" else f"the iGate is {state}"

    async def _later(self, delay: float, asker: str, kind: str, radio: AirRadio | None) -> None:
        await asyncio.sleep(delay)
        if self._answers.refused():
            return
        try:
            if kind == IGATE_QUERY:
                if why := self._no_igate():
                    log.debug("the general query %s of %s is not answered: %s", IGATE_QUERY, asker, why)
                    return
                self._send_frames(asker, [self._capabilities], radio)
            else:
                self._send_frames(asker, [lambda: self._beacon.frame(radio), lambda: self._status(radio)], radio)
        except (BeaconError, ax25.Ax25Error, CallsignError, ValueError) as e:
            log.warning("the general query of %s was not answered: %s", asker, e)

    def _capabilities(self) -> ax25.Frame:
        assert self._igate is not None
        return our_frame(self._config(), (), capabilities_info(len(self._directs(self.clock())), self._igate.gated))

    def _send_frames(self, asker: str, makers: Sequence[Callable[[], ax25.Frame | None]], radio: AirRadio | None) -> None:
        """Make frames separately so one failure keeps the rest; send all or none (budget)."""
        frames: list[ax25.Frame] = []
        for make in makers:
            try:
                frame = make()
            except (BeaconError, ax25.Ax25Error, CallsignError, ValueError) as e:
                log.warning("the answer to the general query of %s lacks a frame: %s", asker, e)
                continue
            if frame is not None:
                frames.append(frame)
        self._answers.send(asker, frames, radio=radio)

    # ---- the answers
    def _directs(self, now: datetime, radio: AirRadio | None = None) -> list[str]:
        """Return the calls heard direct within DIRECT_WINDOW, latest first, on `radio` or any."""
        heard = [(at, s.call) for s in self._book.stations() if s.kind == "station" and not s.is_me and (at := direct_on(s, radio, now)) is not None]
        return [call for _, call in sorted(heard, reverse=True)]
