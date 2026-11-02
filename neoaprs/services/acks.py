"""The ids and acks of messaging: the message id a message of ours is given (the next after the latest, never one that a message still being sent has) and the ack we send for a message to us, `ackMM`, or the
number as it came for a message with a reply-ack number (`ackMM}` for `{MM}`, `ackMM}AA` for `{MM}AA`). An ack is not kept for later when the interlock is shut: the sender sends again. An ack the radio cannot take
at the moment, though it is connected (a frame of ours is on the air, the channel is busy, the TNC settles: the Mercury HF modem decodes a frame while the sender's tail is still on the air, and its busy detector holds
us for a second or two after it), waits and goes when the radio takes frames again (`flush`, from the ticker of the retries), for at most ACK_HOLD_MAX_SEC; after that the sender has sent again anyway."""
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from neoaprs import ax25
from neoaprs.aprsmessage import MessageError, format_ack
from neoaprs.clock import Clock, utcnow
from neoaprs.interlock import Interlock
from neoaprs.message import MSG_IDS, MessageRecord, MessagingError, next_msg_id
from neoaprs.services.common import Radio
from neoaprs.source import Source

log = logging.getLogger("neoaprs.messaging")

ACK_HOLD_MAX_SEC = 60                   # how long an ack waits for a radio that is held; a sender's first retry comes 32 s after its message, so a longer wait would ack a copy that is on its way already


@dataclass(frozen=True)
class Waiting:
    to: str
    msg_id: str
    reply_ack: str | None
    until: datetime


class Acks:
    def __init__(self, tnc: Radio, interlock: Interlock, frame: Callable[[bytes, str], ax25.Frame], clock: Clock = utcnow) -> None:
        self._tnc = tnc
        self._interlock = interlock
        self._frame = frame                                     # our frame for an information field to a station (Messaging._frame)
        self._clock = clock
        self._last_id: str | None = None                        # the id the latest message of ours was given; the next is the one after
        self.waiting: list[Waiting] = []                        # the acks the radio could not take at the moment, oldest first

    def resume(self, records: Iterable[MessageRecord]) -> None:
        """The latest id of ours among the messages held (oldest first) is where the numbering goes on."""
        self._last_id = next((r.msg_id for r in reversed(list(records)) if r.direction == "out" and r.msg_id in MSG_IDS), None)

    def allocate(self, records: Iterable[MessageRecord]) -> str:
        """The next message id: not one that a message still being sent has."""
        ident = next_msg_id(self._last_id, {r.msg_id for r in records if r.state == "sending" and r.msg_id is not None})
        if ident is None:
            raise MessagingError(f"{len(MSG_IDS)} messages are being sent at once: no message id is free")
        self._last_id = ident
        return ident

    def send(self, to: str, msg_id: str, reply_ack: str | None = None) -> None:
        """Acknowledges message `msg_id` of the station `to`: now, or when a radio that is connected but held takes frames again."""
        if self._interlock.refused("ack"):
            return
        if self._tnc.state is Source.State.CONNECTED and not self._tnc.usable:
            if not any(ack.to == to and ack.msg_id == msg_id for ack in self.waiting):           # (a copy of the message that comes while its ack waits gets that one ack)
                self.waiting.append(Waiting(to, msg_id, reply_ack, self._clock() + timedelta(seconds=ACK_HOLD_MAX_SEC)))
                log.info("the ack of message %s from %s waits: %s", msg_id, to, self._tnc.why_unusable())
            return
        self._transmit(to, msg_id, reply_ack)

    def flush(self) -> None:
        """Sends the acks that waited for the radio, now that it takes frames; one that has waited longer than ACK_HOLD_MAX_SEC is dropped."""
        if not self.waiting or not self._tnc.usable:
            return
        now = self._clock()
        waiting, self.waiting = self.waiting, []
        for index, ack in enumerate(waiting):
            if now > ack.until:
                log.info("the ack of message %s from %s waited over %d s for the radio and is dropped: the sender sends again", ack.msg_id, ack.to, ACK_HOLD_MAX_SEC)
            elif not self._transmit(ack.to, ack.msg_id, ack.reply_ack, quiet=True):
                self.waiting.extend(waiting[index:])            # (the radio was taken by the ack before this one: the rest wait for the next tick)
                return

    def _transmit(self, to: str, msg_id: str, reply_ack: str | None, quiet: bool = False) -> bool:
        """Sends the ack; False when the TNC would not take it (said in the log unless `quiet`: an ack that waits is told once, when it starts waiting). An ack that cannot be made is told and counts as done."""
        try:
            sent = self._tnc.send_frame(self._frame(b":" + format_ack(to, msg_id, reply_ack), to))
        except (MessageError, MessagingError) as e:
            log.warning("no ack for message %s from %s: %s", msg_id, to, e)
            return True
        if not sent and not quiet:
            log.warning("the ack of message %s from %s was not sent: the TNC would not take it", msg_id, to)
        return sent
