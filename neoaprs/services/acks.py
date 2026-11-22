"""Message ids and acks: allocate the next message id and send the ack for a message to us.

An ack goes back on the radio the message came on; it is dropped while the interlock is shut and
waits (`flush`, ACK_HOLD_MAX_SEC) while the radio is briefly unusable.
"""

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from neoaprs import ax25
from neoaprs.aprsmessage import MessageError, format_ack
from neoaprs.clock import Clock, utcnow
from neoaprs.interlock import Interlock
from neoaprs.message import MSG_IDS, MessageRecord, MessagingError, next_msg_id
from neoaprs.radiotype import RadioId
from neoaprs.services.radioset import NO_RADIO, AirRadio, RadioPick, first_sender
from neoaprs.source import Source

log = logging.getLogger("neoaprs.messaging")

# The sender's first retry comes 32 s after its message; waiting longer would ack a copy on its way.
ACK_HOLD_MAX_SEC = 60


@dataclass(frozen=True)
class Waiting:
    to: str
    msg_id: str
    reply_ack: str | None
    until: datetime
    radio: RadioId


class Acks:
    def __init__(
        self,
        radios: Callable[[], RadioPick],
        interlock: Interlock,
        frame: Callable[[bytes, str, AirRadio], ax25.Frame],
        clock: Clock = utcnow,
    ) -> None:
        self._radios = radios
        self._interlock = interlock
        self._frame = frame
        self._clock = clock
        self._last_id: str | None = None
        self.waiting: list[Waiting] = []

    def resume(self, records: Iterable[MessageRecord]) -> None:
        """Continue the numbering after the latest outgoing id in `records` (oldest first)."""
        self._last_id = next(
            (r.msg_id for r in reversed(list(records)) if r.direction == "out" and r.msg_id in MSG_IDS), None
        )

    def allocate(self, records: Iterable[MessageRecord]) -> str:
        """Return the next message id, skipping ids of messages still being sent."""
        ident = next_msg_id(self._last_id, {r.msg_id for r in records if r.state == "sending" and r.msg_id is not None})
        if ident is None:
            raise MessagingError(
                f"{len(MSG_IDS)} messages are being sent at once: no message id is free",
                "message.busy",
                count=len(MSG_IDS),
            )
        self._last_id = ident
        return ident

    def send(self, to: str, msg_id: str, reply_ack: str | None = None, radio: AirRadio | None = None) -> None:
        """Ack message `msg_id` of `to` on `radio` (default: first sender), now or once usable."""
        if self._interlock.refused("ack"):
            return
        radio = radio or first_sender(self._radios())
        if radio is None:
            log.warning("no ack for message %s from %s: %s", msg_id, to, NO_RADIO)
            return
        if radio.state is Source.State.CONNECTED and not radio.usable:
            # A copy of the message arriving while its ack waits gets that one ack.
            if not any(ack.to == to and ack.msg_id == msg_id for ack in self.waiting):
                self.waiting.append(
                    Waiting(to, msg_id, reply_ack, self._clock() + timedelta(seconds=ACK_HOLD_MAX_SEC), radio.id)
                )
                log.info("the ack of message %s from %s waits: %s", msg_id, to, radio.why_unusable())
            return
        self._transmit(to, msg_id, reply_ack, radio)

    def flush(self) -> None:
        """Send waiting acks whose radio is usable again; drop those older than ACK_HOLD_MAX_SEC."""
        if not self.waiting:
            return
        now = self._clock()
        waiting, self.waiting = self.waiting, []
        radios = self._radios()
        for ack in waiting:
            radio = radios.get(ack.radio)
            if now > ack.until:
                log.info(
                    "the ack of message %s from %s waited over %d s for the radio and is dropped: the sender sends again",
                    ack.msg_id,
                    ack.to,
                    ACK_HOLD_MAX_SEC,
                )
            elif (
                radio is None
                or not radio.usable
                or not self._transmit(ack.to, ack.msg_id, ack.reply_ack, radio, quiet=True)
            ):
                self.waiting.append(ack)

    def _transmit(self, to: str, msg_id: str, reply_ack: str | None, radio: AirRadio, quiet: bool = False) -> bool:
        """Send the ack; return False if the TNC refused it. An unbuildable ack counts as done."""
        try:
            sent = radio.send_frame(self._frame(b":" + format_ack(to, msg_id, reply_ack), to, radio))
        except (MessageError, MessagingError) as e:
            log.warning("no ack for message %s from %s: %s", msg_id, to, e)
            return True
        if not sent and not quiet:
            log.warning("the ack of message %s from %s was not sent: the TNC would not take it", msg_id, to)
        return sent
