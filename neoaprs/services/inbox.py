"""What messaging does with the packets the Tnc hears: a message to us is kept (state "received") and, when it carries an id, answered at once with an ack; the same id and text from the same station
within DUPLICATE_WINDOW_SEC is not kept again, and is answered again only when it comes more than ACK_AGAIN_SEC after our last ack of it (the copies of one burst get one ack); a message to another
station is kept as "overheard"; an ack or a rej to us settles the message of ours that it quotes. A packet from our own call (a digipeater's copy of a message we sent, or an iGate's) is no message to keep: it is
handed to the host, which links it to the message it is a copy of (services/delivery.py).

A text that reads as an ack or a rej (`ack12`, `rej3`) is one only when it quotes a message of ours to that station, in any state; otherwise it is an ordinary message without an id ("rejoin"), kept and
not acked. A message whose text is a query (neoaprs/message.py `is_query`) is never acked or kept (services/queries.py answers it), and neither is a definition of telemetry channels (`PARM.`, `UNIT.`,
`EQNS.`, `BITS.`), to us or to another: those stay in the packet log.

Reply-acks (neoaprs/aprsmessage.py): the `AA` of a message `{MM}AA` to us settles our message with that id to the sender as an ack does, and is acked as `ackMM}AA`; a message with a number of that
form, `{MM}` too, tells us the sender knows reply-acks, and its id is what the next message we send it carries as its `AA` (services/heard.py) until the station answers one of ours.

A message to a bulletin, an announcement, a group bulletin, ALL, CQ or QST, or a weather service bulletin (neoaprs/bulletin.py) is no conversation and is never acked: it goes to the board
(services/bulletins.py, handed to the inbox as `board`), not to the overheard messages. With no board it is overheard like any other message to another station.

A message is to us when its addressee is our call with its SSID, exactly (no SSID and -0 are the same). A third-party packet (an iGate's copy of what the internet said) counts as its inner sender's: an
ack from the inner source settles our message, a message from it is received and acked to it. The inbox knows nothing of the schedule or of the radio: it asks its host (messaging) for the
messages held, to keep a message and to send an ack.

The first copy of a message to us is also handed to `alert` (services/alerts.py), when there is one: a repeat or another digipeater's copy, an ack, a rej, a bulletin and an overheard message are not."""
import asyncio
import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from typing import Literal, Protocol

from neoaprs.aprsmessage import line_of, reply_ack_of
from neoaprs.aprsthirdparty import header_of
from neoaprs.bulletin import board_slot
from neoaprs.callsign import CallsignError
from neoaprs.message import MessageRecord, addressed_to, is_query, is_telemetry_definition, normal_call, same_call
from neoaprs.messagelog import MessageLog
from neoaprs.packet import Message, Packet
from neoaprs.route import received_text
from neoaprs.services.common import ConfigSource
from neoaprs.services.heard import ACK_AGAIN_SEC, Heard
from neoaprs.tasks import TaskSet

log = logging.getLogger("neoaprs.messaging")

_UNSETTLED = ("sending", "failed", "unconfirmed", "cancelled")           # an ack or a rej that comes settles a message in one of these states


def _station(call: str) -> str:
    """The call as our messages name their addressee, else as it is."""
    try:
        return normal_call(call)
    except CallsignError:
        return call


def _info_of(packet: Packet) -> bytes:
    """The information field of the message: the packet's, or for a third-party packet the wrapped one's."""
    found = None if packet.third_party is None else header_of(packet.info)
    return packet.info if found is None else found[1]


def _plain_text(packet: Packet, message: Message) -> str:
    """The text of an ack or a reject that settled nothing, as it was written."""
    line = line_of(_info_of(packet))
    return line if line is not None else ("ack" + message.ack_id if message.ack_id is not None else "rej" + str(message.rej_id))


class Host(Protocol):
    """What the inbox asks of messaging."""
    def records(self) -> list[MessageRecord]: ...
    def put(self, record: MessageRecord) -> None: ...
    def ack(self, to: str, msg_id: str, reply_ack: str | None = None) -> None: ...
    def echoed(self, packet: Packet, message: Message) -> None: ...


