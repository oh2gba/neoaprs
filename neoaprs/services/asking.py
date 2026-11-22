"""Asking: the directed queries we send to other stations (APRS 1.0.1 chapter 15).

A query is a message sent once without an id; the same one to the same station is refused
(`query.too_soon`) within QUERY_EVERY_SEC.
"""

from datetime import datetime
from typing import Protocol

from neoaprs.callsign import CallsignError, normal_name
from neoaprs.clock import Clock
from neoaprs.aprsmessage import MessageError
from neoaprs.message import QUERIES, QUERY_EVERY_SEC, MessageRecord, MessagingError, query_text


class Sender(Protocol):
    """What asking needs of messaging."""

    async def send(self, to_call: str, text: str, once: bool = False) -> MessageRecord: ...


class Asking:
    def __init__(self, messages: Sender, clock: Clock) -> None:
        self._messages = messages
        self._clock = clock
        self._asked: dict[tuple[str, str], datetime] = {}

    async def ask(self, to_call: str, kind: str, custom: str | None = None) -> MessageRecord:
        """Send the query `kind` (a key of `QUERIES`, or `custom`); may raise MessagingError."""
        try:
            text = query_text(custom or "") if kind == "custom" else QUERIES[kind]
            to = normal_name(to_call)
        except (CallsignError, MessageError) as e:
            raise MessagingError.of(e) from None
        now = self._clock()
        last = self._asked.get((to, text))
        if last is not None and (wait := QUERY_EVERY_SEC - (now - last).total_seconds()) > 0:
            seconds = max(1, round(wait))
            raise MessagingError(
                f"{to} was asked the same a moment ago: wait {seconds} s", "query.too_soon", call=to, seconds=seconds
            )
        self._asked[(to, text)] = now  # before the await
        try:
            return await self._messages.send(to, text, once=True)
        except BaseException:
            self._asked.pop((to, text), None)
            raise
