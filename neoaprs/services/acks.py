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
    radio: Radio                            # the radio the message came on, which the ack goes back on


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

    def send(self, to: str, msg_id: str, reply_ack: str | None = None, radio: Radio | None = None) -> None:
        """Acknowledges message `msg_id` of the station `to` on `radio` (the one the message came on; the one radio there is by default): now, or when that radio, connected but held, takes frames again."""
        if self._interlock.refused("ack"):
            return
        radio = radio or self._tnc
        if radio.state is Source.State.CONNECTED and not radio.usable:
            if not any(ack.to == to and ack.msg_id == msg_id for ack in self.waiting):           # (a copy of the message that comes while its ack waits gets that one ack)
                self.waiting.append(Waiting(to, msg_id, reply_ack, self._clock() + timedelta(seconds=ACK_HOLD_MAX_SEC), radio))
                log.info("the ack of message %s from %s waits: %s", msg_id, to, radio.why_unusable())
            return
        self._transmit(to, msg_id, reply_ack, radio)

    def flush(self) -> None:
        """Sends the acks that waited for their radio, now that it takes frames; one that has waited longer than ACK_HOLD_MAX_SEC is dropped. An ack whose radio is still held waits on."""
        if not self.waiting:
            return
        now = self._clock()
        waiting, self.waiting = self.waiting, []
        for ack in waiting:
            if now > ack.until:
                log.info("the ack of message %s from %s waited over %d s for the radio and is dropped: the sender sends again", ack.msg_id, ack.to, ACK_HOLD_MAX_SEC)
            elif not ack.radio.usable or not self._transmit(ack.to, ack.msg_id, ack.reply_ack, ack.radio, quiet=True):
                self.waiting.append(ack)                        # (the radio is held, or was taken by the ack before this one: it waits for the next tick)

    def _transmit(self, to: str, msg_id: str, reply_ack: str | None, radio: Radio, quiet: bool = False) -> bool:
        """Sends the ack on the radio; False when the TNC would not take it (said in the log unless `quiet`: an ack that waits is told once, when it starts waiting). An ack that cannot be made is told and counts as done."""
        try:
            sent = radio.send_frame(self._frame(b":" + format_ack(to, msg_id, reply_ack), to))
        except (MessageError, MessagingError) as e:
            log.warning("no ack for message %s from %s: %s", msg_id, to, e)
            return True
        if not sent and not quiet:
            log.warning("the ack of message %s from %s was not sent: the TNC would not take it", msg_id, to)
        return sent
