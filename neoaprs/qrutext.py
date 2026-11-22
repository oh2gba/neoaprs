"""The words of QRU as a client says and hears them (the server's side: services/qru.py)."""

import re
from dataclasses import dataclass
from datetime import datetime

from neoaprs.callsign import AX25_CALL
from neoaprs.message import MessagingError
from neoaprs.ownobject import QRU_GROUP_MAX

ASK_KM_MAX = 20000
# the same request goes on the air once in this time
ASK_EVERY_SEC = 60
# any two requests are this far apart
ASK_GAP_SEC = 10
# objects are counted until this long after the closing line
ARRIVAL_GRACE_SEC = 30
# a list or closing line within this time of our request answers it
ANSWER_WINDOW_SEC = 300
_ASK = re.compile(rf"(?P<word>INFO|NEXT|[A-Z0-9]{{1,{QRU_GROUP_MAX}}})(?: (?P<km>\d{{1,5}}))?")
_CALL = AX25_CALL.pattern
_GROUP = rf"[A-Z0-9]{{1,{QRU_GROUP_MAX}}}"
_LIST = re.compile(
    rf"de (?P<call>{_CALL}):(?P<groups>(?:{_GROUP}\(\d{{1,5}}\) ?)*)(?P<more>\+)?(?: ?Max (?P<max>\d{{1,4}})@(?P<range>\d{{1,5}})(?P<unit>km|mi))?"
)
_GROUP_COUNT = re.compile(rf"({_GROUP})\((\d+)\)")
_SENT = re.compile(
    rf"Sent (?P<sent>\d{{1,4}}) (?P<group>{_GROUP}) Objects Max \d{{1,4}}@\d{{1,5}}(?:km|mi) de (?P<call>{_CALL})"
)
_SENT_OF = re.compile(
    rf"Sent (?P<sent>\d{{1,4}}) of \d{{1,5}} (?P<group>{_GROUP}) Objects, NEXT for more\. de (?P<call>{_CALL})"
)


def ask_text(text: str) -> str:
    """Return the request as sent (`INFO`, `NEXT` or a group and distance); else MessagingError."""
    found = _ASK.fullmatch(" ".join(text.upper().split()))
    if found is None or (found["km"] is not None and not 1 <= int(found["km"]) <= ASK_KM_MAX):
        raise MessagingError(
            f"{text!r} is no request to QRU: INFO, NEXT or a group of up to {QRU_GROUP_MAX} letters and digits, and a distance of 1 to {ASK_KM_MAX}",
            "qru.form",
            request=text,
            max=QRU_GROUP_MAX,
            km=ASK_KM_MAX,
        )
    return found[0]


@dataclass(frozen=True, slots=True)
class Listing:
    """A message listing the groups a server serves; `more` when it ends in `+`."""

    call: str
    groups: tuple[tuple[str, int], ...]
    more: bool
    max_objects: int | None
    range: int | None
    unit: str


@dataclass(frozen=True, slots=True)
class Closing:
    """The line a server ends the objects of a group with."""

    call: str
    group: str
    sent: int


def listing_of(text: str) -> Listing | None:
    """Return the list of groups the text is, or None."""
    found = _LIST.fullmatch(text.strip())
    if found is None or not (found["groups"] or found["max"]):
        return None
    groups = tuple((name, int(count)) for name, count in _GROUP_COUNT.findall(found["groups"]))
    return Listing(
        found["call"],
        groups,
        found["more"] is not None,
        None if found["max"] is None else int(found["max"]),
        None if found["range"] is None else int(found["range"]),
        found["unit"] or "",
    )


def closing_of(text: str) -> Closing | None:
    """Return the closing line the text is, or None."""
    found = _SENT.fullmatch(text.strip()) or _SENT_OF.fullmatch(text.strip())
    return None if found is None else Closing(found["call"], found["group"], int(found["sent"]))


@dataclass(frozen=True, slots=True)
class Asked:
    """The latest request we sent."""

    text: str
    at: datetime


@dataclass(frozen=True, slots=True)
class Server:
    """A QRU server that answered: its groups, limit, range and latest closing line."""

    call: str
    groups: tuple[tuple[str, int], ...]
    max_objects: int | None
    range: int | None
    unit: str
    at: datetime
    more: bool = False
    sent: str = ""
    sent_at: datetime | None = None
    sent_objects: int | None = None
    request: str = ""
    since: datetime | None = None
    received: tuple[str, ...] = ()
    settles_at: datetime | None = None
    # the radio its latest answer came on (a request to it goes there)
    radio: int | None = None
