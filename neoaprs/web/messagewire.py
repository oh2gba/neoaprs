"""The messages on the wire: the topic `messages` (a table of rows by id) the commands to send one, send a directed query, send one again and stop sending one, and the test of the alert that tells of one. Models like the rest of the protocol, listed in `neoaprs/web/protocol.py`."""
from typing import Literal

from pydantic import Field

from .wirebase import Iso, _Command, _Message, _Model


class HopRow(_Model):
    """One digipeater of the path an attempt went by, and whether a copy of our own message was heard back with that hop used."""
    call: str = Field(description="the digipeater as the path named it (`OH2RCH-2`, or an alias such as `WIDE1-1`); once heard, the call that did it, which replaces an alias")
    heard: bool = Field(description="a copy was heard by radio with this hop's has-been-repeated bit set (or a later hop's: a hop works the first unused address)")
    heard_at: Iso | None = Field(description="when the first copy that showed the hop was heard (by radio if there was one, else over the internet); null when it was not heard")
    by_internet: bool = Field(description="a copy gated back by an iGate as a third-party packet showed the hop used; with `heard` false the hop is known only that way")


class AttemptRow(_Model):
    """One transmission of a message of ours and what came back of it."""
    sent_at: Iso
    hops: list[HopRow] = Field(description="the digipeaters of the path the attempt went by, in order; empty for a direct path")
    internet: str | None = Field(description="the call of the iGate that put a copy of the message back on the air as a third-party packet, when one was heard for this attempt; null otherwise")
    acked: bool = Field(description="the acknowledgement was heard after this attempt and before the next one: the attempt the ack answers")


class MessageRow(_Model):
    """One message: one we sent or one that was sent to us. The rows are the values of the topic `messages`, keyed by `id` as text: the daemon holds every message (none leaves on its
    own; a database with more than 10000 gives the latest 10000 at a start). A message that is new or changes (its state, its attempts) is a `set` of its row, one that is deleted (`message_delete`, `conversation_delete`) a `del`. The conversation a message belongs to is the other station: `from_call`
    of a message that came in, `to_call` of one we sent."""
    id: int = Field(ge=1, description="the number the database gave the message; it counts up and is kept across runs of the daemon")
    at: Iso = Field(description="when the message was made (sent messages) or heard (received messages)")
    direction: Literal["in", "out"] = Field(description="`in` was heard (sent to us, or overheard), `out` is one of ours")
    from_call: str = Field(description="the sender: the packet's source for a message that came in, our call for one of ours")
    to_call: str = Field(description="the addressee: our call for a message sent to us, the other station for one of ours, whoever it is for when overheard")
    text: str
    msg_id: str | None = Field(description="the message id the acknowledgement quotes (1 to 5 letters or digits); null for a message that came in without one")
    state: Literal["sending", "acked", "rejected", "failed", "unconfirmed", "cancelled", "received", "overheard"] = Field(
        description="`sending`: attempts are being made; `acked`: the addressee acknowledged it; `rejected`: the addressee refused it; `failed`: no answer after the last attempt; `unconfirmed`: no answer after the last attempt of a message that was given 1 or 2 attempts (the station is not expected to ack; a late ack still settles it); `cancelled`: stopped by the page; "
                    "`received`: it was sent to us; `overheard`: it was sent to another station and we heard it (`from_call` sent it, `to_call` is who it is for)")
    attempts: int = Field(ge=0, description="how many times it has been transmitted (at most `attempts_max`: 0, 32, 64, 128, 256, 512, 1024 ... seconds after the first, no wait longer than 960)")
    attempts_max: int = Field(ge=1, le=10, description="how many attempts the message was given when it was sent: 4, 2 for the email gateway `EMAIL-2`, 1 for a bulletin (messages from before the count was fixed have their own, up to 10)")
    last_attempt_at: Iso | None = Field(description="when it was transmitted last; null until the first attempt (the TNC may be away)")
    acked_at: Iso | None = Field(description="when the acknowledgement was heard")
    attempts_detail: list[AttemptRow] = Field(description="for a message of ours, each attempt made (`attempts` of them, the oldest first; fewer for a message sent before the delivery chain was kept, none until the first attempt) with the hops of its path that a copy of our own message was heard back with; a hop heard is a `set` of the message's row. Empty for a message that came in")
    route: str = Field(description="how a message that was heard reached us (from the path of the first copy heard): `direct`, `via OH2RCH-2`, `via OH2RCH-1 → OH2RCH-3`, `via OH7JHF-1 (internet)` for a third-party packet an iGate put on the air; empty for one of ours and for one heard before this was kept")


