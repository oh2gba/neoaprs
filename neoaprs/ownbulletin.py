"""A bulletin, announcement or group bulletin of our own as a value, with its rules.

See spec chapter 14: a message without an id to `BLN` + identifier (`BLN0`..`BLN9` bulletin,
`BLNA`..`BLNZ` announcement, `BLN3HAMS` group). A new post takes the lowest free slot of its kind.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from neoaprs.aprsmessage import MessageError, format_message
from neoaprs.bulletin import GROUP_MAX, board_slot
from neoaprs.coded import CodedError
from neoaprs.decay import Plan, bulletin_plan
from neoaprs.message import check_text
from neoaprs.ownobject import radio_set
from neoaprs.radiotype import FM_ID, RadioId

Kind = Literal["bulletin", "announcement", "group"]
MAX_POSTED = 36  # how many of ours may be on the board
# How long a post of each kind may be sent after its first packet, in hours.
SENT_FOR: dict[Kind, tuple[int, ...]] = {
    "bulletin": (1, 2, 4, 8, 12),
    "group": (1, 2, 4, 8, 12),
    "announcement": (24, 72, 168),
}
DEFAULT_HOURS: dict[Kind, int] = {"bulletin": 4, "group": 4, "announcement": 72}
_IDS: dict[Kind, str] = {"bulletin": "0123456789", "group": "0123456789", "announcement": "ABCDEFGHIJKLMNOPQRSTUVWXYZ"}


class PostError(CodedError):
    """A bulletin cannot be posted."""


@dataclass(frozen=True, slots=True)
class OwnBulletin:
    slot: str  # the addressee: BLN1, BLNA, BLN3HAMS
    group: str  # the group of a group bulletin; empty otherwise
    kind: Kind
    text: str
    hours: int  # how long it is sent after its first packet
    created_at: datetime  # when the text was posted
    sent: int = 0  # how often the text was sent
    first_sent_at: datetime | None = None
    last_sent_at: datetime | None = None
    # ids of the radios it goes out on, ascending, at least one
    radios: tuple[RadioId, ...] = (FM_ID,)

    def __post_init__(self) -> None:
        object.__setattr__(self, "radios", radio_set(self.radios))

    @property
    def plan(self) -> Plan:
        return bulletin_plan(self.kind == "announcement", self.hours)


def slot_of(slot: str) -> tuple[str, str, Kind]:
    """Return the slot as sent, its group and kind; raise PostError if it is not one we may post."""
    name = slot.strip().upper()
    found = board_slot(name)
    if (
        found is None
        or found.kind not in ("bulletin", "announcement", "group")
        or not name.startswith("BLN")
        or len(name) > 9
    ):
        raise PostError(
            f"{slot!r} is not BLN0 to BLN9, BLNA to BLNZ or BLN, a digit and a group of at most {GROUP_MAX} characters",
            "bulletin.slot",
            value=slot,
            group_max=GROUP_MAX,
        )
    if found.kind == "group" and (not name[3].isdigit() or not found.group.isalnum()):
        raise PostError(f"{slot!r}: a group bulletin is BLN, a digit and the group", "bulletin.group", value=slot)
    return (
        found.slot,
        found.group,
        "group" if found.group else "announcement" if found.kind == "announcement" else "bulletin",
    )


def group_ok(group: str) -> bool:
    return 0 < len(group) <= GROUP_MAX and group.isascii() and group.isalnum()


def check_group(group: str) -> str:
    """Return the group as sent (capitals); raise PostError if it is not 1 to GROUP_MAX letters and digits."""
    name = group.strip().upper()
    if not group_ok(name):
        raise PostError(f"{group!r}: a group bulletin is BLN, a digit and the group", "bulletin.group", value=group)
    return name


def free_slot(kind: Kind, group: str, taken: Iterable[str]) -> str | None:
    """Return the lowest slot of the kind (of the group) that `taken` does not hold; None if all are or the group is bad."""
    name = group.strip().upper() if kind == "group" else ""
    if kind == "group" and not group_ok(name):
        return None
    held = set(taken)
    return next((slot for c in _IDS[kind] if (slot := f"BLN{c}{name}") not in held), None)


def make_bulletin(now: datetime, slot: str, text: str, hours: int, radios: Iterable[RadioId] = (FM_ID,)) -> OwnBulletin:
    """Return the bulletin of this slot, text, Sent for and radios, or raise PostError."""
    name, group, kind = slot_of(slot)
    if hours not in SENT_FOR[kind]:
        raise PostError(f"a post cannot be sent for {hours} hours", "bulletin.hours", hours=hours)
    text = text.strip()
    try:
        check_text(text)
        format_message(name, text)
    except MessageError as e:
        raise PostError(str(e), e.code, **e.params) from None
    return OwnBulletin(name, group, kind, text, hours, now, radios=tuple(radios))


def info_of(bulletin: OwnBulletin) -> bytes:
    return b":" + format_message(bulletin.slot, bulletin.text)
