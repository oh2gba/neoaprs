"""What messaging does with the packets heard: keep messages to us, ack them, settle our messages.

A message to us is kept as "received" and acked if it has an id; one to another station is kept
as "overheard"; an ack or rej to us settles the message of ours it quotes.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from typing import Literal, Protocol

from neoaprs.aprsmessage import line_of, reply_ack_of
from neoaprs.bulletin import board_slot
from neoaprs.callsign import CallsignError, normal_name
from neoaprs.message import (
    ACK_SETTLES,
    INTERNET_ROUTE,
    MessageRecord,
    addressed_to,
    is_internet_service,
    is_query,
    is_telemetry_definition,
    same_call,
)
from neoaprs.messagelog import MessageLog
from neoaprs.packet import Message, Packet
from neoaprs.route import received_text
from neoaprs.services.common import ConfigSource
from neoaprs.services.heard import ACK_AGAIN_SEC, Heard
from neoaprs.services.qru import ADDRESSEE
from neoaprs.services.keys import Keys, NoKeys
from neoaprs.tasks import TaskSet

log = logging.getLogger("neoaprs.messaging")


def _station(call: str) -> str:
    """The call as our messages name an addressee, else unchanged."""
    try:
        return normal_name(call)
    except CallsignError:
        return call


def _plain_text(packet: Packet, message: Message) -> str:
    """The text of an ack or reject that settled nothing, as written."""
    line = line_of(packet.inner_info)
    return (
        line
        if line is not None
        else ("ack" + message.ack_id if message.ack_id is not None else "rej" + str(message.rej_id))
    )


class Host(Protocol):
    """What the inbox asks of messaging."""

    def records(self) -> list[MessageRecord]: ...
    def put(self, record: MessageRecord) -> None: ...
    def ack(self, to: str, msg_id: str, reply_ack: str | None = None, packet: Packet | None = None) -> None: ...
    def echoed(self, packet: Packet, message: Message) -> None: ...
    def internet_open(self) -> bool: ...


class Inbox:
    def __init__(
        self,
        host: Host,
        config: ConfigSource,
        messagelog: MessageLog,
        tasks: TaskSet,
        board: Callable[[Packet, Message], None] | None = None,
        alert: Callable[[MessageRecord], None] | None = None,
        qru: Callable[[Packet, Message], bool] | None = None,
        qru_answer: Callable[[Packet, Message], bool] | None = None,
        keyring: Keys | None = None,
    ) -> None:
        self._host = host
        self._keys: Keys = keyring or NoKeys()
        self._qru_answer = qru_answer
        self._qru = qru
        self._alert = alert
        self._board = board
        self._config = config
        self._log = messagelog
        self.heard = Heard()
        self.tasks = tasks

    def on_packet(self, packet: Packet) -> None:
        """Keep and ack a message to us; an ack or rej to us settles the message it quotes."""
        message = packet.decoded
        if packet.direction != "in" or not isinstance(message, Message):
            return
        ours = self._config().station_call
        if not packet.on_air and not self._from_service(packet, message, ours):
            return
        if is_telemetry_definition(message.text):
            return
        if same_call(packet.sender, ours):
            self._host.echoed(packet, message)  # a copy of what we sent, heard back
            return
        if not addressed_to(message.addressee, ours):
            self._elsewhere(packet, message)
            return
        if message.ack_id is not None or message.rej_id is not None:
            if message.ack_id is not None and self._settle(packet, message.ack_id, "acked"):
                return
            if message.rej_id is not None and self._settle(packet, message.rej_id, "rejected"):
                return
            message = Message(message.addressee, _plain_text(packet, message))  # ordinary text
        self._received(packet, message)

    def _from_service(self, packet: Packet, message: Message, ours: str) -> bool:
        """Whether a packet from the internet is a listed service's message or ack to us, taken while it carries ours."""
        return (
            is_internet_service(packet.sender) and addressed_to(message.addressee, ours) and self._host.internet_open()
        )

    def _received(self, packet: Packet, message: Message) -> None:
        if self._qru_answer is not None and message.msg_id is None and self._qru_answer(packet, message):
            return
        line = line_of(packet.inner_info)
        reply = None if line is None else reply_ack_of(line)
        if is_query(message.text):
            asked = MessageRecord(
                0, packet.heard_at, "in", packet.sender, message.addressee, message.text, message.msg_id, "received"
            )
            # A numbered query is acked: without an ack the sender retries five times.
            if message.msg_id is not None and self.heard.ack_due(asked, packet.heard_at):
                self._host.ack(packet.sender, message.msg_id, reply, packet)
            return
        if reply:
            self._settle(packet, reply, "acked")
        text, seal, wire = self._keys.opened(packet.sender, self._config().station_call, message.text)
        record = MessageRecord(
            0,
            packet.heard_at,
            "in",
            packet.sender,
            message.addressee,
            text,
            message.msg_id,
            "received",
            route=received_text(packet.path, packet.gate) if packet.on_air else INTERNET_ROUTE,
            seal=seal,
            wire=wire,
            radio_id=packet.radio_id,
            snr=packet.snr,
            rssi=packet.rssi,
        )
        fresh = self.heard.note(record, packet.heard_at)
        if message.msg_id is not None:
            if self.heard.ack_due(record, packet.heard_at):
                self._host.ack(packet.sender, message.msg_id, reply, packet)
            else:
                log.debug(
                    "message %s from %s heard again within %d s of our ack: not acked again",
                    message.msg_id,
                    packet.sender,
                    ACK_AGAIN_SEC,
                )
            if reply is not None:
                self.heard.owe_reply(_station(packet.sender), message.msg_id, packet.heard_at)
        if fresh:
            self.tasks.spawn(self._keep(record), "message-keep")
            if self._alert is not None:
                self._alert(record)

    def _elsewhere(self, packet: Packet, message: Message) -> None:
        """Route a message to another station: to the QRU server, the board, or overheard."""
        if self._to_qru(packet, message):
            return
        if self._board is None or board_slot(message.addressee) is None:
            self._overheard(packet, message)
        elif message.ack_id is None and message.rej_id is None:
            self._board(packet, message)

    def _to_qru(self, packet: Packet, message: Message) -> bool:
        """Whether the message is a QRU request the server took; never acked, whatever its id."""
        return (
            self._qru is not None
            and message.addressee.strip().upper() == ADDRESSEE
            and message.ack_id is None
            and message.rej_id is None
            and self._qru(packet, message)
        )

    def _overheard(self, packet: Packet, message: Message) -> None:
        """Keep a message to another station once, apart from conversations; skip acks/rejects."""
        if message.ack_id is not None or message.rej_id is not None:
            return
        record = MessageRecord(
            0,
            packet.heard_at,
            "in",
            packet.sender,
            message.addressee,
            message.text,
            message.msg_id,
            "overheard",
            route=received_text(packet.path, packet.gate),
            seal=self._keys.kind(message.text),
            radio_id=packet.radio_id,
            snr=packet.snr,
            rssi=packet.rssi,
        )
        if self.heard.note(record, packet.heard_at):
            self.tasks.spawn(self._keep(record), "message-keep")

    async def _keep(self, record: MessageRecord) -> None:
        if record.seal == "key" and record.state == "received":
            record = replace(record, seal=await self._keys.taken(record.from_call, record.text, record.at))
        kept = await self._log.insert(record)
        if kept is None:
            log.error("a message from %s could not be kept: the database is not open", record.from_call)
            return
        self._host.put(kept)

    def _settle(self, packet: Packet, msg_id: str, state: Literal["acked", "rejected"]) -> bool:
        """Settle our newest message to the sender with this id; return whether one exists.

        Ids wrap around, so an older message with the same id is not the one acked.
        """
        source = _station(packet.sender)
        ours = sorted(
            (r for r in self._host.records() if r.direction == "out" and r.to_call == source and r.msg_id == msg_id),
            key=lambda r: r.id,
            reverse=True,
        )
        if not ours:
            log.debug("%s %s from %s settles no message of ours", state, msg_id, packet.sender)
            return False
        self.heard.settled(source)
        record = ours[0]
        if record.state in ACK_SETTLES:
            self._host.put(
                replace(
                    record,
                    state=state,
                    acked_at=packet.heard_at if state == "acked" else None,
                    failure=None,
                    snr=packet.snr,
                    rssi=packet.rssi,
                )
            )
            log.info("message %d to %s is %s", record.id, record.to_call, state)
        return True

    def forget_before(self, cutoff: datetime) -> None:
        self.heard.forget_before(cutoff)

    async def stop(self) -> None:
        """Wait for pending message keeps to finish."""
        await asyncio.gather(*self.tasks, return_exceptions=True)
