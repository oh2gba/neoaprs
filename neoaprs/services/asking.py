"""Asking: the directed queries we send to other stations (APRS 1.0.1 chapter 15), `?APRSP` (position), `?APRSS` (status), `?APRSD` (the stations it hears direct) and `?APRST` (the route), `?WX?` to a weather station (a
general query in the specification, asked of one station all the same) and a query the operator writes (`custom`: `?APRSH OH2GBA-15`, `?PING?`; message.py `query_text` says what one may be), which the page sends from the
station panel of the Stations tab (the command `query`).

A query is a message to the station with the query as its text, through the normal way a message goes (messaging.py: the interlock, the radio's state, the pacing, the station's path), but sent once and without a message
id: the specification's queries are not numbered, nobody acks one (the answer is a packet, or a message of the station's own) and a station that does not answer is not asked again by the daemon. It is kept as a message
of the conversation with the station, "unconfirmed" after its attempt, an `out` message with no id whose text begins with `?`, which is how the page tells it from a bubble and shows "You asked for its status".

One query of the same text to a station in QUERY_EVERY_SEC seconds: the same again sooner is refused (`query.too_soon`, with the seconds that are left), so that a station is not asked again and again. A query that is refused for
any other reason (the call is not set, the radio is silent, the call is none) does not count."""
from datetime import datetime
from typing import Protocol

from neoaprs.callsign import CallsignError, normal_name
from neoaprs.clock import Clock
from neoaprs.aprsmessage import MessageError
from neoaprs.message import QUERIES, QUERY_EVERY_SEC, MessageRecord, MessagingError, query_text


class Sender(Protocol):
    """What asking needs of messaging: a message sent once, with no id."""
    async def send(self, to_call: str, text: str, once: bool = False) -> MessageRecord: ...


class Asking:
    def __init__(self, messages: Sender, clock: Clock) -> None:
        self._messages = messages
        self._clock = clock
        self._asked: dict[tuple[str, str], datetime] = {}       # when each query (station, text) was last sent

    async def ask(self, to_call: str, kind: str, custom: str | None = None) -> MessageRecord:
        """Sends the query of this kind (a key of `QUERIES`, or `custom` with its text, `query_text`) to the station; the message as `send` gives it back. Raises MessagingError as `send` does, for a custom text
        that is no query, and `query.too_soon` for the same query within QUERY_EVERY_SEC."""
        try:
            text = query_text(custom or "") if kind == "custom" else QUERIES[kind]
            to = normal_name(to_call)
        except (CallsignError, MessageError) as e:
            raise MessagingError(str(e)) from None
        now = self._clock()
        last = self._asked.get((to, text))
        if last is not None and (wait := QUERY_EVERY_SEC - (now - last).total_seconds()) > 0:
            seconds = max(1, round(wait))
            raise MessagingError(f"{to} was asked the same a moment ago: wait {seconds} s", "query.too_soon", call=to, seconds=seconds)
        self._asked[(to, text)] = now                                       # (taken before the first await: two asks together are one)
        try:
            return await self._messages.send(to, text, once=True)
        except BaseException:
            self._asked.pop((to, text), None)
            raise
