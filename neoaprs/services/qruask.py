"""Client side of local info: ask the QRU servers for their groups and objects, track the answers.

A request is a broadcast message to QRU with RFONLY added, refused inside a wait or under the
transmit interlock. The servers that answered are kept for KEEP_FOR; arrival of objects is counted.
"""

import asyncio
import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from neoaprs.aprsmessage import MessageError, format_message
from neoaprs.clock import Clock, utcnow
from neoaprs.coded import CodedError
from neoaprs.message import MessagingError, addressed_to, request_path, same_call
from neoaprs.packet import ItemReport, Message, ObjectReport, Packet
from neoaprs.qrutext import (
    ANSWER_WINDOW_SEC,
    ARRIVAL_GRACE_SEC,
    ASK_EVERY_SEC,
    ASK_GAP_SEC,
    Asked,
    Closing,
    Listing,
    Server,
    ask_text,
    closing_of,
    listing_of,
)
from neoaprs.radiotype import RadioId
from neoaprs import ax25
from neoaprs.services.common import (
    FRAME_ERRORS,
    ConfigSource,
    Paths,
    Radio,
    asked_radios,
    on_words,
    our_call,
    our_frame,
    send_on,
    sent_on,
)
from neoaprs.services.qru import ADDRESSEE
from neoaprs.services.radioset import AirRadio, RadioPick, path_on
from neoaprs.signal import Signal
from neoaprs.tasks import TaskSet

log = logging.getLogger("neoaprs.qru")

CONTINUE_SEC = 120
# how long a server and the last request are remembered
KEEP_FOR = timedelta(hours=1)
# requests kept to tell which one an answer is for
REQUESTS_MAX = 16
# objects (by sender and name) kept to be counted against an answer
HEARD_MAX = 2000


@dataclass(frozen=True, slots=True)
class AskedOn(Asked):
    """A request sent, with the radios it went on."""

    radios: tuple[RadioId, ...] = ()


def _radios_of(asked: Asked) -> tuple[RadioId, ...]:
    return asked.radios if isinstance(asked, AskedOn) else ()


def _on_radio(radios: tuple[RadioId, ...], came: RadioId | None) -> bool:
    """Return whether a packet from radio `came` counts for a request sent on `radios`."""
    return not radios or came is None or came in radios


