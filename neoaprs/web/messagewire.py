"""The messages on the wire: the topic `messages` (a table of rows by id) the commands to send one, send a directed query, send one again and stop sending one, and the test of the alert that tells of one; and
encrypted messages (neoaprs/cipher.py): the topic `station_keys` (the key each station announced, by call), the commands that send our key to a station, forget a station's key and make a new key of ours. Models like
the rest of the protocol, listed in `neoaprs/web/protocol.py`."""
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from neoaprs.message import query_text

from .wirebase import Call, Iso, MessageText, _Command, _Message, _Model


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
    radio: Literal["", "fm", "hf"] = Field(description="the radio the attempt went out on: `fm` the FM radio, `hf` the HF modem (direct, no path); empty for an attempt kept before there were two radios")


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
    radio: Literal["", "fm", "hf"] = Field(description="the radio a message that came in came on: `fm` the FM radio, `hf` the HF modem; empty for a message of ours (its attempts say) and for one kept before there were two radios")
    state: Literal["queued", "sending", "acked", "rejected", "failed", "unconfirmed", "cancelled", "received", "overheard"] = Field(
        description="`queued`: it waits, with no attempt made, for another message of ours to the same station to be acked, rejected, failed or cancelled (one message to a station is on the air at a time; one not expected to be acked, given 1 or 2 attempts, never waits); it can be cancelled, and becomes `sending` when its turn comes; `sending`: attempts are being made; `acked`: the addressee acknowledged it; `rejected`: the addressee refused it; `failed`: no answer after the last attempt, or the reason in `failure`; `unconfirmed`: no answer after the last attempt of a message that was given 1 or 2 attempts (the station is not expected to ack; a late ack still settles it); `cancelled`: stopped by the page; "
                    "`received`: it was sent to us; `overheard`: it was sent to another station and we heard it (`from_call` sent it, `to_call` is who it is for)")
    failure: Literal["too_long_for_radio"] | None = Field(description="why a `failed` message failed when it is not that no answer came: `too_long_for_radio`, its frame does not fit the radio it goes out on (it may have been sent before the radio changed; sent again, it is refused with `message.too_long_for_radio` while it does not fit); null for every other message, and for a failed one that had no answer")
    attempts: int = Field(ge=0, description="how many times it has been transmitted (at most `attempts_max`: 0, 32, 64, 128, 256, 512, 1024 ... seconds after the first, no wait longer than 960)")
    attempts_max: int = Field(ge=1, le=10, description="how many attempts the message was given when it was sent: 4, 2 for the email gateway `EMAIL-2`, 1 for a bulletin (messages from before the count was fixed have their own, up to 10)")
    last_attempt_at: Iso | None = Field(description="when it was transmitted last; null until the first attempt (the TNC may be away)")
    acked_at: Iso | None = Field(description="when the acknowledgement was heard")
    attempts_detail: list[AttemptRow] = Field(description="for a message of ours, each attempt made (`attempts` of them, the oldest first; fewer for a message sent before the delivery chain was kept, none until the first attempt) with the hops of its path that a copy of our own message was heard back with; a hop heard is a `set` of the message's row. Empty for a message that came in")
    route: str = Field(description="how a message that was heard reached us (from the path of the first copy heard): `direct`, `via OH2RCH-2`, `via OH2RCH-1 → OH2RCH-3`, `via OH7JHF-1 (internet)` for a third-party packet an iGate put on the air; empty for one of ours and for one heard before this was kept")
    seal: Literal["", "key", "key_other", "open", "shut"] = Field(description="what the message is besides text (encrypted messages, a daemon started with `--encryption`): empty for a plain message; `key` an announcement of the sender's public key (`send_key`; for one that came in, the key was taken, or is the one kept already); "
                                                                           "`key_other` an announcement that differs from the key kept for the station, not taken (`forget_station_key` first); `open` an encrypted message that was read, `text` is what it says (for one of ours, what was written); `shut` an encrypted message that cannot be read here (no key from the sender, no key of ours, or not for us), `text` is the ciphertext as it came")


class SendMessage(_Command):
    """Sends a message to a station: the addressee is a call with an optional SSID, the text at most 67 bytes of UTF-8 without `|`, `~`, `{` or a control character. The message is kept and transmitted at
    once with the next message id; it arrives as a new row of the topic `messages` (state `sending`) and as the `out` packet, and its row changes when the acknowledgement comes or the attempts run out. It is transmitted at most 4 times, 2 for `EMAIL-2`.
    When the TNC is not connected the message is kept and its first attempt waits for the radio. Answered with an `error` that names the reason when the addressee or the text is refused."""
    cmd: Literal["send_message"]
    to: Call
    text: MessageText
    locked: bool = Field(default=False, description="true encrypts the message with the key shared with the station (its `seal` is `open`): the text may be UTF-8, at most 34 bytes. Refused while the daemon was started without `--encryption` (`lock.off`), while the station has not announced its key (`lock.no_key`), and when the text is over 34 bytes (`lock.too_long`)")


class SetMessageRadio(_Command):
    """Chooses the radio messages to a station go out on while both radios are on: `fm`, `hf`, or empty to leave it to the daemon again (the FM radio unless the station was heard on HF alone). It holds
    from the next attempt on, also of a message on its way, and across a restart; the station's row says it (`message_radio`). Answered by the station's row, or by an `error` for a station that is not
    known (`station.unknown`)."""
    cmd: Literal["message_radio"]
    call: Call
    radio: Literal["", "fm", "hf"]


