"""A bulletin, announcement or group bulletin of our own as a value, with its rules.

See spec chapter 14: a message without an id to `BLN` + identifier (`BLN0`..`BLN9` bulletin,
`BLNA`..`BLNZ` announcement, `BLN3HAMS` group). One is kept per slot; a new text restarts it.
"""
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal

from neoaprs.aprsmessage import MessageError, format_message
from neoaprs.bulletin import GROUP_MAX, board_slot
from neoaprs.coded import CodedError
from neoaprs.decay import ANNOUNCEMENT, BULLETIN, Plan
from neoaprs.message import check_text
from neoaprs.ownobject import radio_set
from neoaprs.radiotype import FM_ID, RadioId

Kind = Literal["bulletin", "announcement", "group"]
MAX_POSTED = 36  # how many of ours may be on the board


class PostError(CodedError):
    """A bulletin cannot be posted."""


@dataclass(frozen=True, slots=True)
class OwnBulletin:
    slot: str  # the addressee: BLN1, BLNA, BLN3HAMS
    group: str  # the group of a group bulletin; empty otherwise
    kind: Kind
    text: str
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
        return ANNOUNCEMENT if self.kind == "announcement" else BULLETIN


def slot_of(slot: str) -> tuple[str, str, Kind]:
    """Return the slot as sent, its group and kind; raise PostError if it is not one we may post."""
    name = slot.strip().upper()
    found = board_slot(name)
    if found is None or found.kind not in ("bulletin", "announcement", "group") or not name.startswith("BLN") or len(name) > 9:
        raise PostError(f"{slot!r} is not BLN0 to BLN9, BLNA to BLNZ or BLN, a digit and a group of at most {GROUP_MAX} characters", "bulletin.slot", value=slot, group_max=GROUP_MAX)
    if found.kind == "group" and (not name[3].isdigit() or not found.group.isalnum()):
        raise PostError(f"{slot!r}: a group bulletin is BLN, a digit and the group", "bulletin.group", value=slot)
    return found.slot, found.group, "group" if found.group else "announcement" if found.kind == "announcement" else "bulletin"


def make_bulletin(now: datetime, slot: str, text: str, before: OwnBulletin | None = None, radios: Iterable[RadioId] = (FM_ID,)) -> OwnBulletin:
    """Return the bulletin of this slot, text and radios, or raise PostError.

    With `before` the time of its last packet is kept; the schedule starts again.
    """
    name, group, kind = slot_of(slot)
    text = text.strip()
    try:
        check_text(text)
        format_message(name, text)
    except MessageError as e:
        raise PostError(str(e), e.code, **e.params) from None
    made = OwnBulletin(name, group, kind, text, now, radios=tuple(radios))
    return made if before is None else replace(made, last_sent_at=before.last_sent_at)


def info_of(bulletin: OwnBulletin) -> bytes:
    return b":" + format_message(bulletin.slot, bulletin.text)
