"""Asking QRU: the client side of local info (the server's is services/qru.py; the words are neoaprs/qrutext.py).

`ask` sends one message to the addressee `QRU`, as APRSISCE and YAAC do: a broadcast, so with no message id, once, not kept as a message of ours and never sent again, by the path of messages (`beacon/path`, or the one set
for the station QRU) with RFONLY after it, so that the iGates keep it off APRS-IS and only the servers in radio range answer. The operator may give the request a path of its own (a station that reaches the network only
through a fill-in digipeater that relays it when it is named, `OH2RDK-7,OH2RCH-2`) and leave RFONLY off; neither given is the path of messages with RFONLY, as before. It is refused under the transmit interlock (RX only, no call) and while the radio is away;
the same request goes on the air once per ASK_EVERY_SEC (the servers answer one station once in that time anyway) and any two are ASK_GAP_SEC apart (the channel is shared); a request
within either is refused with the seconds that are left. So a group can be asked for right after a server listed it.

The servers answer with messages to us (the objects they send are objects like any other): the list of the groups they serve near us with the number of objects in each, and after the objects the line that says how
many went. Those messages are kept in Messages as every message to us is; here the servers that answered are noted for the page's topic `qru`: for each its call, its groups, the limit and range it gave, when it answered
and its last closing line. A list of groups that ends in `+` goes on in the next message of the same server (within CONTINUE_SEC). All of it, and the last request, is forgotten KEEP_FOR after it was heard.

A closing line says how many objects went; whether they arrived is counted here: the objects heard on the radio from the server's call between the request it answers and ARRIVAL_GRACE_SEC after the closing line, each name once (the
server sends them at once while the digipeaters still repeat our request, so one can be lost in the collision). The page shows "sent 1 · 0 arrived" with the request to ask again. A list or a closing line that comes
within ANSWER_WINDOW_SEC of a request of ours, with no message id, is an answer and no conversation: `answers` tells the inbox, which does not keep it as a message (the packet log has it)."""
import asyncio
import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta

from neoaprs.aprsmessage import MessageError, format_message
from neoaprs.clock import Clock, utcnow
from neoaprs.coded import CodedError
from neoaprs.message import MessagingError, addressed_to, request_path, same_call
from neoaprs.packet import ItemReport, Message, ObjectReport, Packet
from neoaprs.qrutext import ANSWER_WINDOW_SEC, ARRIVAL_GRACE_SEC, ASK_EVERY_SEC, ASK_GAP_SEC, Asked, Closing, Listing, Server, ask_text, closing_of, listing_of
from neoaprs.services.common import FRAME_ERRORS, ConfigSource, Radio, our_call, our_frame
from neoaprs.signal import Signal
from neoaprs.tasks import TaskSet

log = logging.getLogger("neoaprs.qru")

ADDRESSEE = "QRU"
CONTINUE_SEC = 120                      # a list that ends in `+` is continued by the next message of the server within this time
KEEP_FOR = timedelta(hours=1)           # how long a server and the last request are remembered
REQUESTS_MAX = 16                       # the requests kept to tell which one an answer is for
HEARD_MAX = 2000                        # the objects (by sender and name) kept to be counted against an answer


