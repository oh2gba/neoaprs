"""A message of the messaging service as a value, and the rules that need no I/O: who a message is addressed to, what text may be sent, and when the next attempt of a message that is being sent is due.

A message is a row of the message table (`MessageRecord`): one we sent (direction "out") or one that was sent to us (direction "in", state "received"). `id` is the number the database gave it; `msg_id` is
the APRS message id, the 1 to 5 characters after the "{" that the acknowledgement quotes (the ones we give are two, `MSG_IDS`). Every datetime is timezone-aware UTC."""
import re
import string
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, get_args

from neoaprs.aprsmessage import FORBIDDEN, MAX_TEXT, MessageError
from neoaprs.ax25 import MAX_PATH
from neoaprs.coded import CodedError
from neoaprs.callsign import format_call, parse_call

State = Literal["sending", "acked", "rejected", "failed", "unconfirmed", "cancelled", "received", "overheard"]
STATES: tuple[str, ...] = get_args(State)

STATION_ATTEMPTS = 4                            # how many times a message to a station is transmitted before it has failed; fixed, the operator does not choose it
EMAIL_ATTEMPTS = 2                              # the email gateway's acks rarely reach us (they come back through an iGate), so a mail is sent twice and then left `unconfirmed`
UNCONFIRMED_MAX = 2                             # a message given this many attempts or fewer is not failed when they are used up with no ack: it is `unconfirmed` (the station is not expected to ack)
FIRST_WAIT_SEC = 30                             # the wait after the first attempt; each wait after that is double the one before, up to MAX_WAIT_SEC
MAX_WAIT_SEC = 960
FINAL_WAIT_SEC = 240                            # how long the answer to the last attempt is waited for before the message has failed
MESSAGES_HELD_MAX = 10000                       # the daemon holds every message; if the database has more, a start takes the latest of these (and every one still being sent) and says so in the log


_ALNUM = string.digits + string.ascii_uppercase
MSG_IDS: tuple[str, ...] = (*(f"{n:02d}" for n in range(1, 100)), *(a + b for a in string.ascii_uppercase for b in _ALNUM), *(d + c for d in string.digits for c in string.ascii_uppercase), "00")
_ID_INDEX = {ident: n for n, ident in enumerate(MSG_IDS)}       # the ids we give: 01..99, A0..ZZ, 0A..9Z and 00, every two-character id once (1296), in the order they are used
_QUERY = re.compile(r"\?(APRS[DHMOPST]?|IGATE|WX|PING)(\?.*|\s.*)?$", re.IGNORECASE)
TELEMETRY_DEFINITIONS = ("PARM.", "UNIT.", "EQNS.", "BITS.")


EMAIL_GATEWAY = "EMAIL-2"                  # the APRS email gateway: a station on the internet, which no message can reach by RF only


class MessagingError(CodedError):
    """The message cannot be sent, or the command cannot be done; the text says why."""


@dataclass(frozen=True, slots=True)
class MessageRecord:
    id: int
    at: datetime
    direction: Literal["in", "out"]
    from_call: str
    to_call: str
    text: str
    msg_id: str | None
    state: State
    attempts: int = 0
    last_attempt_at: datetime | None = None
    acked_at: datetime | None = None
    attempts_max: int = STATION_ATTEMPTS                  # how many attempts the message was given when it was sent (`attempts_for`); an older message keeps the count it was given then
    route: str = ""                                       # how the packet reached us, "direct" or "via OH2RCH-2" (neoaprs/route.py), for a message that was heard; empty for one of ours

    @property
    def peer(self) -> str:
        """The other station of the conversation this message belongs to (for one we only overheard, the sender)."""
        return self.from_call if self.direction == "in" else self.to_call


def normal_call(text: str) -> str:
    """The call as it is written in a message: upper case, no SSID of 0. Raises CallsignError."""
    return format_call(*parse_call(text.strip()))


def normal_path(text: str) -> tuple[str, ...]:
    """A path as it is written, digipeater calls separated by commas, as the calls the frame carries (capitals, no blanks, no SSID of 0); empty for no digipeaters at all. Raises ValueError that says
    what is wrong: a call that is none, more than 8 of them. The rules of the setting beacon/path."""
    calls = tuple(normal_call(piece) for piece in text.split(",") if piece.strip())
    if len(calls) > MAX_PATH:
        raise CodedError(f"{len(calls)} digipeaters is more than the {MAX_PATH} a path may have", "path.too_long", count=len(calls), max=MAX_PATH)
    return calls