class QruAsk:
    def __init__(self, radios: RadioPick | Radio, config: ConfigSource, paths: Paths, clock: Clock = utcnow) -> None:
        self._given = radios
        self._config = config
        self._paths = paths
        self.clock = clock
        self.changed: Signal[[]] = Signal("qru_changed")
        self.asked: Asked | None = None
        # when each request of the last ASK_EVERY_SEC went, by radio and text
        self._sent: dict[tuple[RadioId, str], datetime] = {}
        self._servers: dict[str, Server] = {}
        # latest requests, oldest first
        self._requests: list[Asked] = []
        # when each object (sender, name) was heard since the first request, and on which radio
        self._heard: dict[tuple[str, str], list[tuple[datetime, RadioId | None]]] = {}
        self.tasks = TaskSet(log, "qru")
        self._timer: asyncio.Task[None] | None = None

    async def stop(self) -> None:
        self._timer = None
        await self.tasks.cancel_all()

    # ---- asking
    def ask(self, text: str, path: str | None = None, rf_only: bool = True, *, radio: RadioId | None = None) -> None:
        """Send the request on each radio of Local info's Send on, or on `radio` if named.

        Raise MessagingError, sending nothing, if a target radio is in a wait or makes no frame."""
        config = self._config()
        our_call(config)
        request = ask_text(text)
        on = asked_radios(self._given, self._config, "local_info", radio)
        now = self.clock()
        held = on if radio is not None else send_on(self._given, self._config, "local_info")
        if (wait := max((self._wait(request, one.id, now) for one in held), default=0.0)) > 0:
            seconds = max(1, round(wait))
            raise MessagingError(
                f"too soon for another request for local info: wait {seconds} s", "qru.too_soon", seconds=seconds
            )
        # every frame is made before any is sent: a path that fails on one radio sends nothing
        frames = [(one, self._frame(one, request, path, rf_only)) for one in on]
        went = [one for one, _ in sent_on(frames, "asking QRU")]
        self.asked = AskedOn(request, now, tuple(one.id for one in went))
        self._requests = [*self._requests, self.asked][-REQUESTS_MAX:]
        self._sent = {key: at for key, at in self._sent.items() if (now - at).total_seconds() < ASK_EVERY_SEC} | {
            (one.id, request): now for one in went
        }
        for one in went:
            log.info("asked QRU: %s%s", request, on_words(one, self._given, self._config))
        self._told()

    def _frame(self, radio: AirRadio, request: str, path: str | None, rf_only: bool) -> ax25.Frame:
        """Return the request as a message to QRU for the radio, by the given or usual path."""
        config = self._config()
        try:
            calls = path_on(
                radio,
                config,
                request_path(path, () if path and path.strip() else self._paths(ADDRESSEE, None, radio.id), rf_only),
            )
        except CodedError as e:
            raise MessagingError(str(e), e.code, **e.params) from None
        try:
            return our_frame(config, calls, b":" + format_message(ADDRESSEE, request, None, None))
        except MessageError as e:
            raise MessagingError.of(e) from None
        except FRAME_ERRORS as e:
            raise MessagingError.of(e, f"the request to QRU makes no frame: {e}") from None

    def _wait(self, request: str, radio: RadioId, now: datetime) -> float:
        """Return the seconds before the request may go on the radio."""
        same = self._sent.get((radio, request))
        waits = [ASK_EVERY_SEC - (now - same).total_seconds()] if same is not None else []
        latest = next((asked for asked in reversed(self._requests) if _on_radio(_radios_of(asked), radio)), None)
        if latest is not None:
            waits.append(ASK_GAP_SEC - (now - latest.at).total_seconds())
        return max(waits, default=0.0)

    # ---- the answers
    def on_packet(self, packet: Packet) -> None:
        """Note a server's group list or closing line; keep heard objects to count against it."""
        if packet.direction != "in" or not packet.on_air:
            return
        decoded = packet.decoded
        if isinstance(decoded, ObjectReport | ItemReport):
            self._object(packet, decoded)
            return
        if not isinstance(decoded, Message) or decoded.ack_id is not None or decoded.rej_id is not None:
            return
        if not addressed_to(decoded.addressee, self._config().station_call):
            return
        found = listing_of(decoded.text) or closing_of(decoded.text)
        if found is None or not same_call(found.call, packet.sender):
            return
        self._prune()
        if isinstance(found, Listing):
            self._listed(packet.sender, found, packet.heard_at)
        else:
            self._closed(packet.sender, found, decoded.text.strip(), packet.heard_at)
        if packet.radio_id is not None and any(
            _on_radio(_radios_of(asked), packet.radio_id) for asked in self._requests
        ):
            # the radio it answered on, among those asked; a copy another radio heard says nothing
            self._servers[packet.sender] = replace(self._servers[packet.sender], radio=packet.radio_id)
        self._told()

    def answers(self, packet: Packet, message: Message) -> bool:
        """Return whether the message answers a request: a group list or closing line without an id
        from the server it names, within ANSWER_WINDOW_SEC of a request."""
        found = listing_of(message.text) or closing_of(message.text)
        if not packet.on_air or found is None or message.msg_id is not None or not same_call(found.call, packet.sender):
            return False
        return any(0 <= (packet.heard_at - asked.at).total_seconds() <= ANSWER_WINDOW_SEC for asked in self._requests)

    def _object(self, packet: Packet, report: ObjectReport | ItemReport) -> None:
        if not report.alive or not self._requests:
            return
        key = (packet.sender, report.name.strip())
        stamps = self._heard.setdefault(key, [])
        stamps.append((packet.heard_at, packet.radio_id))
        del stamps[:-8]
        if len(self._heard) > HEARD_MAX:
            self._heard = dict(list(self._heard.items())[-HEARD_MAX // 2 :])
        server = self._servers.get(packet.sender)
        if server is not None and server.since is not None and server.since <= packet.heard_at <= self._settles(server):
            self._told()

    def _listed(self, call: str, found: Listing, at: datetime) -> None:
        before = self._servers.get(call)
        if before is not None and before.more and (at - before.at).total_seconds() <= CONTINUE_SEC:
            names = {name for name, _ in found.groups}
            groups = (*(g for g in before.groups if g[0] not in names), *found.groups)
            self._servers[call] = replace(
                before,
                groups=groups,
                max_objects=found.max_objects,
                range=found.range,
                unit=found.unit,
                at=at,
                more=found.more,
            )
        else:
            asked = self._request_for("INFO", at)
            self._servers[call] = Server(
                call,
                found.groups,
                found.max_objects,
                found.range,
                found.unit,
                at,
                found.more,
                since=None if asked is None else asked.at,
                radio=None if before is None else before.radio,
            )

    def _closed(self, call: str, found: Closing, text: str, at: datetime) -> None:
        before = self._servers.get(call) or Server(call, (), None, None, "", at)
        asked = self._request_for(found.group, at)
        self._servers[call] = replace(
            before,
            at=at,
            sent=text,
            sent_at=at,
            sent_objects=found.sent,
            request="" if asked is None else asked.text,
            since=None if asked is None else asked.at,
        )

    def _request_for(self, word: str, at: datetime) -> Asked | None:
        """Return the latest request before `at` that names `word` (INFO or a group).

        A later NEXT counts as the group asked again, with the group request's distance."""
        names = (word,) if word == "INFO" else (word, "NEXT")
        earlier = [asked for asked in self._requests if asked.at <= at and asked.text.split()[0] in names]
        if not earlier:
            return None
        latest = earlier[-1]
        if latest.text.split()[0] == word:
            return latest
        own = next((asked for asked in reversed(earlier) if asked.text.split()[0] == word), None)
        return AskedOn(word if own is None else own.text, latest.at, _radios_of(latest))

    @staticmethod
    def _settles(server: Server) -> datetime:
        return max(server.at, server.sent_at or server.at) + timedelta(seconds=ARRIVAL_GRACE_SEC)

    def _received(self, server: Server) -> tuple[str, ...]:
        """Return the names of objects heard from the server on its request's radios, each once."""
        if server.since is None:
            return ()
        until = self._settles(server)
        radios = next((_radios_of(asked) for asked in reversed(self._requests) if asked.at == server.since), ())
        return tuple(
            sorted(
                {
                    name
                    for (sender, name), stamps in self._heard.items()
                    if same_call(sender, server.call)
                    and any(server.since <= at <= until and _on_radio(radios, came) for at, came in stamps)
                }
            )
        )

    # ---- what the page is told
    def servers(self) -> list[Server]:
        """Return the servers that answered in the last KEEP_FOR, by call."""
        self._prune()
        return sorted(
            (
                replace(s, received=self._received(s), settles_at=None if s.sent_objects is None else self._settles(s))
                for s in self._servers.values()
            ),
            key=lambda s: s.call,
        )

    def _prune(self) -> None:
        cutoff = self.clock() - KEEP_FOR
        self._servers = {call: s for call, s in self._servers.items() if s.at > cutoff}
        self._requests = [asked for asked in self._requests if asked.at > cutoff]
        self._heard = {
            key: kept
            for key, stamps in self._heard.items()
            if (kept := [(at, came) for at, came in stamps if at > cutoff])
        }
        if self.asked is not None and self.asked.at <= cutoff:
            self.asked = None

    def _told(self) -> None:
        """Notify the page and schedule the forgetting of the oldest note."""
        self.changed.emit()
        self._arm()

    def _arm(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        stamps = [s.at for s in self._servers.values()] + ([self.asked.at] if self.asked is not None else [])
        if not stamps:
            return
        try:
            self._timer = self.tasks.spawn(
                self._forget(max(0.0, (min(stamps) + KEEP_FOR - self.clock()).total_seconds()) + 1), "qru-forget"
            )
        except RuntimeError:
            # no running loop: nobody to notify
            self._timer = None

    async def _forget(self, wait_sec: float) -> None:
        await asyncio.sleep(wait_sec)
        self._prune()
        self._timer = None
        self._told()

    def forget(self) -> None:
        """Forget what is older than KEEP_FOR and notify the page if anything went."""
        before = (len(self._servers), self.asked)
        self._prune()
        if (len(self._servers), self.asked) != before:
            self._told()