class SendMessage(_Command):
    """Sends a message to a station: the addressee is a call with an optional SSID, the text at most 67 bytes of UTF-8 without `|`, `~`, `{` or a control character. The message is kept and transmitted at
    once with the next message id; it arrives as a new row of the topic `messages` (state `sending`) and as the `out` packet, and its row changes when the acknowledgement comes or the attempts run out. It is transmitted at most 4 times, 2 for `EMAIL-2`.
    When the TNC is not connected the message is kept and its first attempt waits for the radio. Answered with an `error` that names the reason when the addressee or the text is refused."""
    cmd: Literal["send_message"]
    to: str = Field(min_length=1, max_length=64)
    text: str = Field(max_length=512)


class QueryStation(_Command):
    """Asks a station a directed query (APRS 1.0.1 chapter 15): a message to it with the text of the query, `?APRSP` (`kind` `position`: its position packet), `?APRSS` (`status`: its status report), `?APRSD` (`heard`: the stations it
    hears direct, as a message) or `?APRST` (`trace`: the path our query reached it by, as a message). The query is sent once, without a message id: no attempts follow and no ack is expected. It is kept as a row of the topic
    `messages` to the station, in state `sending` until it has been transmitted and then `unconfirmed`, whose `text` is the query; the page shows such a row (an `out` message with no `msg_id` whose text is one of the four) as a note of what was asked. The answer is whatever the
    station sends: a packet (the station's card changes) or a message (a row `in`). Not more than one query of a kind to a station in 60 seconds. Answered with an `error` when the station is not in the station book
    (`station.unknown`), is no station that takes messages (`query.not_capable`: an object, an item, ourselves, a station whose position says it takes none and that never sent a message), the same query was sent less than 60 seconds ago
    (`query.too_soon`) or the message is refused as `send_message` refuses it (the call is not set, the radio is silent)."""
    cmd: Literal["query"]
    call: str = Field(min_length=1, max_length=64)
    kind: Literal["position", "status", "heard", "trace"]


class MessageRetry(_Command):
    """Sends a message of ours that failed, is unconfirmed, was rejected or was cancelled again, from the first attempt of the schedule. Answered by the new state of its row, or by an `error` (no such message, or it is
    not in a state that can be sent again)."""
    cmd: Literal["message_retry"]
    id: int = Field(ge=1)


class MessageCancel(_Command):
    """Stops sending a message of ours that is still being sent; its row becomes `cancelled`. Answered by the new state of its row, or by an `error`."""
    cmd: Literal["message_cancel"]
    id: int = Field(ge=1)


class MessageDelete(_Command):
    """Removes a message of any kind (one of ours, one sent to us, one we only overheard) from the database, from the daemon and from every page: its row is a `del` of the topic `messages`. A message that is
    still being sent is cancelled first, so that no attempt is made while it goes. Answered by the `del`, or by an `error` (no such message)."""
    cmd: Literal["message_delete"]
    id: int = Field(ge=1)


class ConversationDelete(_Command):
    """Removes the whole conversation with a station: every message we sent to it and every one it sent to us (not the messages it was only overheard sending to others), from the database in one write, from
    the daemon and from every page: each message's row is a `del` of the topic `messages`. A message that is still being sent is cancelled first. The path and the timeout of the station stay. Answered by the
    `del`s, or by an `error` (the call is none, or there is no message with that station)."""
    cmd: Literal["conversation_delete"]
    call: str = Field(min_length=1, max_length=64)


class OverheardDelete(_Command):
    """Removes every message we only overheard `from_call` sending to `to_call` (the state `overheard`, that sender, that addressee: one pair of the Messages list's overheard rows) from the database in one write,
    from the daemon and from every page: each message's row is a `del` of the topic `messages`. The conversations are not touched: a message we sent or one sent to us is never removed by this. Answered by the
    `del`s, or by an `error` (no overheard message of that pair)."""
    cmd: Literal["overheard_delete"]
    from_call: str = Field(min_length=1, max_length=64)
    to_call: str = Field(min_length=1, max_length=64)


class AlertTest(_Command):
    """Runs the alert command as it is saved in the settings (`messages/alert_command`), exactly as for a message to us (the same shell, the same environment, the 20 s limit) with a made-up message: `NEOAPRS_FROM`
    is `NEOAPRS`, `NEOAPRS_TEXT` is `This is a test of the NeoAPRS alert`, `NEOAPRS_AT` is now and `NEOAPRS_MSG_ID` is empty. `messages/alert` is not asked: a test is explicit. Waits for the command and answers the page
    that asked with `alert_result`, or with an `error` when the command is empty (`no alert command`)."""
    cmd: Literal["alert_test"]


class AlertResultMsg(_Message):
    """The answer to `alert_test`, when the command has ended or run out of its 20 s."""
    type: Literal["alert_result"]
    ok: bool = Field(description="the command ended with exit code 0")
    text: str = Field(description="`ran` when it worked; else why not: the exit code and the first line of stderr (`exit code 3: no display`), or that it could not start or was killed after 20 s")