def same_call(a: str, b: str) -> bool:
    """Are the two the same call with the same SSID (no SSID and -0 are the same)?"""
    try:
        return parse_call(a) == parse_call(b)
    except ValueError:
        return False


def addressed_to(addressee: str, ours: str) -> bool:
    """Is a message for `addressee` for the station `ours`? The call with its SSID, exactly (no SSID and -0 are the same; our base call is not ours when ours has an SSID)."""
    return same_call(addressee, ours)


def is_query(text: str) -> bool:
    """Is the text of a message one of the queries of the specification (`?APRSP`, `?APRSS`, `?APRSD`, `?APRST`, `?APRSM`, `?APRSH`, `?APRSO`, `?PING?`, `?APRS?`, `?IGATE?`, `?WX?`, with what follows
    them)? A query has no id and is not acknowledged."""
    return _QUERY.match(text.strip()) is not None


def is_telemetry_definition(text: str) -> bool:
    """Is the text a definition of the telemetry channels (`PARM.`, `UNIT.`, `EQNS.` or `BITS.` and the values)? Those are for the telemetry software, not a conversation."""
    return text.startswith(TELEMETRY_DEFINITIONS)


def next_msg_id(last: str | None, busy: set[str]) -> str | None:
    """The id after `last` (the first when `last` is none of ours) that is not in `busy`, going round after 00; None when all 1296 are busy."""
    start = _ID_INDEX[last] + 1 if last in _ID_INDEX else 0
    for step in range(len(MSG_IDS)):
        ident = MSG_IDS[(start + step) % len(MSG_IDS)]
        if ident not in busy:
            return ident
    return None


def check_text(text: str) -> None:
    """Raises MessageError that says what is wrong with the text of a message: empty, over `MAX_TEXT` characters, a character the format has no place for, a control character, a character that is not
    printable ASCII (the specification's text is ASCII, and radios show anything else wrongly)."""
    if not text.strip():
        raise MessageError("the message is empty", "message.empty")
    if len(text) > MAX_TEXT:
        raise MessageError(f"the text is {len(text)} characters, at most {MAX_TEXT} fit in a message", "message.too_long", length=len(text), max=MAX_TEXT)
    bad = [c for c in FORBIDDEN if c in text]
    if bad:
        raise MessageError(f"the text has {' '.join(bad)}, which a message cannot carry ({' '.join(FORBIDDEN)} are not allowed)", "message.forbidden", chars=" ".join(bad))
    if not text.isascii():
        odd = "".join(dict.fromkeys(c for c in text if not c.isascii() and c.isprintable()))
        raise MessageError(f"the text has {odd or 'a character'} that is not printable ASCII: a message carries printable ASCII only", "message.not_ascii", chars=odd)
    if not text.isprintable():
        raise MessageError("the text has a control character", "message.control")


def attempts_for(to_call: str) -> int:
    """How many times a message to the station is transmitted: EMAIL_ATTEMPTS for the email gateway, STATION_ATTEMPTS for any other."""
    return EMAIL_ATTEMPTS if to_call == EMAIL_GATEWAY else STATION_ATTEMPTS


def wait_after(attempts: int, attempts_max: int = STATION_ATTEMPTS) -> timedelta:
    """How long after attempt number `attempts` (1 to `attempts_max`) the next one is due; after the last one, how long the answer is waited for. The waits double from 30 seconds (30, 30, 60, 120, ...) and none is
    longer than MAX_WAIT_SEC."""
    if attempts >= attempts_max:
        return timedelta(seconds=FINAL_WAIT_SEC)
    return timedelta(seconds=FIRST_WAIT_SEC if attempts <= 1 else min(FIRST_WAIT_SEC * 2 ** (attempts - 2), MAX_WAIT_SEC))


def schedule_sec(attempts_max: int) -> tuple[int, ...]:
    """When the attempts of a message with `attempts_max` of them are made, in seconds from the first: 0, 30, 60, 120, 240, 480, 960, 1920, 2880, 3840."""
    at = [0]
    for n in range(1, attempts_max):
        at.append(at[-1] + int(wait_after(n, attempts_max).total_seconds()))
    return tuple(at)


def due_at(record: MessageRecord) -> datetime | None:
    """When the message that is being sent needs attention again: its next attempt, or (after the last) its failing. A message with no attempt yet is due when it was made. None for any other state."""
    if record.state != "sending":
        return None
    if record.attempts == 0 or record.last_attempt_at is None:
        return record.at
    return record.last_attempt_at + wait_after(record.attempts, record.attempts_max)
