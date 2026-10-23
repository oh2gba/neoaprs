"""The objects, items and bulletins of our own in the database, so that a restart goes on where the schedules stopped.

Like the message board's log (bulletinlog.py) this runs on the database thread (db.py) and says no instead of raising when the database is not open (dblog.py). An object is kept by its name and a bulletin by
its slot; a write is an append that nobody waits for, in order with everything else the thread was asked. The statements are ownsql.py's."""
import logging
from datetime import datetime

from .clock import Clock, utcnow
from .db import Db
from .dblog import DbLog
from .ownbulletin import OwnBulletin, slot_of
from .ownobject import OwnObject
from .ownsql import Row, all_bulletins, all_objects, delete_bulletin, delete_object, save_bulletin, save_object
from .packetcodec import parse_stamp, stamp

log = logging.getLogger("neoaprs.ownlog")


def _stamp(t: datetime | None) -> str | None:
    return None if t is None else stamp(t)


def object_row(o: OwnObject) -> Row:
    """The columns of the own_object table, in order."""
    return (o.name, o.kind, o.lat, o.lon, o.symbol_table, o.symbol_code, o.comment, o.course_deg, o.speed_kmh, o.path, int(o.alive), stamp(o.created_at), stamp(o.updated_at), o.sent, _stamp(o.last_sent_at))


def object_of(row: Row) -> OwnObject:
    """The object from its row. Raises ValueError (or TypeError) for a row this program did not write."""
    (name, kind, lat, lon, table, code, comment, course, speed, path, alive, created, updated, sent, last) = row
    if kind not in ("object", "item"):
        raise ValueError(f"{kind!r} is not a kind of object")
    return OwnObject(str(name), kind, float(lat), float(lon), str(table), str(code), parse_stamp(str(created)), parse_stamp(str(updated)), str(comment), None if course is None else int(course),
                     None if speed is None else float(speed), None if path is None else str(path), bool(alive), int(sent), None if last is None else parse_stamp(str(last)))


def bulletin_row(b: OwnBulletin) -> Row:
    """The columns of the own_bulletin table, in order."""
    return (b.slot, b.group, b.text, stamp(b.created_at), b.sent, _stamp(b.first_sent_at), _stamp(b.last_sent_at))


def bulletin_of(row: Row) -> OwnBulletin:
    """The bulletin from its row. Raises ValueError (or TypeError) for a row this program did not write."""
    (slot, group, text, created, sent, first, last) = row
    name, found_group, kind = slot_of(str(slot))
    if found_group != group:
        raise ValueError(f"the group {group!r} is not the one of {slot!r}")
    return OwnBulletin(name, found_group, kind, str(text), parse_stamp(str(created)), int(sent), None if first is None else parse_stamp(str(first)), None if last is None else parse_stamp(str(last)))


class OwnLog(DbLog):
    def __init__(self, db: Db | None = None, clock: Clock = utcnow) -> None:
        super().__init__(db, clock, log, "our objects and bulletins could not be read")

    # ---- appends: nobody waits
    def save_object(self, o: OwnObject) -> bool:
        """Keeps the object as it is now (the row is made at once: the value is frozen, but the schedule goes on changing it); False when it could not be queued."""
        row = object_row(o)
        return self._append(lambda conn: save_object(conn, row))

    def delete_object(self, name: str) -> bool:
        return self._append(lambda conn: delete_object(conn, name))

    def save_bulletin(self, b: OwnBulletin) -> bool:
        row = bulletin_row(b)
        return self._append(lambda conn: save_bulletin(conn, row))

    def delete_bulletin(self, slot: str) -> bool:
        return self._append(lambda conn: delete_bulletin(conn, slot))

    # ---- reads
    async def objects(self) -> list[OwnObject]:
        """Every object the database holds, the oldest first."""
        rows: list[Row] = await self._read(all_objects, [])
        return self._decoded(rows, object_of, "own_object")

    async def bulletins(self) -> list[OwnBulletin]:
        """Every bulletin the database holds, the oldest first."""
        rows: list[Row] = await self._read(all_bulletins, [])
        return self._decoded(rows, bulletin_of, "own_bulletin")