class Inbox:
    def __init__(self, host: Host, config: ConfigSource, messagelog: MessageLog, tasks: TaskSet, board: Callable[[Packet, Message], None] | None = None,
                 alert: Callable[[MessageRecord], None] | None = None) -> None:
        self._host = host
        self._alert = alert                                     # told of a message to us the first time it is heard (services/alerts.py)
        self._board = board                                     # where a message to a bulletin or a group goes (services/bulletins.py)
        self._config = config
        self._log = messagelog
        self.heard = Heard()                                    # the messages kept and when: the repeats of a retry are not kept again
        self.tasks = tasks                                          # the keeping of the messages that came in

    def on_packet(self, packet: Packet) -> None:
        """The Tnc heard (or sent) a packet: a message to us is kept and acked, an ack or a rej to us settles the message it quotes."""
        message = packet.decoded
        if packet.direction != "in" or not isinstance(message, Message):
            return
        ours = self._config().station_call
        if is_telemetry_definition(message.text):
            return                                                   # (the packet log has it)
        if same_call(packet.sender, ours):
            self._host.echoed(packet, message)                       # (our own call: a copy of what we sent, heard back; it is not a message to keep)
            return
        if not addressed_to(message.addressee, ours):
            self._elsewhere(packet, message)
            return
        if message.ack_id is not None or message.rej_id is not None:
            if message.ack_id is not None and self._settle(packet, message.ack_id, "acked"):
                return
            if message.rej_id is not None and self._settle(packet, message.rej_id, "rejected"):
                return
            message = Message(message.addressee, _plain_text(packet, message))        # (it settles nothing of ours: the words of a person)
        self._received(packet, message)

    def _received(self, packet: Packet, message: Message) -> None:
        if is_query(message.text):
            return                                                   # (a query has no id and is not acknowledged; the queries answer it)
        line = line_of(_info_of(packet))
        reply = None if line is None else reply_ack_of(line)
        if reply:
            self._settle(packet, reply, "acked")
        record = MessageRecord(0, packet.heard_at, "in", packet.sender, message.addressee, message.text, message.msg_id, "received", route=received_text(packet.path, packet.via))
        fresh = self.heard.note(record, packet.heard_at)
        if message.msg_id is not None:
            if self.heard.ack_due(record, packet.heard_at):
                self._host.ack(packet.sender, message.msg_id, reply)
            else:
                log.debug("message %s from %s heard again within %d s of our ack: not acked again", message.msg_id, packet.sender, ACK_AGAIN_SEC)
            if reply is not None:
                self.heard.owe_reply(_station(packet.sender), message.msg_id, packet.heard_at)
        if fresh:
            self.tasks.spawn(self._keep(record), "message-keep")
            if self._alert is not None:
                self._alert(record)

    def _elsewhere(self, packet: Packet, message: Message) -> None:
        """A message to another station: the board's when it is for a bulletin or a group (an ack or a reject of those is nothing), else overheard."""
        if self._board is None or board_slot(message.addressee) is None:
            self._overheard(packet, message)
        elif message.ack_id is None and message.rej_id is None:
            self._board(packet, message)

    def _overheard(self, packet: Packet, message: Message) -> None:
        """A message to another station: kept apart from the conversations (once for a repeat or a digipeater's copy). An ack or a reject of other stations is not a message and is not kept."""
        if message.ack_id is not None or message.rej_id is not None:
            return
        record = MessageRecord(0, packet.heard_at, "in", packet.sender, message.addressee, message.text, message.msg_id, "overheard", route=received_text(packet.path, packet.via))
        if self.heard.note(record, packet.heard_at):
            self.tasks.spawn(self._keep(record), "message-keep")

    async def _keep(self, record: MessageRecord) -> None:
        kept = await self._log.insert(record)
        if kept is None:
            log.error("a message from %s could not be kept: the database is not open", record.from_call)
            return
        self._host.put(kept)

    def _settle(self, packet: Packet, msg_id: str, state: Literal["acked", "rejected"]) -> bool:
        """Settles the newest unsettled message of ours to the sender that has the id; whether the sender has a message of ours with that id at all (settled or not)."""
        source = _station(packet.sender)
        ours = sorted((r for r in self._host.records() if r.direction == "out" and r.to_call == source and r.msg_id == msg_id), key=lambda r: r.id, reverse=True)
        if not ours:
            log.debug("%s %s from %s settles no message of ours", state, msg_id, packet.sender)
            return False
        self.heard.settled(source)
        for record in ours:
            if record.state in _UNSETTLED:
                self._host.put(replace(record, state=state, acked_at=packet.heard_at if state == "acked" else None))
                log.info("message %d to %s is %s", record.id, record.to_call, state)
                break
        return True

    def forget_before(self, cutoff: datetime) -> None:
        self.heard.forget_before(cutoff)

    async def stop(self) -> None:
        """The messages that came in are kept before the database is closed."""
        await asyncio.gather(*self.tasks, return_exceptions=True)
