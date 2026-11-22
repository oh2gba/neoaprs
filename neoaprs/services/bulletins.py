"""The message board: bulletins, announcements and group messages heard, one per sender and slot.

Persisted in the database; `changed` fires for each new or different bulletin, `removed` for each
deleted one.
"""

from dataclasses import replace

from neoaprs.bulletin import BulletinRecord, board_slot, key_of
from neoaprs.bulletinlog import BulletinLog
from neoaprs.clock import Clock, utcnow
from neoaprs.packet import Message, Packet
from neoaprs.signal import Signal

# a copy this soon after is the same transmission
COPY_SEC = 10.0


class Bulletins:
    def __init__(self, bulletinlog: BulletinLog, clock: Clock = utcnow) -> None:
        self._log = bulletinlog
        self.clock = clock
        self.changed: Signal[[BulletinRecord]] = Signal("bulletins_changed")
        self.removed: Signal[[BulletinRecord]] = Signal("bulletins_removed")
        self._board: dict[str, BulletinRecord] = {}

    def records(self) -> list[BulletinRecord]:
        """The board, most recently heard first."""
        return sorted(self._board.values(), key=lambda b: (b.last_heard, b.key), reverse=True)

    def get(self, key: str) -> BulletinRecord | None:
        return self._board.get(key)

    async def start(self) -> None:
        """Load the board from the database."""
        for record in reversed(await self._log.all()):
            self._board[record.key] = record

    def heard(self, packet: Packet, message: Message) -> None:
        """Record a message to a board addressee; one without text is ignored."""
        found = board_slot(message.addressee)
        text = message.text.strip()
        if not packet.on_air or found is None or not text:
            return
        key = key_of(packet.sender, found.slot)
        before = self._board.get(key)
        at = packet.heard_at
        if before is None or before.text != text:
            record = BulletinRecord(packet.sender, found.slot, found.group, found.kind, text, at, at)
        elif (at - before.last_heard).total_seconds() <= COPY_SEC:
            record = replace(before, last_heard=max(at, before.last_heard))
        else:
            record = replace(before, last_heard=max(at, before.last_heard), times_heard=before.times_heard + 1)
        self._put(record)

    def _put(self, record: BulletinRecord) -> None:
        self._board[record.key] = record
        self._log.save(record)
        self.changed.emit(record)

    def delete(self, sender: str, slot: str) -> bool:
        """Remove the entry from the board and database; return False if there is none."""
        record = self._board.pop(key_of(sender, slot), None)
        if record is None:
            return False
        self._log.delete(record)
        self.removed.emit(record)
        return True
