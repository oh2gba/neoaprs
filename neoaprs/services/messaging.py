"""Messaging: APRS text messages to and from other stations, with acknowledgements and retries, kept in the database.

Outgoing (`send`): the addressee (a call, or the name of a station on the internet: callsign.normal_name) and the text (printable ASCII) are checked, the message is given the next message id (two characters: 01..99, then A0..ZZ, 0A..9Z and 00, 1296 in all, going round and skipping those of messages still being
sent) and kept with state "sending", and it is transmitted at once: a UI frame from `station/call` to the tocall by way of the station's path (below) whose information field is `:` and the message
(aprsmessage.format_message). Every message carries its number as a reply-ack, `{MM}` or, when the station has sent us a message with a reply-ack number that its ack has not reached it with, `{MM}AA`, the
id of the latest such message (services/heard.py); an attempt is made as it is, so a retry carries the latest. The attempts
are made 4 times, 2 for the email gateway (message.attempts_for; the record keeps the number: `attempts_max`), 0, 32, 64, 128, 256, 512, 1024 ... seconds after the first with no wait
longer than 960 (message.schedule_sec); the answer to the last is waited for FINAL_WAIT_SEC, then the message is "failed", or "unconfirmed" when it was given only 1 or 2 attempts (the station is not expected to ack; an ack that comes later still settles it). An ack from the addressee that quotes our id makes it "acked", a rej "rejected";
A message to a bulletin or a group (BLN*, ALL, CQ, QST, NWS-*, SKY*, CWA*: neoaprs/bulletin.py) is sent once, without an id, and kept as "unconfirmed" with one attempt; so is a directed query (`ask`: ?APRSP, ?APRSS, ?APRSD, ?APRST to a
station, once per station and kind in QUERY_EVERY_SEC: services/asking.py, through `send` with `once`), which the conversation shows as a note of what was asked. `cancel` stops a message that is being sent, `retry` sends a failed, unconfirmed, rejected or cancelled one again from the first attempt, `delete` removes a message of any kind (a message being sent is cancelled first).
While the Tnc is not connected, or the radio is silent, or transmitting is switched off (receive only: `station/transmit`), an attempt that is due waits (it is not used up, nothing fails, the waits that were running are moved on by the time it
was away) and the log says so once; a new message, and a retry, is refused at once while it is switched off (code `transmit.off`) and an ack for a message we receive is not sent (nothing is queued).

Incoming (`on_packet`, from the Tnc): the inbox (services/inbox.py) keeps a message to us (state "received"), answers it with an ack when it carries an id (`ackMM`, or the exact copy of a reply-ack number: `ackMM}` for `{MM}`, `ackMM}AA` for `{MM}AA`), and
lets an ack, a rej or the reply-ack of a message to us settle the message of ours that it quotes.

Every message is held here as well as in the database (the page's topic is made from them) and none leaves on its own: nothing is evicted and the daily care does not prune them (the operator deletes with
`delete` and `delete_conversation`). A start takes the latest MESSAGES_HELD_MAX from the database and says so in the log, as a warning, when there were more. `changed` is told with every message that is new or
different, `removed` with every one that is deleted.

Every message is kept: those to us, those we send with every change of their state, and the acks and rejects on the message they settle. A message to another station that we only hear is kept too, as
"overheard" (once for a repeat within DUPLICATE_WINDOW_SEC), apart from the conversations. A message to a bulletin or a group (BLN1, BLNA, BLN3HAMS, ALL, CQ, QST) goes to the
board (services/bulletins.py) instead, and is never acked; a query or a definition of telemetry channels is not kept at all.

A station may have a path of its own (services/prefbook.py, which the composition root gives this as `paths`: the station's own path, empty for direct; else, for attempts 1 and 2 of a message to a station, the path lately heard to reach
it (route.automatic_path, chosen when the attempt is sent), else `beacon/path`), and every message and every ack to the station goes by way of the own path, or by `beacon/path`, with RFONLY after it when the station is RF only (a path that would be more than 8 digipeaters with it is no path: a message to the station is refused, an attempt
waits, an ack is not sent, and the log says "path too long for RF only")."""
import asyncio
import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta

