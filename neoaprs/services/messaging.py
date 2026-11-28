"""Messaging: APRS text messages with acknowledgements and retries, kept in the database.

Sends with retries and a per-station queue, handles encrypted messages, incoming acks and
overheard messages, and picks the radio and path each message goes on."""

import asyncio
import logging
from collections.abc import Callable, Iterable
from dataclasses import replace

from neoaprs import ax25
from neoaprs.bulletin import board_slot
from neoaprs.aprsmessage import MAX_TEXT, MessageError, format_ack
from neoaprs.callsign import CallsignError, normal_name
from neoaprs.clock import Clock, days, utcnow
from neoaprs.interlock import Interlock
from neoaprs.message import (
    ACK_SETTLES,
    MESSAGES_HELD_MAX,
    MSG_IDS,
    MessageRecord,
    MessagingError,
    RETRYABLE,
    Seal,
    UNCONFIRMED_MAX,
    addressed_to,
    attempts_for,
    check_text,
    is_internet_service,
)
from neoaprs.messagelog import MessageLog
from neoaprs.packet import IS, Message, Packet
from neoaprs.services.common import ConfigSource, FRAME_ERRORS, Radio, our_call, our_frame
from neoaprs.services.acks import Acks
from neoaprs.radiospec import told
from neoaprs.radiotype import RadioId
from neoaprs.route import NO_GATE_MARKERS
from neoaprs.services.answers import as_pick
from neoaprs.services.asking import Asking
from neoaprs.services.delivery import Delivery
from neoaprs.services.inbox import Inbox
from neoaprs.services.messageradio import InternetWay, MessageRadios, info, last_run, named
from neoaprs.services.keys import Keys, NoKeys
from neoaprs.services.pace import SPACING_SEC, Pace
from neoaprs.services.radioset import AirRadio, RadioPick, ack_radio, reply_path_on
from neoaprs.services.retries import Retries
from neoaprs.signal import Signal
from neoaprs.source import Source
from neoaprs.tasks import TaskSet

log = logging.getLogger("neoaprs.messaging")

TICK_SEC = 1.0
# Bytes a later attempt may add to a frame: a reply-ack (`{MM}AA`) with a five-character id.
REPLY_ACK_ROOM = 5


def _in_line(record: MessageRecord) -> bool:
    """Return whether the message is being sent and expects an ack, so it goes one at a time."""
    return (
        record.direction == "out"
        and record.state == "sending"
        and record.msg_id is not None
        and record.attempts_max > UNCONFIRMED_MAX
    )


def _to_let_go(records: Iterable[MessageRecord]) -> MessageRecord | None:
    """Return the message to drop from memory: the oldest settled, else the oldest unacked."""
    return min((r for r in records if r.state != "sending"), key=lambda r: (r.state in ACK_SETTLES, r.id), default=None)


def _pace_running(pace: Pace, radios: MessageRadios, record: MessageRecord) -> bool:
    """Return whether the pause after the latest attempt on the message's radio is running."""
    try:
        radio = radios.peek(record)
    except MessagingError:
        return False
    return pace.too_soon(radio.id)


