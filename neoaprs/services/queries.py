"""Queries: what other stations ask of us in an APRS message, and the answers.

A message to us (our call with its SSID exactly: our base call is not ours when ours has an SSID, message.addressed_to) whose text is

    ?APRSP   is answered with our position packet (the beacon's frame, `Beacon.frame()`)
    ?APRSS   with our status report as it was last sent (services/rigstatus.py; nothing while none has been sent)
    ?APRSD   with a message to the asker, "Directs= OH2PU-9 OH2RCH-2", the calls heard direct in the last hour (the one heard last first; at most MAX_TEXT bytes, in two messages at the most, "Directs= none"
             when there is none)
    ?APRST   (and ?PING?) with a message to the asker, "Path= OH2GBA>APZNEO,OH2RCH-2*": the header of the query as we heard it, the digipeaters it went by with their stars

The general query ?APRS? is a `?` packet (the information field starts with `?APRS?`), not the text of a message, and a message with that text is not answered. It may carry a target footprint,
`?APRS?V34.02,-117.15,0200` (latitude and longitude in degrees, the radius in miles; the V stands for a space and may be left out): we answer only when our position is inside it, and a footprint that does not read is
not answered. The answer is our position packet and then our status report (the status only when one has been sent or is kept), after a random delay of 0 to GENERAL_DELAY_MAX_SEC seconds, and
not again within GENERAL_EVERY_SEC of the last time it was taken. Every
answer goes by the path of the asker (the station preferences, else `beacon/path`) as frames of our own; none is a message of messaging, none is retried. The same query from the same station within
ANSWER_AGAIN_SEC (the copies of one transmission by different digipeaters, an impatient asker) is answered once."""
import asyncio
import logging
import math
import random
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Protocol

from neoaprs import ax25
from neoaprs.aprsmessage import MAX_TEXT, MessageError, format_message
from neoaprs.callsign import CallsignError
from neoaprs.interlock import Interlock
from neoaprs.clock import Clock, utcnow
from neoaprs.message import MessagingError, addressed_to, same_call
from neoaprs.packet import Message, Other, Packet
from neoaprs.services.beacon import BeaconError
from neoaprs.services.common import ConfigSource, Radio, our_frame
from neoaprs.stationbook import Station
from neoaprs.tasks import TaskSet

log = logging.getLogger("neoaprs.queries")

GENERAL = "?APRS?"
GENERAL_DELAY_MAX_SEC = 120.0
GENERAL_EVERY_SEC = 600.0
ANSWER_AGAIN_SEC = 30.0
DIRECT_WINDOW = timedelta(hours=1)
MAX_DIRECT_MESSAGES = 2
EARTH_MILES = 3958.8
_NUMBER = r"V?\s*([-+]?\d+(?:\.\d+)?)"                                     # (the V is the specification's mark of a positive value)
_FOOTPRINT = re.compile(rf"\?APRS\?(?:\s*{_NUMBER}\s*[,\s]\s*{_NUMBER}\s*[,\s]\s*(\d{{1,4}}))?", re.IGNORECASE)
_DIRECTED = {"?APRSP": "position", "?APRSS": "status", "?APRSD": "directs", "?APRST": "path", "?PING?": "path"}


class Frames(Protocol):
    """What the queries need of the beacon: the frame of our position."""
    def frame(self) -> ax25.Frame: ...


class Stations(Protocol):
    """What the queries need of the station book."""
    def stations(self) -> list[Station]: ...


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
    """"Path= OH2GBA>APZNEO,OH2RCH-2*": the header of the packet as heard, its digipeaters with their stars; the last of them go when the text would be over MAX_TEXT bytes."""
    head = f"Path= {packet.source}>{packet.destination}"
    hops = list(packet.path)
    while hops and len(f"{head},{','.join(hops)}".encode()) > MAX_TEXT:
        hops.pop()
    return f"{head},{','.join(hops)}" if hops else head


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


