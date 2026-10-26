"""Asking QRU: the client side of local info (the server's is services/qru.py; the words are neoaprs/qrutext.py).

`ask` sends one message to the addressee `QRU`, as APRSISCE and YAAC do: a broadcast, so with no message id, once, not kept as a message of ours and never sent again, by the path of messages (`beacon/path`, or the one set
for the station QRU) with RFONLY after it, so that the iGates keep it off APRS-IS and only the servers in radio range answer. It is refused under the transmit interlock (RX only, no call) and while the radio is away;
one request to QRU goes on the air per ASK_EVERY_SEC, whatever it says: another within that time is refused with the seconds that are left (the servers answer one station once in that time anyway, and the channel is shared).

The servers answer with messages to us (the objects they send are objects like any other): the list of the groups they serve near us with the number of objects in each, and after the objects the line that says how
many went. Those messages are kept in Messages as every message to us is; here the servers that answered are noted for the page's topic `qru`: for each its call, its groups, the limit and range it gave, when it answered
and its last closing line. A list of groups that ends in `+` goes on in the next message of the same server (within CONTINUE_SEC). All of it, and the last request, is forgotten KEEP_FOR after it was heard."""
import asyncio
import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta

from neoaprs import ax25
from neoaprs.aprsmessage import MessageError, format_message
from neoaprs.clock import Clock, utcnow
from neoaprs.message import MessagingError, addressed_to, same_call
from neoaprs.packet import Message, Packet
from neoaprs.qrutext import ASK_EVERY_SEC, Asked, Closing, Listing, Server, ask_text, closing_of, listing_of
from neoaprs.route import rf_only_path
from neoaprs.services.common import FRAME_ERRORS, ConfigSource, Radio, our_call, our_frame
from neoaprs.signal import Signal
from neoaprs.tasks import TaskSet

log = logging.getLogger("neoaprs.qru")

ADDRESSEE = "QRU"
CONTINUE_SEC = 120                      # a list that ends in `+` is continued by the next message of the server within this time
KEEP_FOR = timedelta(hours=1)           # how long a server and the last request are remembered


class QruAsk:
    def __init__(self, tnc: Radio, config: ConfigSource, paths: Callable[[str], tuple[str, ...]], clock: Clock = utcnow) -> None:
        self._tnc = tnc
        self._config = config
        self._paths = paths                                         # the digipeaters of what we send to a station (PrefBook.path_for)
        self.clock = clock
        self.changed: Signal[[]] = Signal("qru_changed")
        self.asked: Asked | None = None
        self._servers: dict[str, Server] = {}
        self.tasks = TaskSet(log, "qru")
        self._timer: asyncio.Task[None] | None = None

    async def stop(self) -> None:
        self._timer = None
        await self.tasks.cancel_all()

    # ---- asking
    def ask(self, text: str) -> None:
        """Sends the request (INFO, NEXT or a group, and a distance: neoaprs/qrutext.py). Raises MessagingError when it is none, nothing may be transmitted (RX only, no call), the radio is away, a request went less than
        ASK_EVERY_SEC ago, whatever it said (`qru.too_soon`, with the seconds that are left) or the frame is not taken."""
        config = self._config()
        our_call(config)
        request = ask_text(text)
        if not self._tnc.usable:
            raise MessagingError(self._tnc.why_unusable())
        now = self.clock()
        if self.asked is not None and (wait := ASK_EVERY_SEC - (now - self.asked.at).total_seconds()) > 0:
            seconds = max(1, round(wait))
            raise MessagingError(f"only one request to QRU per minute: wait {seconds} s", "qru.too_soon", seconds=seconds)
        try:
            path = rf_only_path(self._paths(ADDRESSEE))
            if len(path) > ax25.MAX_PATH:
                raise MessagingError(f"path too long for RF only: {len(path)} digipeaters")
            frame = our_frame(config, path, b":" + format_message(ADDRESSEE, request, None, None))
        except MessageError as e:
            raise MessagingError(str(e)) from None
        except FRAME_ERRORS as e:
            raise MessagingError(f"the request to QRU makes no frame: {e}") from None
        if not self._tnc.send_frame(frame):
            raise MessagingError("the TNC would not take the frame")
        self.asked = Asked(request, now)
        log.info("asked QRU: %s", request)
        self._told()

    # ---- the answers
    def on_packet(self, packet: Packet) -> None:
        """A message to us that is a server's list of groups or its closing line is noted."""
        message = packet.decoded
        if packet.direction != "in" or not packet.on_air or not isinstance(message, Message) or message.ack_id is not None or message.rej_id is not None:
            return
        if not addressed_to(message.addressee, self._config().station_call):
            return
        found = listing_of(message.text) or closing_of(message.text)
        if found is None or not same_call(found.call, packet.sender):
            return
        self._prune()
        if isinstance(found, Listing):
            self._listed(packet.sender, found, packet.heard_at)
        else:
            self._closed(packet.sender, found, message.text.strip(), packet.heard_at)
        self._told()

    def _listed(self, call: str, found: Listing, at: datetime) -> None:
        before = self._servers.get(call)
        if before is not None and before.more and (at - before.at).total_seconds() <= CONTINUE_SEC:
            names = {name for name, _ in found.groups}
            groups = (*(g for g in before.groups if g[0] not in names), *found.groups)
            self._servers[call] = replace(before, groups=groups, max_objects=found.max_objects, range=found.range, unit=found.unit, at=at, more=found.more)
        else:
            self._servers[call] = Server(call, found.groups, found.max_objects, found.range, found.unit, at, found.more)

    def _closed(self, call: str, found: Closing, text: str, at: datetime) -> None:
        before = self._servers.get(call) or Server(call, (), None, None, "", at)
        self._servers[call] = replace(before, at=at, sent=text, sent_at=at)

    # ---- what the page is told
    def servers(self) -> list[Server]:
        """The servers that answered in the last KEEP_FOR, by call."""
        self._prune()
        return sorted(self._servers.values(), key=lambda s: s.call)

    def _prune(self) -> None:
        cutoff = self.clock() - KEEP_FOR
        self._servers = {call: s for call, s in self._servers.items() if s.at > cutoff}
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
