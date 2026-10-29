"""The message board on the wire: the topic `bulletins` (a table of rows by sender and slot) and the command to delete an entry. Models like the rest of the protocol, listed in `neoaprs/web/protocol.py`."""
from typing import Literal

from pydantic import Field

from .wirebase import Call, Iso, _Command, _Model


class BulletinRow(_Model):
    """One bulletin, announcement, group bulletin or group message on the board: what a station sent to `BLN0`..`BLN9`, `BLNA`..`BLNZ`, `BLN3HAMS` (a number or letter and a group of up to five characters) or `ALL`, `CQ`
    or `QST`. None of them is a conversation and none is acked. The rows are the values of the topic `bulletins`, keyed by `sender/slot` (`OH2XYZ/BLN1`): the board holds one row for each sender and slot, a sender
    sending the slot again replaces the text. A bulletin that is new or heard again is a `set` of its row, one that is deleted (`bulletin_delete`) a `del`. Nothing ages out: an
    entry stays on the board until it is deleted."""
    sender: str = Field(description="the call that sent it (for a third-party packet the call inside it)")
    slot: str = Field(description="the addressee in capitals: `BLN1`, `BLNA`, `BLN3HAMS`, `QST`")
    group: str = Field(description="the group of a group bulletin (`HAMS` of `BLN3HAMS`); empty for any other")
    kind: Literal["announcement", "bulletin", "group", "nws"] = Field(description="`announcement` is `BLNA`..`BLNZ`, `bulletin` is `BLN0`..`BLN9`, `group` is a group bulletin or a message to `ALL`, `CQ` or `QST`, `nws` is a weather service bulletin (`NWS-xxxxx`, `SKY...`, `CWA...`)")
    text: str
    first_heard: Iso = Field(description="when this text was first heard; a sender that changes the text starts again")
    last_heard: Iso = Field(description="when it was last heard")
    times_heard: int = Field(ge=1, description="how often this text was heard (the copies of one transmission that came by different digipeaters within 10 seconds are one)")


class BulletinDelete(_Command):
    """Removes an entry from the message board, from the database and from every page: its row is a `del` of the topic `bulletins`. The same bulletin heard again afterwards is a new entry (heard once). Answered by
    the `del`, or by an `error` (no such entry)."""
    cmd: Literal["bulletin_delete"]
    sender: Call = Field(description="the call that sent it, as the row has it")
    slot: str = Field(min_length=1, max_length=16, description="the addressee as the row has it: `BLN1`, `BLNA`, `BLN3HAMS`, `QST`")