from neoaprs import ax25
from neoaprs.bulletin import board_slot
from neoaprs.aprsmessage import MessageError, format_ack, format_message
from neoaprs.callsign import CallsignError, normal_name
from neoaprs.clock import Clock, days, utcnow
from neoaprs.config import Config, can_transmit
from neoaprs.interlock import Interlock
from neoaprs.message import MESSAGES_HELD_MAX, MSG_IDS, UNCONFIRMED_MAX, MessageRecord, MessagingError, State, addressed_to, attempts_for, check_text, due_at, next_msg_id
from neoaprs.messagelog import MessageLog
from neoaprs.packet import Message, Packet
from neoaprs.services.common import FRAME_ERRORS, ConfigSource, Radio, our_frame
from neoaprs.services.asking import Asking
from neoaprs.services.delivery import Delivery
from neoaprs.services.inbox import Inbox
from neoaprs.services.pace import SPACING_SEC, Pace
from neoaprs.signal import Signal
from neoaprs.source import Source
from neoaprs.tasks import TaskSet

log = logging.getLogger("neoaprs.messaging")

TICK_SEC = 1.0
_RETRYABLE = ("failed", "unconfirmed", "rejected", "cancelled")


def _info(to: str, text: str, ident: str | None, reply: str | None) -> bytes:
    """The information field of a message: `:` and the body, with the reply-ack number `{ident}reply` ("" for none) when `reply` is given (the format's own refusals are told as MessagingError)."""
    try:
        return b":" + format_message(to, text, ident, reply)
    except MessageError as e:
        raise MessagingError(str(e)) from None


def _our_call(config: Config) -> str:
    """The call we send under; raises MessagingError when nothing may be transmitted: receive only (the code `transmit.off`), or the interlock's reason (no call)."""
    if not config.station_transmit:
        raise MessagingError("RX only: nothing is sent", "transmit.off")
    if reason := can_transmit(config):
        raise MessagingError(reason)
    return config.station_call


def _named(name: str) -> str:
    """A station as the overheard messages name it: a call in its normal form, else (an addressee that is no call) the text as it is."""
    try:
        return normal_name(name)
    except CallsignError:
        return name.strip()


