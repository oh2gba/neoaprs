"""Queries: what other stations ask of us in an APRS message, and the answers.

A message to us (our call with its SSID exactly: our base call is not ours when ours has an SSID, message.addressed_to) whose text is

    ?APRSP   is answered with our position packet (the beacon's frame, `Beacon.frame()`)
    ?APRSS   with our status report as it was last sent (services/rigstatus.py; nothing while none has been sent)
    ?APRSD   with a message to the asker, "Directs= OH2PU-9 OH2RCH-2", the calls heard direct in the last hour (the one heard last first; at most MAX_TEXT bytes, in two messages at the most, "Directs= none"
             when there is none)
    ?APRST   (and ?PING?) with a message to the asker, "OH2GBA>APZNEO,OH2RCH-2*:": the header of the query as we heard it, the digipeaters it went by with their stars
    ?APRSH N0QBF   (the call after the query, a blank between them or not) with a message to the asker, "N0QBF HEARD: 1 3 2 . . 4 5 6": how many packets of that station we heard in each of the last 8 hours, the
             hour just gone first, a dot for an hour with none (the packet log; "N0QBF NOT HEARD" for a station we have no trace of at all). APRS 1.0.1 (chapter 15) also has the answer carry the station's position
             as an object; we leave that out, because an object named like a station is the one thing our own objects are never allowed to be (services/ownobjects.py) and a program that reads it would show
             the station twice
    ?APRSO   with our live objects and items (services/ownobjects.py), each once as it is now, at most ANSWER_FRAMES_MAX of them; one that is `on_request` (sent only to a station that asks) is among them
    ?APRSM   with our messages to the asker that no ack has settled (being sent, failed or unconfirmed), each once as it was sent ({MM}), the latest ANSWER_FRAMES_MAX of them; their
             records do not change (an ack that comes settles them as ever)

The frames of ?APRSO and ?APRSM go out one at a time, SPACING_SEC apart (services/pace.py, the pause between our own frames); the others at once. How an answer is sent and when it is given only once is services/answers.py's,
which the QRU server (services/qru.py) uses as well.

The general query ?APRS? is a `?` packet (the information field starts with `?APRS?`), not the text of a message, and a message with that text is not answered. It may carry a target footprint,
`?APRS?V34.02,-117.15,0200` (latitude and longitude in degrees, the radius in miles; the V stands for a space and may be left out): we answer only when our position is inside it, and a footprint that does not read is
not answered. The answer is our position packet and then our status report (the status only when one has been sent or is kept), after a random delay of 0 to GENERAL_DELAY_MAX_SEC seconds, and
not again within GENERAL_EVERY_SEC of the last time it was taken. Every
answer goes by the path of the asker (the station preferences, else `beacon/path`) as frames of our own; none is a message of messaging, none is retried.

The general queries `?WX?` (the weather report of a weather station) and `?IGATE?` (the capabilities of an IGate) are recognised and never answered: NeoAPRS has no weather report of its own to send and is no IGate, and
"a queried station that has no relevant information need not respond" (APRS 1.0.1, chapter 15). Each is a line in the log at DEBUG, and the packet is an ordinary `?` packet of the packet log, not an undecoded one."""
import asyncio
import logging
import math
import random
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from neoaprs import ax25
from neoaprs.aprsmessage import MAX_TEXT, MessageError
from neoaprs.callsign import CallsignError
from neoaprs.clock import Clock, utcnow
from neoaprs.message import MessageRecord, addressed_to, same_call
from neoaprs.ownobject import OwnObject, info_of
from neoaprs.packet import Message, Other, Packet
from neoaprs.services.beacon import BeaconError
from neoaprs.services.answers import ANSWER_FRAMES_MAX, Answers
from neoaprs.services.common import ConfigSource, Radio, our_frame
from neoaprs.services.pace import SPACING_SEC
from neoaprs.station import Station

log = logging.getLogger("neoaprs.queries")