class Messaging:
    def __init__(
        self,
        radios: RadioPick | Radio,
        config: ConfigSource,
        messagelog: MessageLog,
        paths: Callable[[str, int | None, RadioId], tuple[str, ...]],
        clock: Clock = utcnow,
        tick_sec: float = TICK_SEC,
        board: Callable[[Packet, Message], None] | None = None,
        alert: Callable[[MessageRecord], None] | None = None,
        spacing_sec: float = SPACING_SEC,
        qru: Callable[[Packet, Message], bool] | None = None,
        qru_answer: Callable[[Packet, Message], bool] | None = None,
        keyring: Keys | None = None,
        internet: InternetWay | None = None,
    ) -> None:
        self._given = radios  # read through `as_pick` at each call
        self._internet = internet
        self.keyring: Keys = keyring or NoKeys()
        self._config = config
        self._interlock = interlock = Interlock(config)
        self._log = messagelog
        # Digipeaters for attempt n of a message on a radio (PrefBook.path_for).
        self._paths = paths
        self.clock, self.tick_sec = clock, tick_sec
        self.pace = Pace(clock, spacing_sec)
        self.changed: Signal[[MessageRecord]] = Signal("messaging_changed")
        self.removed: Signal[[MessageRecord]] = Signal("messaging_removed")
        self._records: dict[int, MessageRecord] = {}  # by id
        self.acks = Acks(
            lambda: as_pick(radios, config),
            interlock,
            lambda info, to, radio: self._frame(info, to, radio=radio),
            clock,
        )
        self.retries = Retries(self, radios, config, interlock, clock, lambda: self.tick_sec, self.acks.flush)
        # Messages whose attempt cannot be made, with the reason; logged once, not every tick.
        self._refused: dict[int, str] = {}
        self.delivery = Delivery(messagelog)
        self.message_radios = MessageRadios(radios, config, lambda number: last_run(self.delivery.attempts_of(number)))
        self.asking = Asking(self, clock)
        # `board` takes bulletin and group messages, `alert` the first copy of each message to us.
        self.inbox = Inbox(
            self, config, messagelog, TaskSet(log, "messaging"), board, alert, qru, qru_answer, self.keyring
        )

    def records(self) -> list[MessageRecord]:
        """Return the held messages, oldest first."""
        return sorted(self._records.values(), key=lambda r: r.id)

    def get(self, number: int) -> MessageRecord | None:
        return self._records.get(number)

    def queued(self, record: MessageRecord) -> bool:
        """Return whether the message waits for an earlier one to the same station to settle."""
        return (
            _in_line(record)
            and record.attempts == 0
            and any(
                other.id != record.id
                and other.to_call == record.to_call
                and _in_line(other)
                and (other.attempts > 0 or other.id < record.id)
                for other in self._records.values()
            )
        )

    def _line_of(self, record: MessageRecord) -> list[MessageRecord]:
        """Return the other queued messages to the station; this one may change their waiting."""
        return [
            other
            for other in self._records.values()
            if other.id != record.id and other.to_call == record.to_call and _in_line(other)
        ]

    async def start(self) -> None:
        """Load the messages, resume the schedule of those still being sent and start the ticker."""
        if self.retries.running:
            return
        latest = await self._log.held(MESSAGES_HELD_MAX)
        if len(latest) >= MESSAGES_HELD_MAX:
            log.warning(
                "the database holds %d messages or more: the latest %d are held and shown, the older stay in the database",
                MESSAGES_HELD_MAX,
                MESSAGES_HELD_MAX,
            )
        heard = [*reversed(latest), *await self._log.sending()]
        for record in heard:
            if record.id not in self._records:
                self._records[record.id] = record
            self.inbox.heard.note(record, record.at)
        await self.delivery.load(self._records)
        for record in self._records.values():
            self.retries.plan(record)
        self.acks.resume(self.records())
        self.retries.start()

    async def stop(self) -> None:
        await self.retries.stop()
        await self.inbox.stop()

    async def send(self, to_call: str, text: str, once: bool = False, locked: bool = False) -> MessageRecord:
        """Keep a new message, transmit it and return it as after the first attempt.

        `once` sends it without an id; `locked` seals the text. Raise MessagingError if refused."""
        ours = our_call(self._config())
        board = board_slot(to_call)
        once = once or board is not None
        try:
            to = to_call.strip().upper() if board is not None else normal_name(to_call)
        except CallsignError as e:
            raise MessagingError.of(e) from None
        if addressed_to(to, ours):
            raise MessagingError(f"{to} is our own call", "message.own_call", call=to)
        if locked:
            if board is not None or once:
                raise MessagingError("a bulletin or a query cannot be encrypted", "failed")
            return await self._send(ours, to, text, False, "open", self.keyring.sealed(ours, to, text))
        try:
            check_text(text)
        except MessageError as e:
            raise MessagingError.of(e) from None
        return await self._send(ours, to, text, once, "", None)

    async def send_key(self, to_call: str) -> MessageRecord:
        """Announce our public key to a station as an ordinary message so it can encrypt to us.

        Refused with `lock.off` while encrypted messages are off."""
        ours = our_call(self._config())
        self.keyring.refuse_unless_on()
        try:
            to = normal_name(to_call)
        except CallsignError as e:
            raise MessagingError.of(e) from None
        if addressed_to(to, ours):
            raise MessagingError(f"{to} is our own call", "message.own_call", call=to)
        return await self._send(ours, to, self.keyring.key_text(), False, "key", None)

    def internet_open(self) -> bool:
        """Whether the Internet connection carries messages to the internet services now."""
        return self._internet is not None and self._internet.carries_messages()

    def by_internet(self, to: str) -> bool:
        """Whether a message to `to` goes over the Internet connection now, not on a radio."""
        return is_internet_service(to) and self.internet_open()

    async def _send(self, ours: str, to: str, text: str, once: bool, seal: Seal, wire: str | None) -> MessageRecord:
        """Pick the radio, check the frame fits, keep the message and make the first attempt."""
        field = info(to, text if wire is None else wire, None if once else MSG_IDS[0], None if once else "")
        if self.by_internet(to):
            way = "the Internet connection"
        else:
            radio = self.message_radios.station(to)
            if radio.state is Source.State.SILENT:
                raise MessagingError.of(radio.why_unusable())
            self._frame(field, to, room=0 if once else REPLY_ACK_ROOM, radio=radio)
            way = told(radio.name, radio.id)
        ident = None if once else self.acks.allocate(self._records.values())
        record = await self._log.insert(
            MessageRecord(
                0,
                self.clock(),
                "out",
                ours,
                to,
                text,
                ident,
                "sending",
                attempts_max=1 if once else attempts_for(to),
                seal=seal,
                wire=wire,
            )
        )
        if record is None:
            raise MessagingError("the message could not be kept: the database is not open", "failed")
        self.put(record)
        log.info(
            "message %d to %s is kept: %d characters, at most %d attempts, on %s",
            record.id,
            to,
            len(text),
            record.attempts_max,
            way,
        )
        return self.attempt(record)

    def retry(self, number: int) -> MessageRecord:
        """Send a failed, unconfirmed, rejected or cancelled message again from attempt one."""
        our_call(self._config())
        record = self._ours(number)
        if record.state not in RETRYABLE:
            raise MessagingError(
                f"message {number} is {record.state}: only a failed, unconfirmed, rejected or cancelled message is sent again",
                "failed",
            )
        self._frame(
            info(
                record.to_call,
                record.text if record.wire is None else record.wire,
                record.msg_id,
                None if record.msg_id is None else "",
            ),
            record.to_call,
            None if record.msg_id is None else 1,
            room=0 if record.msg_id is None else REPLY_ACK_ROOM,
        )
        log.info(
            "message %d to %s is sent again from the first attempt (it was %s; the operator asked)",
            number,
            record.to_call,
            record.state,
        )
        record = replace(
            record, state="sending", attempts=0, last_attempt_at=None, acked_at=None, failure=None, snr=None, rssi=None
        )
        self.delivery.restart(number)
        self.message_radios.forget(number)
        self.put(record)
        return self.attempt(record)

    def cancel(self, number: int) -> MessageRecord:
        """Stop sending a message and keep it as "cancelled"."""
        record = self._ours(number)
        if record.state != "sending":
            raise MessagingError(
                f"message {number} is {record.state}: only a message that is being sent can be cancelled", "failed"
            )
        record = replace(record, state="cancelled")
        log.info(
            "message %d to %s is cancelled (the operator asked): %d of %d attempts were made",
            number,
            record.to_call,
            record.attempts,
            record.attempts_max,
        )
        self.put(record)
        return record

    async def delete(self, number: int) -> None:
        """Remove a message from the database and memory, cancelling it first if being sent.

        Raise MessagingError if there is no such message or the database refuses."""
        record = self._records.get(number)
        if record is None:
            raise MessagingError(f"there is no message {number}", "failed")
        if record.state == "sending":
            self.put(replace(record, state="cancelled"))
        if not await self._log.delete(number):
            raise MessagingError(f"message {number} could not be removed: the database would not take it", "failed")
        self._drop(number)

    async def delete_conversation(self, call: str) -> int:
        """Remove the messages sent to and received from the station; return the count.

        Raise MessagingError if there is none or the database refuses."""
        try:
            peer = normal_name(call)
        except CallsignError as e:
            raise MessagingError.of(e) from None
        # A message still being stored belongs to the conversation.
        await asyncio.gather(*self.inbox.tasks, return_exceptions=True)
        held = [r for r in self._records.values() if r.state != "overheard" and r.peer == peer]
        for record in held:
            if record.state == "sending":
                self.put(replace(record, state="cancelled"))
        count = await self._log.delete_conversation(peer)
        if count is None:
            raise MessagingError(
                f"the conversation with {peer} could not be removed: the database would not take it", "failed"
            )
        if not held and count == 0:
            raise MessagingError(f"there is no conversation with {peer}", "failed")
        for record in held:
            self._drop(record.id)
        return count

    async def delete_overheard(self, from_call: str, to_call: str) -> int:
        """Remove the messages overheard from `from_call` to `to_call`; return the count.

        Raise MessagingError if there is none of that pair or the database refuses."""
        sender, addressee = named(from_call), named(to_call)
        # A message still being stored belongs to the pair.
        await asyncio.gather(*self.inbox.tasks, return_exceptions=True)
        held = [
            r
            for r in self._records.values()
            if r.state == "overheard" and r.from_call == sender and r.to_call == addressee
        ]
        count = await self._log.delete_overheard(sender, addressee)
        if count is None:
            raise MessagingError(
                f"the overheard messages from {sender} to {addressee} could not be removed: the database would not take it",
                "failed",
            )
        if not held and count == 0:
            raise MessagingError(f"there is no overheard message from {sender} to {addressee}", "failed")
        for record in held:
            self._drop(record.id)
        return count

    def _drop(self, number: int) -> None:
        """Forget a message removed from the database or dropped from memory, and announce it."""
        gone = self._records.pop(number, None)
        self.retries.forget(number)
        self._refused.pop(number, None)
        self.delivery.drop(number)
        self.message_radios.forget(number)
        if gone is not None:
            self.removed.emit(gone)

    def _ours(self, number: int) -> MessageRecord:
        record = self._records.get(number)
        if record is None or record.direction != "out":
            raise MessagingError(f"there is no message {number} that we sent", "failed")
        return record

    def radio_of(self, record: MessageRecord) -> AirRadio | None:
        """Return the radio the message goes out on, or None (no email radio, no radio at all)."""
        try:
            return self.message_radios.of(record)
        except MessagingError:
            return None

    def text_max(self, to: str) -> int | None:
        """Return the bytes of text a message to the station holds on its radio now, where fewer than MAX_TEXT fit.

        None where the whole text fits, the radio has no frame limit, or no frame can be made."""
        if self.by_internet(to):
            return None
        try:
            radio = self.message_radios.station(to)
            limit = radio.max_frame
            if limit is None:
                return None
            empty = len(ax25.encode(self._frame(info(to, "x", MSG_IDS[0], ""), to, radio=radio))) - 1
        except MessagingError:
            return None
        room = limit - empty - REPLY_ACK_ROOM
        return max(0, room) if room < MAX_TEXT else None

    def radio_now(self, record: MessageRecord) -> AirRadio | None:
        """Return what `radio_of` would give, keeping and logging nothing; None if there is none."""
        try:
            return self.message_radios.peek(record)
        except MessagingError:
            return None

    def _frame(
        self, field: bytes, to: str, attempt: int | None = None, room: int = 0, radio: AirRadio | None = None
    ) -> ax25.Frame:
        """Return our frame to the station on `radio` (default: the station's own).

        Raise MessagingError if the frame plus `room` bytes for a reply-ack exceeds the cap."""
        c = self._config()
        radio = radio or self.message_radios.station(to)
        try:
            frame = our_frame(c, reply_path_on(radio, c, self._paths(to, attempt, radio.id)), field)
        except MessagingError:
            raise  # e.g. an RF-only path that is too long
        except FRAME_ERRORS as e:
            raise MessagingError.of(e, f"the settings make no frame: {e}") from None
        limit = radio.max_frame
        if limit is not None and (length := len(ax25.encode(frame)) + room) > limit:
            raise MessagingError(
                f"the message is {length} bytes on the air, the radio carries {limit}: shorten it by {length - limit} characters",
                "message.too_long_for_radio",
                length=length,
                max=limit,
                cut=length - limit,
            )
        return frame

    def attempt(self, record: MessageRecord) -> MessageRecord:
        """Transmit the message once if the radio is up, its pause is over and it is not `queued`.

        Return the message as it is afterwards."""
        if record.direction == "out" and self.by_internet(record.to_call):
            return record if self.queued(record) else self._attempt_internet(record)
        if (
            self.queued(record)
            or not self.retries.radio_up(record)
            or _pace_running(self.pace, self.message_radios, record)
        ):
            return record  # still due at the next tick
        reply = None if record.msg_id is None else self.inbox.heard.reply_for(record.to_call, self.clock()) or ""
        try:
            radio = self.message_radios.of(record)
            frame = self._frame(
                info(record.to_call, record.text if record.wire is None else record.wire, record.msg_id, reply),
                record.to_call,
                None if record.msg_id is None else record.attempts + 1,
                radio=radio,
            )
            sent = radio.send_frame(frame)
        except MessagingError as e:
            if e.code == "message.too_long_for_radio":
                return self.retries.end_too_long(record, e)
            if self._refused.get(record.id) != str(e):
                self._refused[record.id] = str(e)
                log.warning("message %d to %s cannot be sent: %s (it waits)", record.id, record.to_call, e)
            return record
        self._refused.pop(record.id, None)
        if not sent:
            # The TNC is restarting or the write failed; retried at the next tick.
            return record
        at = self.pace.stamp(radio.id)
        self.message_radios.sent(record, radio, at)
        record = replace(record, attempts=record.attempts + 1, last_attempt_at=at)
        self.delivery.sent(record, tuple(str(a) for a in frame.path), at, radio.id)
        if record.msg_id is None:
            record = replace(record, state="unconfirmed")  # sent once; nobody acks it
        log.info(
            "message %d to %s sent on %s (attempt %d of %d): %s",
            record.id,
            record.to_call,
            told(radio.name, radio.id),
            record.attempts,
            record.attempts_max,
            record.text if record.wire is None else record.wire,
        )
        self.put(record)
        return record

    def _attempt_internet(self, record: MessageRecord) -> MessageRecord:
        """Put the message on APRS-IS once; return it as it is afterwards (unchanged if the link refused)."""
        reply = None if record.msg_id is None else self.inbox.heard.reply_for(record.to_call, self.clock()) or ""
        text = record.text if record.wire is None else record.wire
        if self._internet is None or not self._internet.send_ours(info(record.to_call, text, record.msg_id, reply)):
            return record
        at = self.clock()
        record = replace(record, attempts=record.attempts + 1, last_attempt_at=at)
        self.delivery.sent(record, (), at, internet=True)
        if record.msg_id is None:
            record = replace(record, state="unconfirmed")
        log.info(
            "message %d to %s sent over the Internet connection (attempt %d of %d): %s",
            record.id,
            record.to_call,
            record.attempts,
            record.attempts_max,
            text,
        )
        self.put(record)
        return record

    def put(self, record: MessageRecord) -> None:
        """Hold, schedule, store and announce a new or changed message (and the queue it is in)."""
        before = self._records.get(record.id)
        self._records[record.id] = record
        if (
            before is None
            and len(self._records) > MESSAGES_HELD_MAX
            and (oldest := _to_let_go(self._records.values())) is not None
        ):
            self._drop(oldest.id)  # stays in the database
        if record.state != "sending":
            self.message_radios.forget(record.id)
        self.retries.plan(record)
        if before is not None:
            self._log.update_state(record)
        self.changed.emit(record)
        if record.direction == "out" and (before is None or before.state != record.state):
            for other in self._line_of(record):
                self.changed.emit(other)

    def forget_heard(self, keep_days: int) -> None:
        """Drop heard-times older than `keep_days` days, which tell a repeat from a new message."""
        self.inbox.forget_before(self.clock() - days(keep_days))

    def on_packet(self, packet: Packet) -> None:
        """Pass a heard or sent packet to the inbox."""
        self.inbox.on_packet(packet)

    def from_internet(self, packet: Packet) -> None:
        """Take a packet from APRS-IS: only a listed service's message or ack to us is used (Inbox)."""
        if packet.via == IS:
            self.inbox.on_packet(packet)

    def echoed(self, packet: Packet, message: Message) -> None:
        """Link a heard copy of our message to its attempt; announce it if it showed a new hop."""
        found = self.delivery.heard(self._records.values(), packet, message)
        if found is not None:
            self.changed.emit(found)

    def ack(self, to: str, msg_id: str, reply_ack: str | None = None, packet: Packet | None = None) -> None:
        """Acknowledge message `msg_id` of station `to` on the radio the message (`packet`) came on.

        The ack is `ackMM`, or `ackMM}` / `ackMM}AA` when the message carried a reply-ack. It is RF
        only when the message was; one that came over the Internet connection is acked there."""
        if packet is not None and packet.via == IS:
            self._ack_internet(to, msg_id, reply_ack)
            return
        self.acks.send(
            to,
            msg_id,
            reply_ack,
            None if packet is None else ack_radio(as_pick(self._given, self._config), packet, to),
            rf_only=packet is not None and any(hop.rstrip("*") in NO_GATE_MARKERS for hop in packet.path),
        )

    def _ack_internet(self, to: str, msg_id: str, reply_ack: str | None) -> None:
        if self._interlock.refused("ack"):
            return
        try:
            field = b":" + format_ack(to, msg_id, reply_ack)
        except MessageError as e:
            log.warning("no ack for message %s from %s: %s", msg_id, to, e)
            return
        if self._internet is None or not self._internet.send_ours(field):
            log.warning(
                "the ack of message %s from %s was not sent: the Internet connection would not take it", msg_id, to
            )
