"""The objects, items and bulletins of our own on the wire: the topics `own_objects` and `own_bulletins` (tables of rows by name and by slot) and the commands that make, change and kill an object and post and
delete a bulletin. Models like the rest of the protocol, listed in `neoaprs/web/protocol.py`."""
from typing import Literal

from pydantic import Field

from neoaprs.config import LATITUDE, LONGITUDE
from neoaprs.ownbulletin import GROUP_MAX
from neoaprs.ownobject import COMMENT_MAX, COURSE_MAX, OBJECT_NAME, QRU_GROUP_MAX, SPEED_MAX_KMH

from .wirebase import Iso, MessageText, PathText, _Command, _Model

SLOT_LENGTH = (4, 3 + 1 + GROUP_MAX)                 # BLN and an identifier, up to a group of five characters


class OwnObjectRow(_Model):
    """One object or item of ours: what we send and where its schedule stands. The rows are the values of the topic `own_objects`, keyed by `name`: an object that is made or changed, and each time it is sent,
    is a `set` of its row, one that is gone (the kill was sent three times, or another station took the name over) a `del`. A live object is also a row of the topic `stations` with `own` true, which is what the
    map shows; a killed one leaves that topic at once and stays here, as `killing`, until its kill has been sent."""
    name: str = Field(description="the name of the object (1 to 9 characters) or of the item (3 to 9), as it is sent: case-sensitive")
    kind: Literal["object", "item"]
    lat: float
    lon: float
    symbol_table: str = Field(description="`/` (primary), `\\` (alternate) or an overlay character 0-9, A-Z")
    symbol_code: str
    comment: str = Field(description="at most 43 characters, 36 when it follows a course and speed")
    course_deg: int | None = Field(description="the course in degrees from north (0 to 359); null for none")
    speed_kmh: float | None = Field(description="the speed in km/h; null for none")
    path: str | None = Field(description="the digipeaters it goes by, calls separated by commas, or `DIRECT` for none at all; null: the path of the setting `beacon/path` is used")
    qru_group: str = Field(description="the group of QRU (1 to 8 upper-case letters and digits) a station that asks the addressee `QRU` for it is answered with this object in; empty for none")
    on_request: bool = Field(description="true: it is never sent on the decay schedule, only to a station that asks for it (`?APRSO`, or its QRU group); false: it is sent on the schedule")
    state: Literal["live", "killing"] = Field(description="`live`: it is being sent on the decay schedule; `killing`: it was killed and its killed form is being sent (three times), then it is forgotten")
    created_at: Iso = Field(description="when it was first made")
    updated_at: Iso = Field(description="when it was last changed or killed")
    sent: int = Field(ge=0, description="how often it was sent since it was last changed or killed")
    last_sent_at: Iso | None = Field(description="when it was last sent; null while it has not been sent (the call is not set, or the radio is away)")
    next_at: Iso | None = Field(description="when it is sent next: 1, 2, 4 ... minutes after the last packet, never more than the net cycle time of its path apart; a time that has passed means it waits for the radio or for the call; null for one that is `on_request`")


class OwnBulletinRow(_Model):
    """One bulletin, announcement or group bulletin of ours: its text and where its schedule stands. The rows are the values of the topic `own_bulletins`, keyed by `slot` (`BLN1`): a bulletin that is posted, and
    each time it is sent, is a `set` of its row, one that is deleted (`bulletin_unpost`) a `del`. One whose schedule is over stays, with a null `next_at`, until it is deleted or posted again."""
    slot: str = Field(description="the addressee: `BLN1`, `BLNA`, `BLN3HAMS`")
    group: str = Field(description="the group of a group bulletin (`HAMS`); empty for any other")
    kind: Literal["bulletin", "announcement", "group"]
    text: str
    posted_at: Iso = Field(description="when the text was posted")
    sent: int = Field(ge=0, description="how often it was sent")
    last_sent_at: Iso | None = Field(description="when it was last sent; null while it has not been sent")
    next_at: Iso | None = Field(description="when it is sent next; null when its schedule is over (a bulletin: now, after 2 and 6 minutes, then every 20 minutes until 4 hours after the first; an announcement: the same early, then every hour until 72 hours after the first)")


class ObjectSet(_Command):
    """Makes an object or an item of ours, or changes the one of that name (a changed object starts its schedule again, and is sent at once, never sooner than a minute after its last packet). `name` is 1 to 9
    characters for an object and 3 to 9 for an item, printable ASCII without `!`, `_`, `|` and `~` and without a blank at either end, and not our own call or the call of a station; `lat` and `lon` the position in decimal
    degrees; the symbol is a table character and a code character; `comment` at most 43 characters (36 with a course or speed); `course_deg` and `speed_kmh` the course and speed, each or both or none; `path` the digipeaters, calls
    separated by commas, or `DIRECT` for none at all (null or empty: `beacon/path`); `qru_group` the group of QRU it belongs to (up to 8 letters and digits, not `INFO` or `NEXT`; empty for none) and `on_request` true to send it
    only to a station that asks for it, never on the schedule. Nothing is sent while the call is not set. Answered by the `set` of its row in `own_objects` and `stations`, or by an `error` that names the reason."""
    cmd: Literal["object_set"]
    name: str = Field(min_length=OBJECT_NAME[0], max_length=OBJECT_NAME[1])
    kind: Literal["object", "item"]
    lat: float = Field(ge=LATITUDE[0], le=LATITUDE[1])
    lon: float = Field(ge=LONGITUDE[0], le=LONGITUDE[1])
    symbol_table: str = Field(min_length=1, max_length=1)
    symbol_code: str = Field(min_length=1, max_length=1)
    comment: str = Field(max_length=COMMENT_MAX)
    course_deg: int | None = Field(ge=0, le=COURSE_MAX)
    speed_kmh: float | None = Field(ge=0, le=SPEED_MAX_KMH)
    path: PathText | None
    qru_group: str = Field(max_length=QRU_GROUP_MAX)
    on_request: bool


class ObjectKill(_Command):
    """Kills an object or an item of ours: the killed form is sent three times (at once, after a minute and after three) and then it is forgotten, and it leaves the map now. One that was never sent is removed at
    once. Answered by the `del` of its row in `stations` (and in `own_objects` once the kill is sent, or at once), or by an `error` (no such object of ours)."""
    cmd: Literal["object_kill"]
    name: str = Field(min_length=1, max_length=OBJECT_NAME[1])


class BulletinPost(_Command):
    """Posts a bulletin, an announcement or a group bulletin of ours: `slot` is `BLN0`..`BLN9`, `BLNA`..`BLNZ` or `BLN`, a number and a group of up to five characters (`BLN3HAMS`), `text` at most 67 characters of
    printable ASCII without `|`, `~` and `{`. It is sent at once and then on the schedule of the specification (a bulletin a few times early and every 20 minutes for 4 hours, an announcement every hour for 72 hours);
    a text for a slot that holds one replaces it. Nothing is sent while the call is not set. Answered by the `set` of its row in `own_bulletins`, or by an `error` that names the reason."""
    cmd: Literal["bulletin_post"]
    slot: str = Field(min_length=SLOT_LENGTH[0], max_length=SLOT_LENGTH[1])
    text: MessageText = Field(min_length=1)


class BulletinUnpost(_Command):
    """Deletes a bulletin of ours: it is not sent again and leaves the board. Answered by the `del` of its row in `own_bulletins`, or by an `error` (no such bulletin of ours)."""
    cmd: Literal["bulletin_unpost"]
    slot: str = Field(min_length=SLOT_LENGTH[0], max_length=SLOT_LENGTH[1])
