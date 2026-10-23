"""A bulletin, an announcement or a group bulletin of our own as a value, the rules it must keep to be sent, and the information field it makes (chapter 14 of the specification).

The packet is a message without an id to `BLN` and an identifier, padded to nine characters: a digit `BLN0`..`BLN9` for a bulletin, a capital `BLNA`..`BLNZ` for an announcement, a digit and a group name of
one to five characters (`BLN3HAMS`) for a group bulletin; the text is at most 67 characters of printable ASCII (neoaprs/aprsmessage.py). Nobody acknowledges it: `:BLN3     :Snow expected in Tampa RSN`.
We keep one of each slot (the addressee), a new text for a slot replaces the one before and starts its schedule again (neoaprs/decay.py: a few times early, then at a long interval, for a few hours for a
bulletin and a few days for an announcement); the group messages to `ALL`, `CQ` and `QST` are not posted from here.

`OwnBulletin` holds the text and where the schedule stands: how often it was sent, when it was first and last sent. Every datetime is timezone-aware UTC."""
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal

from neoaprs.aprsmessage import MessageError, format_message
from neoaprs.bulletin import board_slot
from neoaprs.coded import CodedError
from neoaprs.decay import ANNOUNCEMENT, BULLETIN, Plan
from neoaprs.message import check_text

Kind = Literal["bulletin", "announcement", "group"]
GROUP_MAX = 5
MAX_POSTED = 36                                  # how many of ours may be on the board at once


class PostError(CodedError):
    """What cannot be posted; the text says why."""


@dataclass(frozen=True, slots=True)
class OwnBulletin:
    slot: str                                    # the addressee: BLN1, BLNA, BLN3HAMS
    group: str                                   # the group of a group bulletin; empty for any other
    kind: Kind
    text: str
    created_at: datetime                         # when the text was posted
    sent: int = 0                                # how often the text was sent
    first_sent_at: datetime | None = None
    last_sent_at: datetime | None = None

    @property
    def plan(self) -> Plan:
        return ANNOUNCEMENT if self.kind == "announcement" else BULLETIN


def slot_of(slot: str) -> tuple[str, str, Kind]:
    """The slot written the way it is sent (capitals), its group, and its kind: PostError when it is none of ours (a bulletin `BLN0`..`BLN9`, an announcement `BLNA`..`BLNZ`, a group bulletin
    `BLN` a digit and a group of one to five letters, digits and dashes)."""
    name = slot.strip().upper()
    found = board_slot(name)
    if found is None or found.kind not in ("bulletin", "announcement", "group") or not name.startswith("BLN") or len(name) > 9:
        raise PostError(f"{slot!r} is not BLN0 to BLN9, BLNA to BLNZ or BLN, a digit and a group of at most {GROUP_MAX} characters", "bulletin.slot", value=slot, group_max=GROUP_MAX)
    if found.kind == "group" and (not name[3].isdigit() or not found.group.isalnum()):
        raise PostError(f"{slot!r}: a group bulletin is BLN, a digit and the group", "bulletin.group", value=slot)
    return found.slot, found.group, "group" if found.group else "announcement" if found.kind == "announcement" else "bulletin"


def make_bulletin(now: datetime, slot: str, text: str, before: OwnBulletin | None = None) -> OwnBulletin:
    """The bulletin of this slot and text, or PostError that says what is wrong. With `before` (what the slot held) the time of its last packet is kept, so that the rules of the schedule see it; the schedule
    starts again."""
    name, group, kind = slot_of(slot)
    text = text.strip()
    try:
        check_text(text)
        format_message(name, text)
    except MessageError as e:
        raise PostError(str(e), e.code, **e.params) from None
    made = OwnBulletin(name, group, kind, text, now)
    return made if before is None else replace(made, last_sent_at=before.last_sent_at)


def info_of(bulletin: OwnBulletin) -> bytes:
    """The information field of the bulletin: `:BLN1     :text`."""
    return b":" + format_message(bulletin.slot, bulletin.text)
