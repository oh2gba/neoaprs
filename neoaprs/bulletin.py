"""The message board as values: which addressees are the board's and not a station's (bulletins, announcements, group bulletins, the group messages to ALL, CQ and QST, and the weather service's), and
a bulletin as the board keeps it.

A message to `BLN0`..`BLN9` is a bulletin and to `BLNA`..`BLNZ` an announcement; `BLN3HAMS` (the number or letter, then the name of a group of up to five characters) is a group bulletin; `ALL`, `CQ`
and `QST` are group messages; `NWS-xxxxx` is a bulletin of the National Weather Service and `SKY` and `CWA` (with up to three more characters) are the weather watchers' kind of it (kind "nws"). None of
them is a conversation, none is acked, and the board holds one for each sender and addressee (the slot): the sender sending the same slot again replaces the
text. Nothing ages out: an entry stays until the operator deletes it. Every datetime is timezone-aware UTC."""
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, get_args

Kind = Literal["announcement", "bulletin", "group", "nws"]
KINDS: tuple[str, ...] = get_args(Kind)

GROUP_MESSAGES = ("ALL", "CQ", "QST")
_BULLETIN = re.compile(r"BLN([0-9A-Z])([0-9A-Z-]{0,5})$")
_WEATHER = re.compile(r"(NWS-[0-9A-Z_]{1,5}|(SKY|CWA)[0-9A-Z]{0,3})$")


@dataclass(frozen=True, slots=True)
class Slot:
    slot: str                                      # the addressee in capitals: "BLN1", "BLNA", "BLN3HAMS", "QST"
    kind: Kind
    group: str                                     # the group of a group bulletin ("HAMS"); empty for any other


@dataclass(frozen=True, slots=True)
class BulletinRecord:
    sender: str
    slot: str
    group: str
    kind: Kind
    text: str
    first_heard: datetime                          # when this text was first heard: a sender that changes the text starts the count again
    last_heard: datetime
    times_heard: int = 1

    @property
    def key(self) -> str:
        """What the board and the page call it: "OH2XYZ/BLN1"."""
        return key_of(self.sender, self.slot)


def key_of(sender: str, slot: str) -> str:
    return f"{sender}/{slot}"


def board_slot(addressee: str) -> Slot | None:
    """The slot a message to `addressee` is for, or None when the addressee is a station (or anything else) and the message is no board's."""
    name = addressee.strip().upper()
    if name in GROUP_MESSAGES:
        return Slot(name, "group", "")
    if _WEATHER.match(name):
        return Slot(name, "nws", "")
    found = _BULLETIN.match(name)
    if found is None:
        return None
    identifier, group = found.groups()
    if group:
        return Slot(name, "group", group)
    return Slot(name, "bulletin" if identifier.isdigit() else "announcement", "")