GENERAL = "?APRS?"
GENERAL_DELAY_MAX_SEC = 120.0
GENERAL_EVERY_SEC = 600.0
DIRECT_WINDOW = timedelta(hours=1)
MAX_DIRECT_MESSAGES = 2
EARTH_MILES = 3958.8
_NUMBER = r"V?\s*([-+]?\d+(?:\.\d+)?)"                                     # (the V is the specification's mark of a positive value)
_FOOTPRINT = re.compile(rf"\?APRS\?(?:\s*{_NUMBER}\s*[,\s]\s*{_NUMBER}\s*[,\s]\s*(\d{{1,4}}))?", re.IGNORECASE)
_DIRECTED = {"?APRSP": "position", "?APRSS": "status", "?APRSD": "directs", "?APRST": "path", "?PING?": "path", "?APRSO": "objects", "?APRSM": "messages"}
_PACED = ("objects", "messages")                                          # the answers of several frames, sent SPACING_SEC apart
HEARD_HOURS = 8
_HEARD = re.compile(r"\?APRSH\s*([A-Z0-9-]{1,9})?")
_NOT_ANSWERED = ("?WX?", "?IGATE?")                                        # general queries of the specification that we have nothing to answer
_UNSETTLED = ("sending", "failed", "unconfirmed")


class Frames(Protocol):
    """What the queries need of the beacon: the frame of our position."""
    def frame(self) -> ax25.Frame: ...


class Stations(Protocol):
    """What the queries need of the station book."""
    def stations(self) -> list[Station]: ...
    def get(self, call: str) -> Station | None: ...


class HeardLog(Protocol):
    """What the queries need of the packet log (neoaprs/packetlog.py)."""
    async def heard_since(self, call: str, when: datetime) -> list[datetime]: ...


class Objects(Protocol):
    """What the queries need of our objects and items (services/ownobjects.py)."""
    def records(self) -> list[OwnObject]: ...


class Messages(Protocol):
    """What the queries need of messaging."""
    def records(self) -> list[MessageRecord]: ...


class _Nothing:
    def records(self) -> list:                                                  # type: ignore[type-arg]
        return []


_NOTHING = _Nothing()                                                           # (no objects, no messages: a Queries made without them)


def directs_messages(calls: list[str]) -> list[str]:
    """The texts of the messages that list the calls: "Directs= OH2PU-9 OH2RCH-2", each at most MAX_TEXT bytes, at most MAX_DIRECT_MESSAGES of them (the calls that do not fit are left out);
    "Directs= none" for no call at all."""
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
    """"OH2GBA>APZNEO,OH2RCH-2*:": the header of the packet as heard, its digipeaters with their stars, as the example of APRS 1.0.1 (chapter 15) writes it; the last of them go when the text
    would be over MAX_TEXT bytes."""
    head = f"{packet.source}>{packet.destination}"
    hops = list(packet.path)
    while hops and len(f"{head},{','.join(hops)}:".encode()) > MAX_TEXT:
        hops.pop()
    return f"{head},{','.join(hops)}:" if hops else f"{head}:"


@dataclass(frozen=True)
class Footprint:
    """The circle a general query asks the stations in to answer: its centre in degrees and its radius in miles."""
    lat: float
    lon: float
    miles: int

    def contains(self, lat: float, lon: float) -> bool:
        """Whether the point is inside the circle (the great-circle distance on a sphere of radius EARTH_MILES)."""
        p1, p2 = math.radians(self.lat), math.radians(lat)
        a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon - self.lon) / 2) ** 2
        return 2 * EARTH_MILES * math.asin(min(1.0, math.sqrt(a))) <= self.miles


def _is_general(text: str) -> bool:
    return text.strip().upper().startswith(GENERAL)


def footprint_of(text: str) -> Footprint | None:
    """The footprint a general query carries, None for the plain `?APRS?`; ValueError when what follows the `?APRS?` is not a footprint or the degrees are not on the earth."""
    found = _FOOTPRINT.fullmatch(text.strip())
    if found is None:
        raise ValueError(f"{text.strip()!r} is not ?APRS? with a footprint")
    if found.group(1) is None:
        return None
    lat, lon = float(found.group(1)), float(found.group(2))
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ValueError(f"the footprint {lat:g}, {lon:g} is not on the earth")
    return Footprint(lat, lon, int(found.group(3)))