class QruAsk:
    def __init__(self, tnc: Radio, config: ConfigSource, paths: Callable[[str], tuple[str, ...]], clock: Clock = utcnow) -> None:
        self._tnc = tnc
        self._config = config
        self._paths = paths                                         # the digipeaters of what we send to a station (PrefBook.path_for)
        self.clock = clock
        self.changed: Signal[[]] = Signal("qru_changed")
        self.asked: Asked | None = None
        self._sent: dict[str, datetime] = {}                          # when each request of the last ASK_EVERY_SEC went, by its text
        self._servers: dict[str, Server] = {}
        self._requests: list[Asked] = []                              # the latest requests, oldest first
        self._heard: dict[tuple[str, str], list[datetime]] = {}       # when each object (its sender and name) was heard since the first request
        self.tasks = TaskSet(log, "qru")
        self._timer: asyncio.Task[None] | None = None

    async def stop(self) -> None:
        self._timer = None
        await self.tasks.cancel_all()

    # ---- asking
    def ask(self, text: str, path: str | None = None, rf_only: bool = True) -> None:
        """Sends the request (INFO, NEXT or a group, and a distance: neoaprs/qrutext.py) by `path` (calls separated by commas, DIRECT for none; None or empty is the path of messages to QRU) with RFONLY after it
        when `rf_only`. Raises MessagingError when it is none, nothing may be transmitted (RX only, no call), the radio is away, a request went less than ASK_EVERY_SEC ago with the same text or any less than
        ASK_GAP_SEC ago (`qru.too_soon`, with the seconds that are left), the path is no path or too long with RFONLY, or the frame is not taken."""
        config = self._config()
        our_call(config)
        request = ask_text(text)
        if not self._tnc.usable:
            raise MessagingError(self._tnc.why_unusable())
        now = self.clock()
        if (wait := self._wait(request, now)) > 0:
            seconds = max(1, round(wait))
            raise MessagingError(f"too soon for another request for local info: wait {seconds} s", "qru.too_soon", seconds=seconds)
        try:
            calls = request_path(path, () if path and path.strip() else self._paths(ADDRESSEE), rf_only)
        except CodedError as e:
            raise MessagingError(str(e), e.code, **e.params) from None
        try:
            frame = our_frame(config, calls, b":" + format_message(ADDRESSEE, request, None, None))
        except MessageError as e:
            raise MessagingError(str(e)) from None
        except FRAME_ERRORS as e:
            raise MessagingError(f"the request to QRU makes no frame: {e}") from None
        if not self._tnc.send_frame(frame):
            raise MessagingError("the TNC would not take the frame")
        self.asked = Asked(request, now)
        self._requests = [*self._requests, self.asked][-REQUESTS_MAX:]
        self._sent = {text: at for text, at in self._sent.items() if (now - at).total_seconds() < ASK_EVERY_SEC} | {request: now}
        log.info("asked QRU: %s", request)
        self._told()

    def _wait(self, request: str, now: datetime) -> float:
        """The seconds before this request may go: ASK_EVERY_SEC after the same text, ASK_GAP_SEC after any."""
        same = self._sent.get(request)
        waits = [ASK_EVERY_SEC - (now - same).total_seconds()] if same is not None else []
        if self.asked is not None:
            waits.append(ASK_GAP_SEC - (now - self.asked.at).total_seconds())
        return max(waits, default=0.0)

    # ---- the answers
    def on_packet(self, packet: Packet) -> None:
        """A message to us that is a server's list of groups or its closing line is noted, and an object heard is kept to be counted when the server's closing line says how many went."""
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
        self._told()

    def answers(self, packet: Packet, message: Message) -> bool:
        """Whether the message to us is a server's answer to a request of ours (a list of groups, `+` continuation included, or a closing line, from the server it names, with no id, within ANSWER_WINDOW_SEC of a request):
        it is shown with the servers and is no conversation."""
        found = listing_of(message.text) or closing_of(message.text)
        if not packet.on_air or found is None or message.msg_id is not None or not same_call(found.call, packet.sender):
            return False
        return any(0 <= (packet.heard_at - asked.at).total_seconds() <= ANSWER_WINDOW_SEC for asked in self._requests)

    def _object(self, packet: Packet, report: ObjectReport | ItemReport) -> None:
        if not report.alive or not self._requests:
            return
        key = (packet.sender, report.name.strip())
        stamps = self._heard.setdefault(key, [])
        stamps.append(packet.heard_at)
        del stamps[:-8]
        if len(self._heard) > HEARD_MAX:
            self._heard = dict(list(self._heard.items())[-HEARD_MAX // 2:])
        server = self._servers.get(packet.sender)
        if server is not None and server.since is not None and server.since <= packet.heard_at <= self._settles(server):
            self._told()

    def _listed(self, call: str, found: Listing, at: datetime) -> None:
        before = self._servers.get(call)
        if before is not None and before.more and (at - before.at).total_seconds() <= CONTINUE_SEC:
            names = {name for name, _ in found.groups}
            groups = (*(g for g in before.groups if g[0] not in names), *found.groups)
            self._servers[call] = replace(before, groups=groups, max_objects=found.max_objects, range=found.range, unit=found.unit, at=at, more=found.more)
        else:
            asked = self._request_for("INFO", at)
            self._servers[call] = Server(call, found.groups, found.max_objects, found.range, found.unit, at, found.more, since=None if asked is None else asked.at)

    def _closed(self, call: str, found: Closing, text: str, at: datetime) -> None:
        before = self._servers.get(call) or Server(call, (), None, None, "", at)
        asked = self._request_for(found.group, at)
        self._servers[call] = replace(before, at=at, sent=text, sent_at=at, sent_objects=found.sent, request="" if asked is None else asked.text, since=None if asked is None else asked.at)

    def _request_for(self, word: str, at: datetime) -> Asked | None:
        """The request before `at` that an answer about `word` (INFO or a group) is for: the latest one that names it. A NEXT after the group's own request is read as the group asked again, with the distance of that request;
        what is counted starts at the NEXT, and what Ask again sends is the group's request."""
        names = (word,) if word == "INFO" else (word, "NEXT")
        earlier = [asked for asked in self._requests if asked.at <= at and asked.text.split()[0] in names]
        if not earlier:
            return None
        latest = earlier[-1]
        if latest.text.split()[0] == word:
            return latest
        own = next((asked for asked in reversed(earlier) if asked.text.split()[0] == word), None)
        return Asked(word if own is None else own.text, latest.at)

    @staticmethod
    def _settles(server: Server) -> datetime:
        return max(server.at, server.sent_at or server.at) + timedelta(seconds=ARRIVAL_GRACE_SEC)

    def _received(self, server: Server) -> tuple[str, ...]:
        """The names of the objects heard from the server between the request it answers and the end of the counting."""
        if server.since is None:
            return ()
        until = self._settles(server)
        return tuple(sorted({name for (sender, name), stamps in self._heard.items() if same_call(sender, server.call) and any(server.since <= at <= until for at in stamps)}))

    # ---- what the page is told
    def servers(self) -> list[Server]:
        """The servers that answered in the last KEEP_FOR, by call."""
        self._prune()
        return sorted((replace(s, received=self._received(s), settles_at=None if s.sent_objects is None else self._settles(s)) for s in self._servers.values()), key=lambda s: s.call)

    def _prune(self) -> None:
        cutoff = self.clock() - KEEP_FOR
        self._servers = {call: s for call, s in self._servers.items() if s.at > cutoff}
        self._requests = [asked for asked in self._requests if asked.at > cutoff]
        self._heard = {key: kept for key, stamps in self._heard.items() if (kept := [at for at in stamps if at > cutoff])}
        if self.asked is not None and self.asked.at <= cutoff:
            self.asked = None

    def _told(self) -> None:
        """The page is told, and the moment the oldest note is to be forgotten is waited for."""
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
            self._timer = self.tasks.spawn(self._forget(max(0.0, (min(stamps) + KEEP_FOR - self.clock()).total_seconds()) + 1), "qru-forget")
        except RuntimeError:
            self._timer = None                                      # (no loop: nobody to tell)

    async def _forget(self, wait_sec: float) -> None:
        await asyncio.sleep(wait_sec)
        self._prune()
        self._timer = None
        self._told()

    def forget(self) -> None:
        """Forgets what is older than KEEP_FOR now and tells the page when anything went."""
        before = (len(self._servers), self.asked)
        self._prune()
        if (len(self._servers), self.asked) != before:
            self._told()