class Queries:
    def __init__(self, tnc: Radio, config: ConfigSource, beacon: Frames, status: Callable[[], ax25.Frame | None], book: Stations, paths: Callable[[str], tuple[str, ...]],
                 clock: Clock = utcnow, delay: Callable[[], float] = lambda: random.uniform(0.0, GENERAL_DELAY_MAX_SEC)) -> None:
        self._tnc = tnc
        self._config = config
        self._interlock = Interlock(config)
        self._beacon = beacon
        self._status = status                                   # the frame of the status as last sent (RigStatus.status_frame); None while none has been sent
        self._book = book
        self._paths = paths                                     # the digipeaters of what we send to a station (PrefBook.path_for)
        self.clock = clock
        self._delay = delay                                     # how long the answer to the general query waits
        self._answered: dict[tuple[str, str], datetime] = {}    # when each (station, query) was last answered
        self._general_until: datetime | None = None             # no general query is taken before this
        self._tasks = TaskSet(log, "queries")

    async def stop(self) -> None:
        """An answer that is waiting is not sent."""
        await self._tasks.cancel_all()

    # ---- what is asked
    def on_packet(self, packet: Packet) -> None:
        """The Tnc heard a packet: a query to us, or the general query, is answered."""
        if packet.direction != "in" or same_call(packet.sender, self._config().station_call):
            return
        decoded = packet.decoded
        if isinstance(decoded, Message):
            if decoded.ack_id is None and decoded.rej_id is None and addressed_to(decoded.addressee, self._config().station_call) and decoded.text.strip().upper() in _DIRECTED:
                self._directed(packet, _DIRECTED[decoded.text.strip().upper()])
        elif isinstance(decoded, Other) and decoded.kind == "query" and _is_general(decoded.text):
            self._general(packet, decoded.text)

    def _directed(self, packet: Packet, query: str) -> None:
        asker = packet.sender
        if self._interlock.refused("query answer"):
            return
        if self._answered_lately(asker, query, packet.heard_at):
            log.debug("the %s query of %s was answered a moment ago", query, asker)
            return
        try:
            frames = [frame for frame in self._answer(packet, query) if frame is not None]
            if frames and all([self._send(asker, frame) for frame in frames]):
                self._answered[(asker, query)] = packet.heard_at
                log.info("the %s query of %s is answered", query, asker)
        except (BeaconError, ax25.Ax25Error, CallsignError, MessageError, ValueError) as e:
            log.warning("the %s query of %s was not answered: %s", query, asker, e)

    def _answer(self, packet: Packet, query: str) -> list[ax25.Frame | None]:
        """The frames that answer the query (a None for a status not yet sent); BeaconError when the settings make no frame."""
        asker = packet.sender
        if query == "position":
            return [self._beacon.frame()]
        if query == "status":
            return [self._status()]
        if query == "directs":
            return [self._message(asker, text) for text in directs_messages(self._directs(packet.heard_at))]
        return [self._message(asker, path_text(packet))]

    def _general(self, packet: Packet, text: str) -> None:
        """?APRS?: our position and status after a random wait when we are inside its footprint (if it has one), and no second one before GENERAL_EVERY_SEC has passed."""
        if self._interlock.refused("query answer"):
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
        self._tasks.spawn(self._later(delay, packet.sender), "query-general")

    async def _later(self, delay: float, asker: str) -> None:
        await asyncio.sleep(delay)
        if self._interlock.refused("query answer"):
            return
        try:
            frames = [self._beacon.frame(), self._status()]
            for frame in frames:
                if frame is not None and not self._send(asker, frame):
                    break
        except (BeaconError, ax25.Ax25Error, CallsignError, ValueError) as e:
            log.warning("the general query of %s was not answered: %s", asker, e)

    def _answered_lately(self, asker: str, query: str, at: datetime) -> bool:
        """Whether the same station asked the same and was answered less than ANSWER_AGAIN_SEC ago."""
        self._answered = {key: when for key, when in self._answered.items() if (at - when).total_seconds() < ANSWER_AGAIN_SEC}
        return (asker, query) in self._answered

    # ---- the answers
    def _directs(self, now: datetime) -> list[str]:
        """The calls heard direct within DIRECT_WINDOW, the one heard last first (not us, not an object)."""
        heard = [(s.last_direct_at, s.call) for s in self._book.stations() if s.kind == "station" and not s.is_me and s.last_direct_at is not None and now - s.last_direct_at <= DIRECT_WINDOW]
        return [call for _, call in sorted(heard, reverse=True)]

    def _message(self, asker: str, text: str) -> ax25.Frame:
        """Our frame carrying a message to the asker, without an id (nothing is waited for)."""
        c = self._config()
        return our_frame(c, (), b":" + format_message(asker, text))

    def _send(self, asker: str, frame: ax25.Frame) -> bool:
        """Sends the frame by the asker's path; whether it went, and a word in the log when it did not."""
        if self._interlock.refused("query answer"):
            return False
        if not self._tnc.usable:
            log.warning("a query of %s is not answered: %s", asker, self._tnc.why_unusable())
            return False
        try:
            path = tuple(ax25.Address.parse(call) for call in self._paths(asker))
        except MessagingError as e:
            log.warning("a query of %s is not answered: %s", asker, e)
            return False
        if not self._tnc.send_frame(replace(frame, path=path)):
            log.warning("the answer to %s was not sent: the TNC would not take the frame", asker)
            return False
        return True
