"""The way of our messages to the internet services (message.INTERNET_SERVICES) over the Internet connection.

Open while the connection carries them (Igate.carries_messages: Send what I hear on, the login verified); messaging
then puts an attempt or an ack there instead of on a radio."""

import logging
from dataclasses import replace
from typing import Protocol

from neoaprs.aprsmessage import MessageError, format_ack
from neoaprs.clock import Clock
from neoaprs.interlock import Interlock
from neoaprs.message import MessageRecord, is_internet_service
from neoaprs.services.delivery import Delivery
from neoaprs.services.heard import Heard
from neoaprs.services.messageradio import info

log = logging.getLogger("neoaprs.messaging")


class InternetWay(Protocol):
    """The Internet connection as a way for our messages to the internet services (Igate)."""

    def carries_messages(self) -> bool: ...
    def send_ours(self, info: bytes) -> bool: ...


class ServiceRoute:
    def __init__(self, way: InternetWay | None, interlock: Interlock, clock: Clock) -> None:
        self._way = way
        self._interlock = interlock
        self._clock = clock

    def open(self) -> bool:
        """Whether the Internet connection carries messages to the internet services now."""
        return self._way is not None and self._way.carries_messages()

    def takes(self, to: str) -> bool:
        """Whether a message to `to` goes over the Internet connection now, not on a radio."""
        return is_internet_service(to) and self.open()

    def attempt(self, record: MessageRecord, heard: Heard, delivery: Delivery) -> MessageRecord | None:
        """Put the message on APRS-IS once and keep the attempt; return the message after it, or None if the link
        did not take it."""
        reply = None if record.msg_id is None else heard.reply_for(record.to_call, self._clock()) or ""
        text = record.text if record.wire is None else record.wire
        if self._way is None or not self._way.send_ours(info(record.to_call, text, record.msg_id, reply)):
            return None
        at = self._clock()
        record = replace(record, attempts=record.attempts + 1, last_attempt_at=at)
        delivery.sent(record, (), at, internet=True)
        log.info(
            "message %d to %s sent over the Internet connection (attempt %d of %d): %s",
            record.id,
            record.to_call,
            record.attempts,
            record.attempts_max,
            text,
        )
        return record if record.msg_id is not None else replace(record, state="unconfirmed")

    def ack(self, to: str, msg_id: str, reply_ack: str | None) -> None:
        """Ack a service's message over the Internet connection."""
        if self._interlock.refused("ack"):
            return
        try:
            field = b":" + format_ack(to, msg_id, reply_ack)
        except MessageError as e:
            log.warning("no ack for message %s from %s: %s", msg_id, to, e)
            return
        if self._way is None or not self._way.send_ours(field):
            log.warning(
                "the ack of message %s from %s was not sent: the Internet connection would not take it", msg_id, to
            )
