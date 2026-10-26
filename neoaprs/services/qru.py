"""The QRU server: objects of ours that a station gets only when it asks for them.

QRU is the Morse code abbreviation for "have you anything for me?". A station sends a message to the addressee `QRU` (not to a station: any server in range answers) whose text is

    INFO          which groups of objects are served near me? (`?` asks the same; the older APRSISCE spelling puts `?` before a word, `?INFO`, `?RP70 100`)
    INFO 250      the same within 250 km instead of the usual RANGE_KM
    RP70          the objects of the group RP70 near me
    RP70 250      the same within 250 km
    NEXT          the next objects of the group last asked for

and the server answers by the asker's path with RFONLY added, as frames of its own with no message id (services/answers.py). To `INFO` it answers with a message "de OH2GBA-10:RP70(3) FOOD(1) Max 5@50km": the groups with the number of
objects in range, the objects it sends at most (ANSWER_FRAMES_MAX, the limit of the answers of the queries as well) and the range; a long list goes over two messages, the first ending in `+`. To a group it answers
with the objects of the group in range, the nearest first, at most ANSWER_FRAMES_MAX of them as object packets one at a time (SPACING_SEC apart), then a message "Sent 3 RP70 Objects Max 5@50km de OH2GBA-10"; when
more are in range the message says "Sent 5 of 12 RP70 Objects, NEXT for more. de OH2GBA-10" and `NEXT` sends the following ones. Nothing is answered where nothing is in range: a server with nothing for the asker stays quiet.
The same request from the same station within ANSWER_AGAIN_SEC is answered once. A message to QRU is not a message to us: the inbox hands it here (services/inbox.py), it is a broadcast and is never acked (also when it carries an id: an
ack from our call matches nothing at the asker), and it is never kept as ours. It is handed over only while we serve some group; without one it is an overheard message to another station as any other. Only a request heard on the radio is
answered: one that came over the internet, or as a third-party packet that an iGate took from it, is not (the asker is not in our radio range, and the answer would have no way back).

Our objects and items (services/ownobjects.py) belong to a group by the `qru_group` the operator gives them (1 to 8 upper-case letters and digits; `INFO` and `NEXT` are the words above and no group), and may be `on_request`:
never sent on the decay schedule, only to a station that asks, here or by `?APRSO`. An object with a group that is not `on_request` is beaconed as ever and answers a request as well. "In range" is the distance from the asker's
latest position in the station book to the object; of a station whose position we do not know every object is in range (it asked us, so it is within our radio range).

What this follows: the QRU server of APRSIS32 (http://aprsisce.wikidot.com/doc:qru: the query to `QRU` of `INFO` and of a group name with an optional distance, the group list "group(#) ... Max O@M", the objects of
the group near the asker, objects that are sent only on request, the next batch on "Next"), YAAC's (https://www.ka2ddo.org/ka2ddo/YAACdocs/querymenu.html: objects and items associated with a QRU group are sent again when a
request in range arrives; the standard group names AMBU, CLUB, ECHO, FIRE, FOOD, FUEL, HOSP, LIFEBOAT, LTHS, POLI, POST, RD2M, RD70, RP10, RP23, RP2M, RP6M, RP70, SRAIL, STOR, T2SRV, VETE, WOTA ...) and the replies
quoted in SA7SKY's sheet of queries (https://privat.bahnhof.se/wb758759/documents/APRS-Queries.pdf: "de DF8LS-10:RP70(10) RP2M(3) ... Max 5@50km" and the closing "Sent 5 RP70 Objects Max 5@50km de DF8LS-10"). WB2OSZ's
APRS Information Services notes that it is meant for RF near the asker, an implementation of Bob Bruninga's APRS Local Frequency Info Initiative; Bruninga's own page (aprs.org) could not be read. Left out of what the
programs above do: the limit of group size that turns a long group into a message of counts, and the QRU beacon (the symbol and group list sent on an interval)."""
import logging
import re
from collections import Counter
from collections.abc import Callable, Sequence
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
from neoaprs.services.answers import ANSWER_FRAMES_MAX, Answers
from neoaprs.services.common import ConfigSource, Radio, our_frame
from neoaprs.services.pace import SPACING_SEC
from neoaprs.station import Station

log = logging.getLogger("neoaprs.qru")

ADDRESSEE = "QRU"
RANGE_KM = 50                                                       # how far from the asker an object is offered, when the request names no distance
MAX_INFO_MESSAGES = 2                                               # the messages the list of groups goes over at most
NEXT_KEEP = timedelta(hours=1)                                      # how long the place in a group is kept for `NEXT`
_REQUEST = re.compile(r"(?P<mark>\?)?(?P<word>[A-Z0-9]{1,8})?(?:\s+(?P<km>\d{1,5}))?")


