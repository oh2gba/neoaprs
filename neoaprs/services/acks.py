"""The ids and acks of messaging: the message id a message of ours is given (the next after the latest, never one that a message still being sent has) and the ack we send for a message to us, `ackMM`, or the
number as it came for a message with a reply-ack number (`ackMM}` for `{MM}`, `ackMM}AA` for `{MM}AA`). An ack is not kept for later when the interlock is shut: the sender sends again."""
import logging
from collections.abc import Callable, Iterable

from neoaprs import ax25
from neoaprs.aprsmessage import MessageError, format_ack
from neoaprs.interlock import Interlock
from neoaprs.message import MSG_IDS, MessageRecord, MessagingError, next_msg_id
from neoaprs.services.common import Radio

log = logging.getLogger("neoaprs.messaging")


class Acks:
    def __init__(self, tnc: Radio, interlock: Interlock, frame: Callable[[bytes, str], ax25.Frame]) -> None:
        self._tnc = tnc
        self._interlock = interlock
        self._frame = frame                                     # our frame for an information field to a station (Messaging._frame)
        self._last_id: str | None = None                        # the id the latest message of ours was given; the next is the one after

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
        """Acknowledges message `msg_id` of the station `to`."""
        if self._interlock.refused("ack"):
            return
        try:
            if not self._tnc.send_frame(self._frame(b":" + format_ack(to, msg_id, reply_ack), to)):
                log.warning("the ack of message %s from %s was not sent: the TNC would not take it", msg_id, to)
        except (MessageError, MessagingError) as e:
            log.warning("no ack for message %s from %s: %s", msg_id, to, e)
