"""The message board: the bulletins, announcements, group bulletins and group messages the Tnc hears (neoaprs/bulletin.py says which addressees they are for), one for each sender and slot.

The inbox (services/inbox.py) hands over every message to a board addressee; none of these is a conversation and none is acked. A sender sending its slot again replaces the text (the count of
hearings starts at 1 again and `first_heard` is when the new text was first heard); the same text again only counts and moves `last_heard`, and the copies of one transmission that come by different
digipeaters within COPY_SEC of the last hearing are one hearing. Nothing leaves the board on its own (no ageing, no limit, no daily care): the operator deletes an entry (`delete`), and the same
bulletin sent again after that is a new one. The board is kept in the database (bulletinlog.py) so that a restart finds it; `changed` is told with every bulletin that is new or different, `removed`
with every one that is deleted."""
from dataclasses import replace

from neoaprs.bulletin import BulletinRecord, board_slot, key_of
from neoaprs.bulletinlog import BulletinLog
from neoaprs.clock import Clock, utcnow
from neoaprs.packet import Message, Packet
from neoaprs.signal import Signal

COPY_SEC = 10.0                                             # a copy heard this soon after the last hearing is the same transmission by another path


class Bulletins:
    def __init__(self, bulletinlog: BulletinLog, clock: Clock = utcnow) -> None:
        self._log = bulletinlog
        self.clock = clock
        self.changed: Signal[[BulletinRecord]] = Signal("bulletins_changed")
        self.removed: Signal[[BulletinRecord]] = Signal("bulletins_removed")
        self._board: dict[str, BulletinRecord] = {}

    # ---- what there is
    def records(self) -> list[BulletinRecord]:
        """The board, the one heard last first."""
        return sorted(self._board.values(), key=lambda b: (b.last_heard, b.key), reverse=True)

    def get(self, key: str) -> BulletinRecord | None:
        return self._board.get(key)

    # ---- life
    async def start(self) -> None:
        """Takes the board from the database."""
        for record in reversed(await self._log.all()):
            self._board[record.key] = record

    # ---- incoming
    def heard(self, packet: Packet, message: Message) -> None:
        """A message to a board addressee was heard (from the inbox). One without text is no bulletin and is left out."""
        found = board_slot(message.addressee)
        text = message.text.strip()
        if not packet.on_air or found is None or not text:
            return                                                   # (the board is what was heard on the radio)
        key = f"{packet.sender}/{found.slot}"
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

    # ---- deleting
    def delete(self, sender: str, slot: str) -> bool:
        """Removes the entry of the sender and slot from the board and the database; False when there is none."""
        record = self._board.pop(key_of(sender, slot), None)
        if record is None:
            return False
        self._log.delete(record)
        self.removed.emit(record)
        return True