class Objects(Protocol):
    """What the QRU server needs of our objects (services/ownobjects.py)."""
    def records(self) -> list[OwnObject]: ...


class Stations(Protocol):
    """What the QRU server needs of the station book."""
    def get(self, call: str) -> Station | None: ...


@dataclass(frozen=True)
class Request:
    """What a station asked of QRU: `word` is INFO, NEXT or a group name (`?` is read as INFO), `km` the distance it named, None for the usual."""
    word: str
    km: int | None


def request_of(text: str) -> Request | None:
    """The request the text of a message to QRU makes; None for a text that is none (it is no business of a QRU server)."""
    found = _REQUEST.fullmatch(text.strip().upper())
    if found is None or (found["word"] is None and found["mark"] is None):
        return None
    word = found["word"]
    if word is None:
        word = "INFO"
    elif found["mark"] and word.startswith("APRS"):
        return None                                                 # (a query of the specification, `?APRSP`: not a request for a group)
    return Request(word, None if found["km"] is None else int(found["km"]))


def info_texts(call: str, groups: Sequence[tuple[str, int]], km: int) -> list[str]:
    """The messages that list the groups with their number of objects: "de OH2GBA-10:RP70(3) FOOD(1) Max 5@50km", at most MAX_INFO_MESSAGES of them of at most MAX_TEXT bytes (the groups that do not fit are left
    out); every one but the last ends in `+`."""
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
    def __init__(self, tnc: Radio, config: ConfigSource, objects: Objects, book: Stations, paths: Callable[[str], tuple[str, ...]], clock: Clock = utcnow, spacing_sec: float = SPACING_SEC) -> None:
        self._config = config
        self._answers = Answers(tnc, config, paths, spacing_sec)
        self._objects = objects
        self._book = book
        self.clock = clock
        self._next: dict[str, tuple[datetime, str, int, int]] = {}      # for each station: when it asked, the group, the distance and how many of its objects it has been sent

    async def stop(self) -> None:
        """An answer that is waiting is not sent."""
        await self._answers.stop()

    def heard(self, packet: Packet, message: Message) -> bool:
        """A message to QRU: answered, and True, when we serve some group and the text is a request; False for anything else (the inbox keeps it as a message overheard)."""
        request = request_of(message.text)
        if not packet.on_air or packet.via == RF_GATED or request is None or not any(o.alive and o.qru_group for o in self._objects.records()):
            return False
        asker, key = packet.sender, f"QRU {request.word} {request.km or ''}".strip()
        if self._answers.refused():
            return True
        if self._answers.lately(asker, key, packet.heard_at):
            log.debug("the request %r of %s to QRU was answered a moment ago", key, asker)
            return True
        try:
            frames = self._frames(asker, request, packet.heard_at)
            if frames:
                self._answers.deliver(asker, key, frames, packet.heard_at, True, rf_only=True)
            else:
                log.debug("the request %r of %s to QRU: nothing to answer with", key, asker)
        except (ax25.Ax25Error, CallsignError, MessageError, ValueError) as e:
            log.warning("the request %r of %s to QRU was not answered: %s", key, asker, e)
        return True

    def _frames(self, asker: str, request: Request, at: datetime) -> list[ax25.Frame]:
        """The frames that answer the request; none when nothing is in range."""
        found = self._book.get(asker)
        where = None if found is None or found.lat is None or found.lon is None else (found.lat, found.lon)
        if request.word == "NEXT":
            seen = self._next.pop(asker, None)
            if seen is None or at - seen[0] > NEXT_KEEP:
                return []
            _, group, km, done = seen
        else:
            group, km, done = request.word, request.km or RANGE_KM, 0
        near = [o for o in self._objects.records() if o.alive and o.qru_group and (where is None or distance_km(*where, o.lat, o.lon) <= km)]
        if request.word == "INFO":
            counts = sorted(Counter(o.qru_group for o in near).items())
            return [] if not counts else [self._answers.message(asker, text) for text in info_texts(self._config().station_call, counts, km)]
        return self._group_frames(asker, group, km, done, near, where, at)

    def _group_frames(self, asker: str, group: str, km: int, done: int, near: list[OwnObject], where: tuple[float, float] | None, at: datetime) -> list[ax25.Frame]:
        """The next ANSWER_FRAMES_MAX objects of the group from the `done`th, the nearest first, and the message that says how many went; the place is kept for `NEXT` when more are left."""
        ours = sorted((o for o in near if o.qru_group == group), key=lambda o: (0.0 if where is None else distance_km(*where, o.lat, o.lon), o.created_at, o.name))
        page = ours[done:done + ANSWER_FRAMES_MAX]
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
