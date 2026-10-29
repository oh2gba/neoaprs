"""An object or an item of our own as a value, the rules it must keep to be sent, and the information field it makes.

An object (`;`, chapter 11 of the specification) is a name of 9 characters (padded with blanks), `*` for a live one or `_` for a killed one, a time stamp, a position and a comment; an item (`)`) has a
name of 3 to 9 characters, `!` for a live one or `_` for a killed one, and no time stamp. Both carry the symbol with the position, and the comment may follow a data extension: our objects carry the course
and speed (`CSE/SPD`, the course in degrees from north with 360 for north and 000 for none, the speed in knots, 7 bytes) when they have either. The comment is at most 43 characters, 36 behind
the course and speed. The position is the uncompressed form, rounded to the hundredth of a minute. The time stamp of an object is the day of the month, the hour and the minute of the moment it is sent, in UTC
(`092345z`: the specification recommends zulu time only), so a copy that goes out later carries its own time.

A killed object is the same packet with `_` in place of `*` (an item: `_` in place of `!`), as it is sent by every APRS program on the air; the specification's table of data types lists a `-` for it, which no
program of the air reads. The name is case-sensitive, `!`, `_`, `|` and `~` are not in it (the first two end an item's name, the others are a TNC's commands) and it has no blank at either end.

`OwnObject` holds what is sent and where the schedule (neoaprs/decay.py) stands: how often it was sent since it was last changed or killed, and when it was last sent. Every datetime is timezone-aware UTC.

An object may belong to a QRU group (services/qru.py): a station that asks the addressee `QRU` for the group is answered with it. An object that is `on_request` is not sent on the schedule at all, only to a station that asks
(`?APRSO`, or its group), and so has no kill to send."""
import re
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal, get_args

from neoaprs.aprsposition import north_as_360, uncompressed_position
from neoaprs.config import MAX_COMMENT, MAX_COMMENT_PHG, SYMBOL_TABLES
from neoaprs.coded import CodedError
from neoaprs.configtypes import over_the_air_refusal
from neoaprs.message import path_choice
from neoaprs.route import DIRECT_ONLY
from neoaprs.units import KNOT_KMH

Kind = Literal["object", "item"]
KINDS: tuple[str, ...] = get_args(Kind)

OBJECT_NAME = (1, 9)
ITEM_NAME = (3, 9)
NAME_FORBIDDEN = "!_|~"
COMMENT_MAX = MAX_COMMENT                    # without a data extension
COMMENT_MAX_MOTION = MAX_COMMENT_PHG         # behind the course and speed
COURSE_MAX = 359                             # degrees from north; the course 360 is how north is written on the air
SPEED_MAX_KMH = round(999 * KNOT_KMH, 3)     # three digits of knots, 1850.148 km/h
QRU_GROUP_MAX = 8                            # the longest group name of the list of QRU servers (LIFEBOAT)
QRU_RESERVED = ("INFO", "NEXT")              # what a station says to QRU that is not a group: the list of groups, the next objects of the last group
_QRU_GROUP = re.compile(rf"[A-Z0-9]{{1,{QRU_GROUP_MAX}}}")


class OwnError(CodedError):
    """What cannot be an object of ours or be sent as one; the text says why."""


@dataclass(frozen=True, slots=True)
class OwnObject:
    name: str
    kind: Kind
    lat: float
    lon: float
    symbol_table: str
    symbol_code: str
    created_at: datetime
    updated_at: datetime                         # when it was last changed or killed
    comment: str = ""
    course_deg: int | None = None
    speed_kmh: float | None = None
    path: str | None = None                      # the digipeaters, "WIDE1-1,WIDE2-1", or DIRECT for none at all; None: the path of the beacon
    alive: bool = True                           # False once killed: the kill is being sent
    sent: int = 0                                # how often it was sent since it was last changed or killed
    last_sent_at: datetime | None = None
    qru_group: str = ""                          # the group of QRU (services/qru.py) it is offered in to a station that asks; empty: none
    on_request: bool = False                     # True: never sent on the schedule, only to a station that asks for it

    @property
    def path_calls(self) -> tuple[str, ...] | None:
        return None if self.path is None else () if self.path == DIRECT_ONLY else tuple(self.path.split(","))

    def same_content(self, other: "OwnObject") -> bool:
        """Do the two say the same on the air (everything but the times and the count of what was sent)?"""
        return replace(self, created_at=other.created_at, updated_at=other.updated_at, sent=other.sent, last_sent_at=other.last_sent_at) == other

    def killed(self, now: datetime) -> "OwnObject":
        """The object as it is once it is killed: the kill starts its own count."""
        return replace(self, alive=False, updated_at=now, sent=0)


def _name(name: str, kind: str) -> str:
    low, high = OBJECT_NAME if kind == "object" else ITEM_NAME
    if name != name.strip() or not name.isascii() or not name.isprintable() or any(c in name for c in NAME_FORBIDDEN):
        raise OwnError(f"the name {name!r} has a blank at an end or a character that cannot be in it ({' '.join(NAME_FORBIDDEN)} and anything but printable ASCII)", "object.name_chars", name=name)
    if not low <= len(name) <= high:
        raise OwnError(f"the name of {'an object' if kind == 'object' else 'an item'} is {low} to {high} characters, not {len(name)}", "object.name_length", kind=kind, min=low, max=high, length=len(name))
    return name


