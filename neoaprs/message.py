"""A message as a value, and the I/O-free rules: addressee, sendable text, attempt timing."""

import random
import re
import string
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, get_args

from neoaprs.aprsmessage import FORBIDDEN, MAX_TEXT, MessageError
from neoaprs.ax25 import MAX_PATH
from neoaprs.coded import CodedError
from neoaprs.callsign import format_call, normal_name, parse_call
from neoaprs.policy import DIGI_DUPLICATE_SEC
from neoaprs.radiotype import RadioId
from neoaprs.route import DIRECT_ONLY, rf_only_path

State = Literal["sending", "acked", "rejected", "failed", "unconfirmed", "cancelled", "received", "overheard"]
Seal = Literal["", "key", "key_other", "open", "shut"]
SEALS: tuple[Seal, ...] = ("", "key", "key_other", "open", "shut")
Failure = Literal["too_long_for_radio"]
FAILURES: tuple[Failure, ...] = get_args(Failure)
STATES: tuple[str, ...] = get_args(State)
# no ack has settled them
UNSETTLED: tuple[State, ...] = ("sending", "failed", "unconfirmed")
# states an ack or rej settles
ACK_SETTLES: tuple[State, ...] = (*UNSETTLED, "cancelled")
# states the operator may resend from
RETRYABLE: tuple[State, ...] = ("failed", "unconfirmed", "rejected", "cancelled")

# transmissions of a message to a station before it fails
STATION_ATTEMPTS = 4
# the email gateway's acks rarely reach us: a mail is sent twice, then `unconfirmed`
EMAIL_ATTEMPTS = 2
# at most this many attempts and no ack: `unconfirmed`, not failed
UNCONFIRMED_MAX = 2
# first wait: just past the digipeaters' duplicate window, so a retry is not dropped; then doubles
FIRST_WAIT_SEC = int(DIGI_DUPLICATE_SEC) + 2
MAX_WAIT_SEC = 960
# how long the answer to the last attempt is awaited
FINAL_WAIT_SEC = 240
MESSAGES_HELD_MAX = 10000


_ALNUM = string.digits + string.ascii_uppercase
MSG_IDS: tuple[str, ...] = (
    *(f"{n:02d}" for n in range(1, 100)),
    *(a + b for a in string.ascii_uppercase for b in _ALNUM),
    *(d + c for d in string.digits for c in string.ascii_uppercase),
    "00",
)
# the ids we give, in order: 01..99, A0..ZZ, 0A..9Z, 00
_ID_INDEX = {ident: n for n, ident in enumerate(MSG_IDS)}
QUERY_TEXT: dict[str, str] = {
    "position": "?APRSP",
    "status": "?APRSS",
    "directs": "?APRSD",
    "path": "?APRST",
    "objects": "?APRSO",
    "messages": "?APRSM",
    "heard": "?APRSH",
    "ping": "?PING?",
    "aprs": "?APRS?",
    "igate": "?IGATE?",
    "wx": "?WX?",
}
"""The queries of the specification (APRS 1.0.1 ch. 15) that we know, by what each asks for: the one list the others take from (the page's queries below, the answers of services/queries.py, the asking of services/generalask.py, `is_query`)."""
_QUERY = re.compile(
    r"\?(?:" + "|".join(sorted((t.strip("?") for t in QUERY_TEXT.values()), key=len, reverse=True)) + r")(\?.*|\s.*)?$",
    re.IGNORECASE,
)
TELEMETRY_DEFINITIONS = ("PARM.", "UNIT.", "EQNS.", "BITS.")


# the directed queries the page can send, by kind (`?WX?` is general in the spec)
QUERIES: dict[str, str] = {
    "position": QUERY_TEXT["position"],
    "status": QUERY_TEXT["status"],
    "heard": QUERY_TEXT["directs"],
    "trace": QUERY_TEXT["path"],
    "weather": QUERY_TEXT["wx"],
}
QUERY_EVERY_SEC = 60


EMAIL_GATEWAY = "EMAIL-2"
# The services of the page's list (ui/src/lib/services.ts) and the email gateway: they live on APRS-IS, so with
# Send what I hear on a message to one goes over the Internet connection and its answers are taken from there.
INTERNET_SERVICES = ("ANSRVR", "OTA", EMAIL_GATEWAY)


# The route of a message that came over the Internet connection.
INTERNET_ROUTE = "internet"


def is_internet_service(call: str) -> bool:
    """Return whether the call is one of INTERNET_SERVICES, exactly (with its SSID)."""
    return call.strip().upper() in INTERNET_SERVICES


class MessagingError(CodedError):
    """The message cannot be sent or the command cannot be done; the text says why."""


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
    attempts_max: int = STATION_ATTEMPTS
    route: str = ""
    # "key": public key announcement; "key_other": differs from the kept key, not taken;
    # "open": encrypted and read; "shut": encrypted, unreadable here
    seal: Seal = ""
    # the ciphertext sent on the air for an encrypted message of ours
    wire: str | None = None
    radio_id: RadioId | None = None
    failure: Failure | None = None
    # dB and dBm: of the packet itself, or for ours of the ack or reject
    snr: float | None = None
    rssi: float | None = None

    @property
    def peer(self) -> str:
        return self.from_call if self.direction == "in" else self.to_call


def normal_call(text: str) -> str:
    return format_call(*parse_call(text.strip()))