def hourly_counts(times: Sequence[datetime], now: datetime) -> list[int]:
    """How many of the times fall in each of the last HEARD_HOURS hours before `now`, the hour just gone first (the first is the last 60 minutes, the second the 60 before them, and so on)."""
    counts = [0] * HEARD_HOURS
    for when in times:
        hours = int((now - when).total_seconds() // 3600)
        if 0 <= hours < HEARD_HOURS:
            counts[hours] += 1
    return counts


def heard_text(call: str, counts: Sequence[int] | None) -> str:
    """The answer to ?APRSH as the example of APRS 1.0.1 has it: "N0QBF HEARD: 1 3 2 . . 4 5 6", a dot for an hour with none; "N0QBF NOT HEARD" for a station that was never heard (`counts` None)."""
    if counts is None:
        return f"{call} NOT HEARD"
    return f"{call} HEARD: " + " ".join(str(min(n, 9999)) if n else "." for n in counts)


class Queries:
    def __init__(self, tnc: Radio, config: ConfigSource, beacon: Frames, status: Callable[[], ax25.Frame | None], book: Stations, paths: Callable[[str], tuple[str, ...]],
                 clock: Clock = utcnow, delay: Callable[[], float] = lambda: random.uniform(0.0, GENERAL_DELAY_MAX_SEC), objects: Objects = _NOTHING, messages: Messages = _NOTHING,
                 spacing_sec: float = SPACING_SEC, heard: HeardLog | None = None) -> None:
        self._config = config
        self._answers = Answers(tnc, config, paths, spacing_sec)
        self._beacon = beacon
        self._status = status                                   # the frame of the status as last sent (RigStatus.status_frame); None while none has been sent
        self._book = book
        self.clock = clock
        self._delay = delay                                     # how long the answer to the general query waits
        self._objects, self._messages, self._heard = objects, messages, heard
        self._general_until: datetime | None = None             # no general query is taken before this

    async def stop(self) -> None:
        """An answer that is waiting is not sent."""
        await self._answers.stop()

    # ---- what is asked
    def on_packet(self, packet: Packet) -> None:
        """The Tnc heard a packet: a query to us, or the general query, is answered."""
        if packet.direction != "in" or not packet.on_air or same_call(packet.sender, self._config().station_call):
            return                                                   # (a query that came over the internet is not answered: the answer would go out by radio to a station that is not here)
        decoded = packet.decoded
        if isinstance(decoded, Message):
            if decoded.ack_id is None and decoded.rej_id is None and addressed_to(decoded.addressee, self._config().station_call):
                self._to_us(packet, decoded.text.strip().upper())
        elif isinstance(decoded, Other) and decoded.kind == "query":
            if _is_general(decoded.text):
                self._general(packet, decoded.text)
            elif decoded.text.strip().upper().startswith(_NOT_ANSWERED):
                log.debug("the general query %s of %s has nothing to be answered with here", decoded.text.strip(), packet.sender)

    def _to_us(self, packet: Packet, text: str) -> None:
        """The text of a message to us, upper case: a directed query is answered, any other text is a message."""
        if text in _DIRECTED:
            self._directed(packet, _DIRECTED[text])
        elif (found := _HEARD.fullmatch(text)) is not None:
            self._directed(packet, "heard", found.group(1))

    def _directed(self, packet: Packet, query: str, argument: str | None = None) -> None:
        asker, key = packet.sender, query if argument is None else f"{query} {argument}"
        if self._answers.refused():
            return
        if self._answers.lately(asker, key, packet.heard_at):
            log.debug("the %s query of %s was answered a moment ago", key, asker)
            return
        if query == "heard":
            if self._starts_heard(packet, key, argument):
                self._answers.tasks.spawn(self._heard_answer(packet, key, argument), "query-heard")
            return
        try:
            frames = [frame for frame in self._answer(packet, query) if frame is not None]
            self._answers.deliver(asker, key, frames, packet.heard_at, query in _PACED)
        except (BeaconError, ax25.Ax25Error, CallsignError, MessageError, ValueError) as e:
            log.warning("the %s query of %s was not answered: %s", key, asker, e)

    def _answer(self, packet: Packet, query: str) -> Sequence[ax25.Frame | None]:
        """The frames that answer the query (a None for a status not yet sent); BeaconError when the settings make no frame."""
        asker = packet.sender
        if query == "position":
            return [self._beacon.frame()]
        if query == "status":
            return [self._status()]
        if query == "directs":
            return [self._answers.message(asker, text) for text in directs_messages(self._directs(packet.heard_at))]
        if query == "objects":
            return [our_frame(self._config(), (), info_of(o, self.clock())) for o in self._objects.records() if o.alive][:ANSWER_FRAMES_MAX]
        if query == "messages":
            return [self._answers.message(asker, r.text, r.msg_id) for r in self._unsettled(asker)]
        return [self._answers.message(asker, path_text(packet))]

    def _unsettled(self, asker: str) -> list[MessageRecord]:
        """Our messages to the asker that no ack has settled, the latest ANSWER_FRAMES_MAX, oldest first."""
        ours = [r for r in self._messages.records() if r.direction == "out" and r.msg_id is not None and r.state in _UNSETTLED and same_call(r.to_call, asker)]
        return sorted(ours, key=lambda r: r.id)[-ANSWER_FRAMES_MAX:]

    # ---- ?APRSH
    def _starts_heard(self, packet: Packet, key: str, call: str | None) -> bool:
        """Whether the answer to ?APRSH is to be worked out: there is a packet log, a call to look for that is not ours. The query counts as answered from now, so that the copies of it are not."""
        if self._heard is None or call is None or same_call(call, self._config().station_call):
            log.debug("the heard query of %s is not answered: %s", packet.sender, "no call" if call is None else "nothing to look in" if self._heard is None else "it is about us")
            return False
        self._answers.note(packet.sender, key, packet.heard_at)
        return True

    async def _heard_answer(self, packet: Packet, key: str, call: str | None) -> None:
        """The message that tells in which of the last HEARD_HOURS hours the station was heard, from the packet log."""
        assert self._heard is not None and call is not None
        times = await self._heard.heard_since(call, packet.heard_at - timedelta(hours=HEARD_HOURS))
        counts = hourly_counts(times, packet.heard_at)
        found = self._book.get(call)
        known = any(counts) or (found is not None and not found.internet_only)           # (a station known from the internet alone was never heard on the air)
        try:
            self._answers.deliver(packet.sender, key, [self._answers.message(packet.sender, heard_text(call, counts if known else None))], packet.heard_at, False)
        except (ax25.Ax25Error, CallsignError, MessageError, ValueError) as e:
            log.warning("the %s query of %s was not answered: %s", key, packet.sender, e)

    # ---- ?APRS?
    def _general(self, packet: Packet, text: str) -> None:
        """?APRS?: our position and status after a random wait when we are inside its footprint (if it has one), and no second one before GENERAL_EVERY_SEC has passed."""
        if self._answers.refused():
            return
        try:
            footprint = footprint_of(text)
        except ValueError as e:
            log.debug("the general query of %s is not answered: %s", packet.sender, e)
            return
        c = self._config()
        if footprint is not None and (c.station_position is None or not footprint.contains(*c.station_position)):
            log.debug("the general query of %s is for a footprint we are not in", packet.sender)
            return
        if self._general_until is not None and packet.heard_at < self._general_until:
            log.debug("the general query of %s is not taken: one was taken less than %d s ago", packet.sender, GENERAL_EVERY_SEC)
            return
        self._general_until = packet.heard_at + timedelta(seconds=GENERAL_EVERY_SEC)
        delay = self._delay()
        log.info("the general query of %s: our position and status go out in %.0f s", packet.sender, delay)
        self._answers.tasks.spawn(self._later(delay, packet.sender), "query-general")

    async def _later(self, delay: float, asker: str) -> None:
        await asyncio.sleep(delay)
        if self._answers.refused():
            return
        try:
            frames = [self._beacon.frame(), self._status()]
            for frame in frames:
                if frame is not None and not self._answers.send(asker, frame):
                    break
        except (BeaconError, ax25.Ax25Error, CallsignError, ValueError) as e:
            log.warning("the general query of %s was not answered: %s", asker, e)

    # ---- the answers
    def _directs(self, now: datetime) -> list[str]:
        """The calls heard direct within DIRECT_WINDOW, the one heard last first (not us, not an object)."""
        heard = [(s.last_direct_at, s.call) for s in self._book.stations() if s.kind == "station" and not s.is_me and s.last_direct_at is not None and now - s.last_direct_at <= DIRECT_WINDOW]
        return [call for _, call in sorted(heard, reverse=True)]