class SendKey(_Command):
    """Sends our public key to a station as an ordinary message (`seal` `key`), so that it can encrypt to us; our key pair is made the first time it is needed. Nothing is ever announced by itself: a station that is to read our
    locked messages gets our key this way, by hand, and we read its when it has sent its key the same way. Refused while the daemon was started without `--encryption` (`lock.off`). Answered as `send_message` is."""
    cmd: Literal["send_key"]
    to: Call


class ForgetStationKey(_Command):
    """Takes a station's key away (the topic `station_keys`): the first key a station announces is kept, and a later announcement of a different key is not taken until the old one is forgotten. Answered by the `del` of the
    station's entry, or by an `error` (`lock.no_key` when there is none)."""
    cmd: Literal["forget_station_key"]
    call: Call


class NewMessageKey(_Command):
    """Makes a new key pair of ours in place of the old: the stations that have the old key must be sent the new one (`send_key`) before they can read us again. The fingerprint of the new key comes with the next
    `status`. Answered by that `status`, or by an `error` when the key could not be kept."""
    cmd: Literal["message_key_new"]


class StationKey(_Model):
    """The public key a station announced, kept on first hearing. The entries are the values of the topic `station_keys`, keyed by call; a station that has not announced a key has no entry. A key heard from a station is a
    `set`, `forget_station_key` a `del`."""
    fingerprint: str = Field(description="16 hex characters in four groups (`A1B2 C3D4 E5F6 0718`), the start of SHA-256 of the key, for the two operators to compare on voice")
    heard_at: Iso = Field(description="when the key was heard")


class QueryStation(_Command):
    """Asks a station a directed query (APRS 1.0.1 chapter 15): a message to it with the text of the query, `?APRSP` (`kind` `position`: its position packet), `?APRSS` (`status`: its status report), `?APRSD` (`heard`: the stations it
    hears direct, as a message), `?APRST` (`trace`: the path our query reached it by, as a message), `?WX?` (`weather`: its weather report; a general query in the specification, which many stations do not answer
    when it is addressed to them) or the operator's own (`custom`, with `text`: `?APRSH OH2GBA-15`, `?PING?`). The query is sent once, without a message id: no attempts follow and no ack is expected. It is kept as a row of the topic
    `messages` to the station, in state `sending` until it has been transmitted and then `unconfirmed`, whose `text` is the query; the page shows such a row (an `out` message with no `msg_id` whose text begins with `?`) as a note of what was asked. The answer is whatever the
    station sends: a packet (the station's card changes) or a message (a row `in`). Not more than one query of the same text to a station in 60 seconds. Answered with an `error` when the station is not in the station book
    (`station.unknown`), is no station that takes messages (`query.not_capable`: an object, an item, ourselves, a station whose position says it takes none and that never sent a message), the same query was sent less than 60 seconds ago
    (`query.too_soon`) or the message is refused as `send_message` refuses it (the call is not set, the radio is silent); a `custom` text that is no query is refused as invalid."""
    cmd: Literal["query"]
    call: Call
    kind: Literal["position", "status", "heard", "trace", "weather", "custom"]
    text: MessageText | None = Field(default=None, description="the query of `custom`, as the operator wrote it: after the spaces at its ends are taken off it begins with `?` and has something after it, is printable "
                                                                       "ASCII without `|`, `~` or `{` and at most 67 characters, the text of a message; it is sent upper-cased. Absent or null for the other kinds")

    @field_validator("text")
    @classmethod
    def _a_query(cls, text: str | None) -> str | None:
        return None if text is None else query_text(text)

    @model_validator(mode="after")
    def _text_with_custom(self) -> Self:
        if (self.kind == "custom") != (self.text is not None):
            raise ValueError("`text` is given with the kind `custom` and with no other")
        return self


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
    call: Call


class OverheardDelete(_Command):
    """Removes every message we only overheard `from_call` sending to `to_call` (the state `overheard`, that sender, that addressee: one pair of the Messages list's overheard rows) from the database in one write,
    from the daemon and from every page: each message's row is a `del` of the topic `messages`. The conversations are not touched: a message we sent or one sent to us is never removed by this. Answered by the
    `del`s, or by an `error` (no overheard message of that pair)."""
    cmd: Literal["overheard_delete"]
    from_call: Call
    to_call: Call


class AlertTest(_Command):
    """Runs the alert command as it is saved in the settings (`messages/alert_command`), exactly as for a message to us (the same shell, the same environment, the 20 s limit) with a made-up message: `NEOAPRS_FROM`
    is `NEOAPRS`, `NEOAPRS_TEXT` is `This is a test of the NeoAPRS alert`, `NEOAPRS_AT` is now and `NEOAPRS_MSG_ID` is empty. `messages/alert` is not asked: a test is explicit. Waits for the command and answers the page
    that asked with `alert_result`, or with an `error` when the command is empty (`no alert command`). A page of another device is refused with `setting.local_only`."""
    cmd: Literal["alert_test"]


class AlertResultMsg(_Message):
    """The answer to `alert_test`, when the command has ended or run out of its 20 s."""
    type: Literal["alert_result"]
    ok: bool = Field(description="the command ended with exit code 0")
    text: str = Field(description="`ran` when it worked; else why not: the exit code and the first line of stderr (`exit code 3: no display`), or that it could not start or was killed after 20 s")