def normal_path(text: str) -> tuple[str, ...]:
    """Return a comma-separated path as calls. Raise CodedError for DIRECT or too many."""
    calls = tuple(normal_call(piece) for piece in text.split(",") if piece.strip())
    if DIRECT_ONLY in calls:
        raise CodedError(
            f"{DIRECT_ONLY} is no digipeater: written alone it means no digipeaters at all",
            "path.direct_alone",
            word=DIRECT_ONLY,
        )
    if len(calls) > MAX_PATH:
        raise CodedError(
            f"{len(calls)} digipeaters is more than the {MAX_PATH} a path may have",
            "path.too_long",
            count=len(calls),
            max=MAX_PATH,
        )
    return calls


def path_choice(text: str) -> tuple[str, ...] | None:
    """Return None for an empty path (automatic), () for DIRECT, else the calls."""
    if not text.strip():
        return None
    return () if text.strip().upper() == DIRECT_ONLY else normal_path(text)


def request_path(text: str | None, fallback: tuple[str, ...], rf_only: bool) -> tuple[str, ...]:
    """Return the typed path or `fallback`, plus RFONLY if `rf_only`. Raise CodedError if bad."""
    calls = path_choice(text or "")
    path = fallback if calls is None else calls
    if not rf_only:
        return path
    added = rf_only_path(path)
    if len(added) > MAX_PATH:
        raise CodedError(
            f"path too long for Radio only: {len(path)} digipeaters and RFONLY make more than the {MAX_PATH} a path may have",
            "path.too_long_rf_only",
            count=len(path),
            max=MAX_PATH,
        )
    return added


def same_call(a: str, b: str) -> bool:
    try:
        return normal_name(a) == normal_name(b)
    except ValueError:
        return False


def addressed_to(addressee: str, ours: str) -> bool:

    return same_call(addressee, ours)


def is_query(text: str) -> bool:
    return _QUERY.match(text.strip()) is not None


def query_text(text: str) -> str:
    """Return the query trimmed and upper-cased. Raise MessageError if invalid."""
    query = text.strip()
    if len(query) < 2 or not query.startswith("?"):
        raise MessageError("a query begins with ? and says what it asks after it", "query.form")
    check_text(query)
    return query.upper()


def is_telemetry_definition(text: str) -> bool:
    return text.startswith(TELEMETRY_DEFINITIONS)


def next_msg_id(last: str | None, busy: set[str]) -> str | None:
    """Return the next id after `last` not in `busy`; None if all are busy."""
    start = _ID_INDEX[last] + 1 if last in _ID_INDEX else 0
    for step in range(len(MSG_IDS)):
        ident = MSG_IDS[(start + step) % len(MSG_IDS)]
        if ident not in busy:
            return ident
    return None


def check_text(text: str) -> None:
    """Raise MessageError if the text is empty, too long or not printable ASCII."""
    if not text.strip():
        raise MessageError("the message is empty", "message.empty")
    if len(text) > MAX_TEXT:
        raise MessageError(
            f"the text is {len(text)} characters, at most {MAX_TEXT} fit in a message",
            "message.too_long",
            length=len(text),
            max=MAX_TEXT,
        )
    bad = [c for c in FORBIDDEN if c in text]
    if bad:
        raise MessageError(
            f"the text has {' '.join(bad)}, which a message cannot carry ({' '.join(FORBIDDEN)} are not allowed)",
            "message.forbidden",
            chars=" ".join(bad),
        )
    if not text.isascii():
        odd = "".join(dict.fromkeys(c for c in text if not c.isascii() and c.isprintable()))
        raise MessageError(
            f"the text has {odd or 'a character'} that is not printable ASCII: a message carries printable ASCII only",
            "message.not_ascii",
            chars=odd,
        )
    if not text.isprintable():
        raise MessageError("the text has a control character", "message.control")


def attempts_for(to_call: str) -> int:
    return EMAIL_ATTEMPTS if to_call == EMAIL_GATEWAY else STATION_ATTEMPTS


def wait_after(attempts: int, attempts_max: int = STATION_ATTEMPTS) -> timedelta:
    """Return the wait after attempt `attempts`; after the last, the wait for an answer."""
    if attempts >= attempts_max:
        return timedelta(seconds=FINAL_WAIT_SEC)
    return timedelta(
        seconds=FIRST_WAIT_SEC if attempts <= 1 else min(FIRST_WAIT_SEC * 2 ** (attempts - 2), MAX_WAIT_SEC)
    )


def schedule_sec(attempts_max: int) -> tuple[int, ...]:
    at = [0]
    for n in range(1, attempts_max):
        at.append(at[-1] + int(wait_after(n, attempts_max).total_seconds()))
    return tuple(at)


def retry_pause(record: MessageRecord, jitter_sec: int) -> timedelta:
    """Return a deterministic pause of 0 to `jitter_sec`; zero before the first and last attempt."""
    if jitter_sec <= 0 or record.attempts == 0 or record.attempts >= record.attempts_max:
        return timedelta(0)
    return timedelta(seconds=random.Random(f"{record.to_call}/{record.id}/{record.attempts}").uniform(0, jitter_sec))  # noqa: S311


def due_at(record: MessageRecord) -> datetime | None:
    """Return when a sending message next needs attention; None otherwise."""
    if record.state != "sending":
        return None
    if record.attempts == 0 or record.last_attempt_at is None:
        return record.at
    return record.last_attempt_at + wait_after(record.attempts, record.attempts_max)
