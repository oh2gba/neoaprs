"""The QRU server: own objects that a station gets only when it asks for them.

A station messages `QRU` with INFO, a group name or NEXT, and an optional range in km. Requests
heard on the radio are answered with message and object frames, nearest first."""

import logging
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from neoaprs import ax25
from neoaprs.aprsmessage import MAX_TEXT, MessageError
from neoaprs.callsign import CallsignError
from neoaprs.clock import Clock, utcnow
from neoaprs.geo import distance_km
from neoaprs.ownobject import OwnObject, info_of
from neoaprs.packet import RF_GATED, Message, Packet
from neoaprs.services.answers import ANSWER_FRAMES_MAX, Answers, AnswerBudget, as_pick
from neoaprs.services.common import ConfigSource, Paths, Radio, our_frame
from neoaprs.services.radioset import RadioPick, answerable
from neoaprs.services.pace import SPACING_SEC
from neoaprs.station import Station

log = logging.getLogger("neoaprs.qru")

ADDRESSEE = "QRU"
RANGE_KM = 50
# The digipeaters are still repeating the request; an answer sent at once collides with them.
FIRST_WAIT_SEC = 5.0
MAX_INFO_MESSAGES = 2
NEXT_KEEP = timedelta(hours=1)
_REQUEST = re.compile(r"(?P<mark>\?)?(?P<word>[A-Z0-9]{1,8})?(?:\s+(?P<km>\d{1,5}))?")


class Objects(Protocol):
    def records(self) -> list[OwnObject]: ...


class Stations(Protocol):
    def get(self, call: str) -> Station | None: ...


@dataclass(frozen=True)
class Request:
    """A request to QRU: `word` is INFO, NEXT or a group name; `km` is None for the default."""

    word: str
    km: int | None


def request_of(text: str) -> Request | None:
    """Return the request the message text makes, or None if it is not one."""
    found = _REQUEST.fullmatch(text.strip().upper())
    if found is None or (found["word"] is None and found["mark"] is None):
        return None
    word = found["word"]
    if word is None:
        word = "INFO"
    elif found["mark"] and word.startswith("APRS"):
        # a query of the specification such as `?APRSP`, not a group
        return None
    return Request(word, None if found["km"] is None else int(found["km"]))


def info_texts(call: str, groups: Sequence[tuple[str, int]], km: int) -> list[str]:
    """Return the messages listing the groups with counts; groups that do not fit are left out.

    Every message but the last ends in `+`."""
    head, foot = f"de {call}:", f" Max {ANSWER_FRAMES_MAX}@{km}km"
    lines = [head]
    for group, count in groups:
        token = f"{group}({count})"
        if len(lines[-1]) + 1 + len(token) + len(foot) > MAX_TEXT:
            if len(lines) == MAX_INFO_MESSAGES:
                break
            lines.append(head)
        lines[-1] += token if lines[-1] == head else " " + token
    return [line + "+" for line in lines[:-1]] + [lines[-1] + foot]


class Qru:
    def __init__(
        self,
        radios: RadioPick | Radio,
        config: ConfigSource,
        objects: Objects,
        book: Stations,
        paths: Paths,
        clock: Clock = utcnow,
        spacing_sec: float = SPACING_SEC,
        first_wait_sec: float = FIRST_WAIT_SEC,
        budget: AnswerBudget | None = None,
    ) -> None:
        self._config = config
        self.first_wait_sec = first_wait_sec
        self._given = radios
        self._answers = Answers(
            radios, config, paths, spacing_sec, budget if budget is not None else AnswerBudget(clock)
        )
        self._objects = objects
        self._book = book
        self.clock = clock
        # per asker: when it asked, the group, the distance, how many objects were sent
        self._next: dict[str, tuple[datetime, str, int, int]] = {}

    async def stop(self) -> None:
        """Drop answers that are still waiting."""
        await self._answers.stop()

    def heard(self, packet: Packet, message: Message) -> bool:
        """Answer a message to QRU; return False if it is no request, so the inbox keeps it."""
        request = request_of(message.text)
        if (
            not packet.on_air
            or packet.via == RF_GATED
            or request is None
            or not any(o.alive and o.qru_group for o in self._objects.records())
        ):
            return False
        asker, key = packet.sender, f"QRU {request.word} {request.km or ''}".strip()
        if self._answers.refused() or not answerable(as_pick(self._given, self._config), packet):
            return True
        if self._answers.lately(asker, key, packet.heard_at):
            log.debug("the request %r of %s to QRU was answered a moment ago", key, asker)
            return True
        try:
            frames = self._frames(asker, request, packet.heard_at)
            if frames:
                self._answers.deliver(
                    asker,
                    key,
                    frames,
                    packet.heard_at,
                    True,
                    rf_only=True,
                    first_after_sec=self.first_wait_sec,
                    radio=as_pick(self._given, self._config).for_packet(packet),
                )
            else:
                log.debug("the request %r of %s to QRU: nothing to answer with", key, asker)
        except (ax25.Ax25Error, CallsignError, MessageError, ValueError) as e:
            log.warning("the request %r of %s to QRU was not answered: %s", key, asker, e)
        return True

    def _frames(self, asker: str, request: Request, at: datetime) -> list[ax25.Frame]:
        """Return the frames that answer the request, none when nothing is in range."""
        found = self._book.get(asker)
        where = None if found is None or found.lat is None or found.lon is None else (found.lat, found.lon)
        if request.word == "NEXT":
            seen = self._next.pop(asker, None)
            if seen is None or at - seen[0] > NEXT_KEEP:
                return []
            _, group, km, done = seen
        else:
            group, km, done = request.word, request.km or RANGE_KM, 0
        near = [
            o
            for o in self._objects.records()
            if o.alive and o.qru_group and (where is None or distance_km(*where, o.lat, o.lon) <= km)
        ]
        if request.word == "INFO":
            counts = sorted(Counter(o.qru_group for o in near).items())
            return (
                []
                if not counts
                else [
                    self._answers.message(asker, text) for text in info_texts(self._config().station_call, counts, km)
                ]
            )
        return self._group_frames(asker, group, km, done, near, where, at)

    def _group_frames(
        self,
        asker: str,
        group: str,
        km: int,
        done: int,
        near: list[OwnObject],
        where: tuple[float, float] | None,
        at: datetime,
    ) -> list[ax25.Frame]:
        """Return the next objects after `done`, nearest first, and the summary."""
        ours = sorted(
            (o for o in near if o.qru_group == group),
            key=lambda o: (0.0 if where is None else distance_km(*where, o.lat, o.lon), o.created_at, o.name),
        )
        page = ours[done : done + ANSWER_FRAMES_MAX]
        if not page:
            return []
        c = self._config()
        sent = done + len(page)
        if sent < len(ours):
            self._next = {who: place for who, place in self._next.items() if at - place[0] <= NEXT_KEEP}
            self._next[asker] = (at, group, km, sent)
            text = f"Sent {len(page)} of {len(ours)} {group} Objects, NEXT for more. de {c.station_call}"
        else:
            text = f"Sent {len(page)} {group} Objects Max {ANSWER_FRAMES_MAX}@{km}km de {c.station_call}"
        return [*[our_frame(c, (), info_of(o, self.clock())) for o in page], self._answers.message(asker, text)]
