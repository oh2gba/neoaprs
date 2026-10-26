"""The words of QRU as a client says and hears them (the server's side is neoaprs/services/qru.py): what we ask a QRU server, and the messages a server answers with.

We ask with `INFO` (which groups are served near me?), `NEXT` (the next objects of the group last asked for) or a group (`RP70`, 1 to 8 upper-case letters and digits), with a distance in kilometres after it,
1 to ASK_KM_MAX (`INFO 250`, `RP70 150`). A server answers with messages from its own call to us:

    de DF8LS-10:RP70(10) RP2M(3) Max 5@50km         the groups it serves near us with the number of objects in each, the objects it sends at most, and the range; a long list is two messages,
                                                    the first ending in `+`
    Sent 5 RP70 Objects Max 5@50km de DF8LS-10      the objects of a group went
    Sent 5 of 12 RP70 Objects, NEXT for more. de DF8LS-10      the objects of a group went, and more are left

and the objects between them as ordinary objects (nothing here). The range is in kilometres or miles, as the server counts."""
import re
from dataclasses import dataclass
from datetime import datetime

from neoaprs.message import MessagingError
from neoaprs.ownobject import QRU_GROUP_MAX

ASK_KM_MAX = 20000                                  # the farthest a request names (APRSISCE's own example is `POST 20000`)
_ASK = re.compile(rf"(?P<word>INFO|NEXT|[A-Z0-9]{{1,{QRU_GROUP_MAX}}})(?: (?P<km>\d{{1,5}}))?")
_CALL = r"[A-Z0-9]{1,6}(?:-\d{1,2})?"
_GROUP = rf"[A-Z0-9]{{1,{QRU_GROUP_MAX}}}"
_LIST = re.compile(rf"de (?P<call>{_CALL}):(?P<groups>(?:{_GROUP}\(\d{{1,5}}\) ?)*)(?P<more>\+)?(?: ?Max (?P<max>\d{{1,4}})@(?P<range>\d{{1,5}})(?P<unit>km|mi))?")
_GROUP_COUNT = re.compile(rf"({_GROUP})\((\d+)\)")
_SENT = re.compile(rf"Sent (?P<sent>\d{{1,4}}) (?P<group>{_GROUP}) Objects Max \d{{1,4}}@\d{{1,5}}(?:km|mi) de (?P<call>{_CALL})")
_SENT_OF = re.compile(rf"Sent (?P<sent>\d{{1,4}}) of \d{{1,5}} (?P<group>{_GROUP}) Objects, NEXT for more\. de (?P<call>{_CALL})")


def ask_text(text: str) -> str:
    """The text of a request to QRU as it is sent, upper case, `INFO`, `NEXT` or a group with an optional distance; raises MessagingError for any other."""
    found = _ASK.fullmatch(" ".join(text.upper().split()))
    if found is None or (found["km"] is not None and not 1 <= int(found["km"]) <= ASK_KM_MAX):
        raise MessagingError(f"{text!r} is no request to QRU: INFO, NEXT or a group of up to {QRU_GROUP_MAX} letters and digits, and a distance of 1 to {ASK_KM_MAX}")
    return found[0]


@dataclass(frozen=True, slots=True)
class Listing:
    """A message that lists the groups a server serves: `more` when it ends in `+` (the list goes on in the next message). The limit and the range are None in a message that is not the last."""
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
    """The list of groups the text is, or None."""
    found = _LIST.fullmatch(text.strip())
    if found is None or not (found["groups"] or found["max"]):
        return None
    groups = tuple((name, int(count)) for name, count in _GROUP_COUNT.findall(found["groups"]))
    return Listing(found["call"], groups, found["more"] is not None, None if found["max"] is None else int(found["max"]), None if found["range"] is None else int(found["range"]), found["unit"] or "")


def closing_of(text: str) -> Closing | None:
    """The closing line the text is, or None."""
    found = _SENT.fullmatch(text.strip()) or _SENT_OF.fullmatch(text.strip())
    return None if found is None else Closing(found["call"], found["group"], int(found["sent"]))


@dataclass(frozen=True, slots=True)
class Asked:
    """The latest request we sent."""
    text: str
    at: datetime


@dataclass(frozen=True, slots=True)
class Server:
    """A QRU server that answered: `groups` with the number of objects each has near us, the `max_objects` it sends at most and its `range` in `unit` (km or mi; empty until the end of the list came), `at` when it answered last,
    `sent` its last closing line (empty before one) and `sent_at` when. `more` is set while the list ends in `+`."""
    call: str
    groups: tuple[tuple[str, int], ...]
    max_objects: int | None
    range: int | None
    unit: str
    at: datetime
    more: bool = False
    sent: str = ""
    sent_at: datetime | None = None
