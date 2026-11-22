"""The message board in the database: the bulletins heard and not deleted.

Runs on the database thread; returns False or an empty result instead of raising when the database
is not open. A bulletin is keyed by sender and slot."""
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
    """Return the columns of the bulletin table, in order."""
    return (record.sender, record.slot, record.group, record.text, stamp(record.first_heard), stamp(record.last_heard), record.times_heard)


def bulletin_of(row: Row) -> BulletinRecord:
    """Return the bulletin of a row. Raise ValueError or TypeError for a malformed row."""
    (sender, slot, group, text, first, last, times) = row
    found = board_slot(str(slot))
    if found is None:
        raise ValueError(f"{slot!r} is no slot of the board")
    return BulletinRecord(str(sender), found.slot, found.group, found.kind, str(text), parse_stamp(str(first)), parse_stamp(str(last)), int(times))


class BulletinLog(DbLog):
    def __init__(self, db: Db | None = None, clock: Clock = utcnow) -> None:
        super().__init__(db, clock, log, "the bulletins could not be read")

    # Appends: nobody waits for the result.
    def save(self, record: BulletinRecord) -> bool:
        """Queue saving the bulletin; return False if it could not be queued."""
        # The row is built now: the record may change before the write runs.
        row = bulletin_row(record)
        return self._append(lambda conn: save_bulletin(conn, row))

    def delete(self, record: BulletinRecord) -> bool:
        """Queue removing the bulletin of the record's sender and slot; return False if not
        queued."""
        sender, slot = record.sender, record.slot
        return self._append(lambda conn: delete_bulletin(conn, sender, slot))

    # Reads.
    async def all(self) -> list[BulletinRecord]:
        """Return every stored bulletin, last heard first."""
        rows: list[Row] = await self._read(all_bulletins, [])
        return self._decoded(rows, bulletin_of, "bulletin")
