"""The message board in the database: the bulletins, announcements and group messages that were heard and not deleted.

Like the message log (messagelog.py) this runs on the database thread (db.py) and says no instead of raising when the database is not open (dblog.py). A bulletin is kept by its sender and slot, so a
write is an append that nobody waits for, in order with everything else the thread was asked. The statements are bulletinsql.py's."""
import logging

from .bulletin import BulletinRecord, board_slot
from .bulletinsql import all_bulletins, delete_bulletin, save_bulletin
from .clock import Clock, utcnow
from .db import Db
from .dberror import Row
from .dblog import DbLog
from .packetcodec import parse_stamp, stamp

log = logging.getLogger("neoaprs.bulletinlog")


def bulletin_row(record: BulletinRecord) -> Row:
    """The columns of the bulletin table, in order."""
    return (record.sender, record.slot, record.group, record.text, stamp(record.first_heard), stamp(record.last_heard), record.times_heard)


def bulletin_of(row: Row) -> BulletinRecord:
    """The bulletin from its row. Raises ValueError (or TypeError) for a row this program did not write."""
    (sender, slot, group, text, first, last, times) = row
    found = board_slot(str(slot))
    if found is None:
        raise ValueError(f"{slot!r} is no slot of the board")
    return BulletinRecord(str(sender), found.slot, found.group, found.kind, str(text), parse_stamp(str(first)), parse_stamp(str(last)), int(times))


class BulletinLog(DbLog):
    def __init__(self, db: Db | None = None, clock: Clock = utcnow) -> None:
        super().__init__(db, clock, log, "the bulletins could not be read")

    # ---- appends: nobody waits
    def save(self, record: BulletinRecord) -> bool:
        """Keeps the bulletin as it is now (the row is made at once: the record goes on changing hands); False when it could not be queued."""
        row = bulletin_row(record)
        return self._append(lambda conn: save_bulletin(conn, row))

    def delete(self, record: BulletinRecord) -> bool:
        """Removes the bulletin of the record's sender and slot; False when it could not be queued."""
        sender, slot = record.sender, record.slot
        return self._append(lambda conn: delete_bulletin(conn, sender, slot))

    # ---- reads
    async def all(self) -> list[BulletinRecord]:
        """Every bulletin the database holds, the one heard last first."""
        rows: list[Row] = await self._read(all_bulletins, [])
        return self._decoded(rows, bulletin_of, "bulletin")