def _place(lat: float, lon: float, table: str, code: str) -> None:
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise OwnError(f"the position {lat}, {lon} is not on the earth", "object.position", lat=lat, lon=lon)
    if len(table) != 1 or table not in SYMBOL_TABLES or len(code) != 1 or not "!" <= code <= "~":
        raise OwnError(f"the symbol {table!r} {code!r} is not a table (/ \\ A-Z 0-9) and one printable character", "object.symbol", table=table, symbol=code)


def _motion(course: int | None, speed: float | None) -> None:
    if course is not None and not 0 <= course <= COURSE_MAX:
        raise OwnError(f"the course {course} is not between 0 and {COURSE_MAX} degrees", "object.course", value=course, max=COURSE_MAX)
    if speed is not None and not 0.0 <= speed <= SPEED_MAX_KMH:
        raise OwnError(f"the speed {speed:g} is not between 0 and {SPEED_MAX_KMH:.0f} km/h", "object.speed", value=speed, max=round(SPEED_MAX_KMH))


def _qru_group(group: str) -> str:
    """The group name in upper case ("" for none); OwnError for one that is not 1 to QRU_GROUP_MAX letters and digits or is a word QRU takes for something else."""
    found = group.strip().upper()
    if found and (_QRU_GROUP.fullmatch(found) is None or found in QRU_RESERVED):
        raise OwnError(f"the category {group!r} is 1 to {QRU_GROUP_MAX} letters and digits, and not INFO or NEXT", "object.qru_group", group=group, max=QRU_GROUP_MAX)
    return found


def _path(path: str | None) -> str | None:
    try:
        calls = path_choice(path or "")
        return None if calls is None else DIRECT_ONLY if not calls else ",".join(calls)
    except CodedError as e:
        raise OwnError(f"the path: {e}", e.code, **e.params) from None


def make_object(now: datetime, name: str, kind: str, lat: float, lon: float, symbol_table: str, symbol_code: str, comment: str = "", course_deg: int | None = None,
                speed_kmh: float | None = None, path: str | None = None, before: OwnObject | None = None, qru_group: str = "", on_request: bool = False) -> OwnObject:
    """The object of these values, or OwnError that says what is wrong. With `before` (the object of that name we have) the times and the count of what was sent are kept, so that the rules of the
    schedule see the change: a changed object starts its decay again."""
    if kind not in KINDS:
        raise OwnError(f"{kind!r} is not an object or an item", "object.kind", value=kind)
    _name(name, kind)
    _place(lat, lon, symbol_table, symbol_code)
    _motion(course_deg, speed_kmh)
    comment = comment.strip()
    if refusal := over_the_air_refusal(comment):
        raise OwnError(f"the comment: {refusal}", refusal.code, **refusal.params)
    limit = COMMENT_MAX if course_deg is None and speed_kmh is None else COMMENT_MAX_MOTION
    if len(comment) > limit:
        raise OwnError(f"the comment is {len(comment)} characters, at most {limit} fit{' behind the course and speed' if limit == COMMENT_MAX_MOTION else ''}", "object.comment_length",
                       length=len(comment), max=limit, motion=int(limit == COMMENT_MAX_MOTION))
    made = OwnObject(name, "object" if kind == "object" else "item", lat, lon, symbol_table, symbol_code, now if before is None else before.created_at, now, comment, course_deg, speed_kmh, _path(path),
                     qru_group=_qru_group(qru_group), on_request=on_request)
    return made if before is None else replace(made, sent=0, last_sent_at=before.last_sent_at)


def _motion_text(obj: OwnObject) -> bytes:
    if obj.course_deg is None and obj.speed_kmh is None:
        return b""
    course = 0 if obj.course_deg is None else north_as_360(obj.course_deg)
    knots = 0 if obj.speed_kmh is None else round(obj.speed_kmh / KNOT_KMH)
    return f"{course:03d}/{min(knots, 999):03d}".encode("ascii")


def info_of(obj: OwnObject, now: datetime) -> bytes:
    """The information field of the object as it is sent at `now`: live or, once it is killed, killed. `;LEADER   *092345z4903.50N/07201.75W>088/036`, `)AID!4903.50N\\07201.75W+comment`."""
    position = uncompressed_position(obj.lat, obj.lon, obj.symbol_table, obj.symbol_code)
    tail = _motion_text(obj) + obj.comment.encode("ascii")
    if obj.kind == "object":
        return b";" + obj.name.ljust(OBJECT_NAME[1]).encode("ascii") + (b"*" if obj.alive else b"_") + now.strftime("%d%H%M").encode("ascii") + b"z" + position + tail
    return b")" + obj.name.encode("ascii") + (b"!" if obj.alive else b"_") + position + tail
