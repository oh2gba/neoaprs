"""The message board as values: which addressees are the board's, and a stored bulletin.

Board addressees (`BLN0`..`BLNZ`, `BLN3HAMS`, `ALL`, `CQ`, `QST`, `NWS-xxxxx`, `SKY`/`CWA`) are
never conversations or acked. The board holds one entry per sender and slot; nothing ages out.
"""
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, get_args

Kind = Literal["announcement", "bulletin", "group", "nws"]
KINDS: tuple[str, ...] = get_args(Kind)

GROUP_MESSAGES = ("ALL", "CQ", "QST")
# characters of a bulletin's group name
GROUP_MAX = 5
_BULLETIN = re.compile(rf"BLN([0-9A-Z])([0-9A-Z-]{{0,{GROUP_MAX}}})$")
_WEATHER = re.compile(r"(NWS-[0-9A-Z_]{1,5}|(SKY|CWA)[0-9A-Z]{0,3})$")


@dataclass(frozen=True, slots=True)
class Slot:
    slot: str  # addressee in capitals: "BLN1", "BLNA", "BLN3HAMS", "QST"
    kind: Kind
    group: str  # group of a group bulletin ("HAMS"); empty otherwise


@dataclass(frozen=True, slots=True)
class BulletinRecord:
    sender: str
    slot: str
    group: str
    kind: Kind
    text: str
    first_heard: datetime  # a changed text restarts the count
    last_heard: datetime
    times_heard: int = 1

    @property
    def key(self) -> str:
        """Return what the board and the page call it: "OH2XYZ/BLN1"."""
        return key_of(self.sender, self.slot)


def key_of(sender: str, slot: str) -> str:
    return f"{sender}/{slot}"


def board_slot(addressee: str) -> Slot | None:
    """Return the slot a message to `addressee` is for; None if it is for a station."""
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