class Messaging:
    def __init__(self, tnc: Radio, config: ConfigSource, messagelog: MessageLog, paths: Callable[[str, int | None], tuple[str, ...]], clock: Clock = utcnow, tick_sec: float = TICK_SEC,
                 board: Callable[[Packet, Message], None] | None = None, alert: Callable[[MessageRecord], None] | None = None,
                 spacing_sec: float = SPACING_SEC, qru: Callable[[Packet, Message], bool] | None = None) -> None:
        self._tnc = tnc
        self._config = config
        self._interlock = Interlock(config)
        self._log = messagelog
        self._paths = paths                                     # the digipeaters of what we send to a station, for attempt n of a message (PrefBook.path_for)
        self.clock, self.tick_sec = clock, tick_sec
        self.pace = Pace(clock, spacing_sec)                    # several messages written together go out one after the other, never in a burst
        self.changed: Signal[[MessageRecord]] = Signal("messaging_changed")
        self.removed: Signal[[MessageRecord]] = Signal("messaging_removed")
        self._records: dict[int, MessageRecord] = {}            # every message by id
        self._due: dict[int, datetime] = {}                     # the messages being sent, and when each needs attention
        self._last_id: str | None = None                        # the id the latest message of ours was given; the next is the one after
        self._down_since: datetime | None = None
        self._told_down = False
        self._refused: dict[int, str] = {}                      # the messages whose attempt cannot be made, with why: told once, not at every tick
        self._ticker: asyncio.Task[None] | None = None
        self.delivery = Delivery(messagelog)                    # the attempts of every message and the hops heard back (services/delivery.py)
        self.asking = Asking(self, clock)                       # the directed queries we send (services/asking.py)
        self.inbox = Inbox(self, config, messagelog, TaskSet(log, "messaging"), board, alert, qru)       # what the Tnc hears (services/inbox.py); `board` takes the messages to bulletins and groups, `alert` the first copy of each message to us, `qru` a request to QRU

    def records(self) -> list[MessageRecord]:
        """The messages held, the oldest first."""
        return sorted(self._records.values(), key=lambda r: r.id)

    def get(self, number: int) -> MessageRecord | None:
        return self._records.get(number)

    # ---- life
    async def start(self) -> None:
        """Takes the messages from the database, picks up the schedule of those still being sent, and starts the ticker."""
        if self._ticker is not None:
            return
        latest = await self._log.held(MESSAGES_HELD_MAX)
        if len(latest) >= MESSAGES_HELD_MAX:
            log.warning("the database holds %d messages or more: the latest %d are held and shown, the older stay in the database", MESSAGES_HELD_MAX, MESSAGES_HELD_MAX)
        heard = [*reversed(latest), *await self._log.sending()]
        for record in heard:
            if record.id not in self._records:
                self._records[record.id] = record
            self.inbox.heard.note(record, record.at)
        await self.delivery.load(self._records)
        for record in self._records.values():
            self._plan(record)
        self._last_id = next((r.msg_id for r in reversed(self.records()) if r.direction == "out" and r.msg_id in MSG_IDS), None)
        self._ticker = asyncio.get_running_loop().create_task(self._run(), name="messaging")

    async def stop(self) -> None:
        ticker, self._ticker = self._ticker, None
        if ticker is not None:
            ticker.cancel()
            await asyncio.gather(ticker, return_exceptions=True)
        await self.inbox.stop()

    # ---- sending
    async def send(self, to_call: str, text: str, once: bool = False) -> MessageRecord:
        """Keeps a new message to `to_call` and transmits it. Raises MessagingError, with the reason, when the addressee or the text is not right, the radio is silent, or the message cannot be kept. The message is given back
        as it is after the first attempt; when the Tnc is not connected it has had none yet and the attempt waits. While the call is not set (the interlock) it is refused with "set your call first". With `once` (what a
        directed query is, services/asking.py) it goes out as a message to a bulletin does: without an id, with one attempt."""
        ours = _our_call(self._config())
        board = board_slot(to_call)
        once = once or board is not None
        try:
            to = to_call.strip().upper() if board is not None else normal_name(to_call)
        except CallsignError as e:
            raise MessagingError(str(e)) from None
        if addressed_to(to, ours):
            raise MessagingError(f"{to} is our own call")
        try:
            check_text(text)
        except MessageError as e:
            raise MessagingError(str(e)) from None
        if self._tnc.state is Source.State.SILENT:
            raise MessagingError(self._tnc.why_unusable())
        self._frame(_info(to, text, None if once else MSG_IDS[0], None if once else ""), to)          # (the settings make a frame, and the text one)
        ident = None if once else self._allocate()
        record = await self._log.insert(MessageRecord(0, self.clock(), "out", ours, to, text, ident, "sending", attempts_max=1 if once else attempts_for(to)))
        if record is None:
            raise MessagingError("the message could not be kept: the database is not open")
        self.put(record)
        return self._attempt(record)

    def retry(self, number: int) -> MessageRecord:
        """Sends a failed, unconfirmed, rejected or cancelled message again, from the first attempt of the schedule."""
        _our_call(self._config())
        record = self._ours(number)
        if record.state not in _RETRYABLE:
            raise MessagingError(f"message {number} is {record.state}: only a failed, unconfirmed, rejected or cancelled message is sent again")
        record = replace(record, state="sending", attempts=0, last_attempt_at=None, acked_at=None)
        self.delivery.restart(number)
        self.put(record)
        return self._attempt(record)

    def cancel(self, number: int) -> MessageRecord:
        """Stops sending a message; it is kept, as "cancelled"."""
        record = self._ours(number)
        if record.state != "sending":
            raise MessagingError(f"message {number} is {record.state}: only a message that is being sent can be cancelled")
        record = replace(record, state="cancelled")
        self.put(record)
        return record

    async def delete(self, number: int) -> None:
        """Removes a message of any kind from the database, from here and (by `removed`) from every page; one that is being sent is cancelled first, so that no attempt is made while it goes. Raises
        MessagingError when there is no such message, or the database would not take the removal (the message is then kept, cancelled if it was being sent)."""
        record = self._records.get(number)
        if record is None:
            raise MessagingError(f"there is no message {number}")
        if record.state == "sending":
            self.put(replace(record, state="cancelled"))
        if not await self._log.delete(number):
            raise MessagingError(f"message {number} could not be removed: the database would not take it")
        self._drop(number)

    async def delete_conversation(self, call: str) -> int:
        """Removes every message of the conversation with the station (those we sent to it and those it sent to us; the ones we only overheard it sending to others are not the conversation's) from the
        database in one write, from here and (by `removed`, one for each) from every page; those being sent are cancelled first. The station's path and timeout stay. Returns how many messages the database had.
        Raises MessagingError when the call is none, when there is no message with the station, or when the database would not take the removal (the messages are then kept, those that were being sent cancelled)."""
        try:
            peer = normal_name(call)
        except CallsignError as e:
            raise MessagingError(str(e)) from None
        await asyncio.gather(*self.inbox.tasks, return_exceptions=True)          # (a message that is being kept is part of the conversation)
        held = [r for r in self._records.values() if r.state != "overheard" and r.peer == peer]
        for record in held:
            if record.state == "sending":
                self.put(replace(record, state="cancelled"))
        count = await self._log.delete_conversation(peer)
        if count is None:
            raise MessagingError(f"the conversation with {peer} could not be removed: the database would not take it")
        if not held and count == 0:
            raise MessagingError(f"there is no conversation with {peer}")
        for record in held:
            self._drop(record.id)
        return count

    async def delete_overheard(self, from_call: str, to_call: str) -> int:
        """Removes every message we only overheard `from_call` sending to `to_call` (the pair as the Messages list shows it) from the database in one write, from here and (by `removed`, one for each) from every
        page. The conversations, the messages we sent and the ones sent to us are not touched. Returns how many the database had. Raises MessagingError when there is none of that pair, or when the database
        would not take the removal (the messages are then kept)."""
        sender, addressee = _named(from_call), _named(to_call)
        await asyncio.gather(*self.inbox.tasks, return_exceptions=True)          # (a message that is being kept is part of the pair)
        held = [r for r in self._records.values() if r.state == "overheard" and r.from_call == sender and r.to_call == addressee]
        count = await self._log.delete_overheard(sender, addressee)
        if count is None:
            raise MessagingError(f"the overheard messages from {sender} to {addressee} could not be removed: the database would not take it")
        if not held and count == 0:
            raise MessagingError(f"there is no overheard message from {sender} to {addressee}")
        for record in held:
            self._drop(record.id)
        return count

    def _drop(self, number: int) -> None:
        """A message the database has removed: gone from here, from its schedule and chain, and told."""
        gone = self._records.pop(number, None)
        self._due.pop(number, None)
        self._refused.pop(number, None)
        self.delivery.drop(number)
        if gone is not None:
            self.removed.emit(gone)

    def _ours(self, number: int) -> MessageRecord:
        record = self._records.get(number)
        if record is None or record.direction != "out":
            raise MessagingError(f"there is no message {number} that we sent")
        return record

    def _allocate(self) -> str:
        """The next message id: not one that a message still being sent has."""
        ident = next_msg_id(self._last_id, {r.msg_id for r in self._records.values() if r.state == "sending" and r.msg_id is not None})
        if ident is None:
            raise MessagingError(f"{len(MSG_IDS)} messages are being sent at once: no message id is free")
        self._last_id = ident
        return ident

    def _frame(self, info: bytes, to: str, attempt: int | None = None) -> ax25.Frame:
        """Our frame to the station for this information field: from `station/call` to the tocall by way of the station's path (for attempt number `attempt` of a message to it, when it is given)."""
        c = self._config()
        try:
            return our_frame(c, self._paths(to, attempt), info)
        except MessagingError:
            raise                                                   # (the path of a station that is RF only is too long: the reason is the path's)
        except FRAME_ERRORS as e:
            raise MessagingError(f"the settings make no frame: {e}") from None

    def _radio_up(self) -> bool:
        if self._tnc.usable:
            return True
        if not self._told_down:
            self._told_down = True
            log.warning("a message is waiting and %s: its attempts wait for the radio (none is used up)", self._tnc.why_unusable())
        return False

    def _attempt(self, record: MessageRecord) -> MessageRecord:
        """Transmits the message once, when the radio can; the message as it is after that."""
        if not self._radio_up() or self.pace.too_soon():
            return record                                            # (what waits is due at the next tick)
        reply = None if record.msg_id is None else self.inbox.heard.reply_for(record.to_call, self.clock()) or ""
        try:
            frame = self._frame(_info(record.to_call, record.text, record.msg_id, reply), record.to_call, None if record.msg_id is None else record.attempts + 1)
            sent = self._tnc.send_frame(frame)
        except MessagingError as e:
            if self._refused.get(record.id) != str(e):
                self._refused[record.id] = str(e)
                log.warning("message %d to %s cannot be sent: %s (it waits)", record.id, record.to_call, e)
            return record
        self._refused.pop(record.id, None)
        if not sent:
            return record                                            # (the TNC is restarting into KISS mode, or the write failed: it is tried again at the next tick)
        at = self.pace.stamp()
        record = replace(record, attempts=record.attempts + 1, last_attempt_at=at)
        self.delivery.sent(record, tuple(str(a) for a in frame.path), at)
        if record.msg_id is None:
            record = replace(record, state="unconfirmed")                   # (a bulletin or a group message is sent once and nobody acks it)
        log.info("message %d to %s sent (attempt %d of %d): %s", record.id, record.to_call, record.attempts, record.attempts_max, record.text)
        self.put(record)
        return record

    # ---- the ticker
    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self.tick_sec)
            try:
                self._tick()
            except Exception:
                log.exception("the messaging tick failed")

    def _tick(self) -> None:
        now = self.clock()
        if not self._tnc.usable or can_transmit(self._config()) is not None:      # (the radio is away, or the interlock is shut: receive only, no call)
            self._down_since = self._down_since or now
            if any(now >= due for due in self._due.values()) and self._radio_up():
                self._interlock.refused("message")                   # (tells once)
            return
        self._told_down = False
        if self._down_since is not None:
            self._move_on(now - self._down_since)
            self._down_since = None
        for number, due in list(self._due.items()):
            record = self._records.get(number)
            if record is None or now < due:
                continue
            if record.attempts >= record.attempts_max:
                state: State = "unconfirmed" if record.attempts_max <= UNCONFIRMED_MAX else "failed"
                log.log(logging.INFO if state == "unconfirmed" else logging.WARNING, "message %d to %s is %s: no answer after %d attempts", record.id, record.to_call, state, record.attempts)
                self.put(replace(record, state=state))
            else:
                self._attempt(record)

    def _move_on(self, away: timedelta) -> None:
        """The radio was away for this long: the waits that were running did not run."""
        for number, due in self._due.items():
            record = self._records.get(number)
            if record is not None and record.attempts > 0:
                self._due[number] = due + away

    # ---- keeping
    def _plan(self, record: MessageRecord) -> None:
        due = due_at(record)
        if due is None:
            self._due.pop(record.id, None)
        else:
            self._due[record.id] = due

    def put(self, record: MessageRecord) -> None:
        """A new or changed message: held, planned, kept in the database and told."""
        known = record.id in self._records
        self._records[record.id] = record
        self._plan(record)
        if known:
            self._log.update_state(record)
        self.changed.emit(record)

    def forget_heard(self, keep_days: int) -> None:
        """The daily care: the memory of when each message was heard, which tells a repeat from a new message, is dropped for what is older than `keep_days` days. The messages themselves stay."""
        self.inbox.forget_before(self.clock() - days(keep_days))

    # ---- incoming
    def on_packet(self, packet: Packet) -> None:
        """The Tnc heard (or sent) a packet; the inbox keeps, acks or settles."""
        self.inbox.on_packet(packet)

    def echoed(self, packet: Packet, message: Message) -> None:
        """A packet from our own call was heard: a copy of a message we sent is linked to its attempt, and told when it showed a hop not known before."""
        found = self.delivery.heard(self._records.values(), packet, message)
        if found is not None:
            self.changed.emit(found)

    def ack(self, to: str, msg_id: str, reply_ack: str | None = None) -> None:
        """Acknowledges message `msg_id` of the station `to`: `ackMM`, or the number as it came for a message with a reply-ack number, `ackMM}` for `{MM}` (`reply_ack` "") and `ackMM}AA` for `{MM}AA`."""
        if self._interlock.refused("ack"):
            return                                                  # (no ack is kept for later: the sender sends again)
        try:
            if not self._tnc.send_frame(self._frame(b":" + format_ack(to, msg_id, reply_ack), to)):
                log.warning("the ack of message %s from %s was not sent: the TNC would not take it", msg_id, to)
        except (MessageError, MessagingError) as e:
            log.warning("no ack for message %s from %s: %s", msg_id, to, e)
