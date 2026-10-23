"""The bulletins, announcements and group bulletins of our own: posted by the operator, kept in the database, shown on the message board as ours, and sent on the air by a schedule of their own.

`post` puts a text in a slot (`BLN1`, `BLNA`, `BLN3HAMS`; a text for a slot that holds one replaces it and starts its schedule again), `delete` takes the slot off the board and stops it. What is sent is a
message without an id to the slot (`ownbulletin.info_of`): nobody acknowledges it, so it goes out a few times early and then at a long interval, as the specification says of bulletins ("a few times an hour
for a few hours") and announcements ("less frequently but perhaps for several days"): neoaprs/decay.py has the numbers (a bulletin: now, after 2 minutes, after 6, then every 20 minutes until 4 hours after
the first; an announcement the same early and then every hour until 72 hours after the first). The packet goes by `beacon/path`. The sender (services/sender.py) holds back everything while the call is not
set, while the radio is not usable and between two frames of ours; what is due then goes out when the radio is back, one packet however many were missed. After the last one the entry stays on the board, as
ended, until it is deleted or posted again. The time of each packet and how often it was sent are kept in the database (ownlog.py), so a restart goes on where the schedule stopped.

A bulletin of ours that comes back from a digipeater is not heard: the inbox takes a packet from our own call for a copy of what we sent, so the board of what was heard (services/bulletins.py) never holds ours.
`changed` is told with every bulletin that is new or different (and each time one is sent), `removed` with every one that is deleted."""
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta

from neoaprs.clock import Clock, utcnow
from neoaprs.config import Config, can_transmit
from neoaprs.decay import MIN_GAP_SEC, bulletin_wait_sec
from neoaprs.ownbulletin import MAX_POSTED, OwnBulletin, PostError, info_of, make_bulletin, slot_of
from neoaprs.ownlog import OwnLog
from neoaprs.services.repeater import TICK_SEC, Repeater
from neoaprs.services.sender import Sender
from neoaprs.signal import Signal


class OwnBulletins(Repeater[str]):
    kind = "bulletin"

    def __init__(self, sender: Sender, config: Callable[[], Config], ownlog: OwnLog, clock: Clock = utcnow, tick_sec: float = TICK_SEC) -> None:
        super().__init__(sender, clock, tick_sec)
        self._config = config
        self._log = ownlog
        self.changed: Signal[[OwnBulletin]] = Signal("ownbulletins_changed")
        self.removed: Signal[[OwnBulletin]] = Signal("ownbulletins_removed")
        self._posted: dict[str, OwnBulletin] = {}

    # ---- what there is
    def records(self) -> list[OwnBulletin]:
        """Our bulletins, the oldest first."""
        return sorted(self._posted.values(), key=lambda b: (b.created_at, b.slot))

    def get(self, slot: str) -> OwnBulletin | None:
        return self._posted.get(slot)

    def next_at(self, slot: str) -> datetime | None:
        """When the bulletin is sent next (a time in the past: it waits for the radio); None for one that is over."""
        return self._due(slot)

    # ---- life
    async def start(self) -> None:
        """Takes our bulletins from the database, tells them, and starts the ticker."""
        for bulletin in await self._log.bulletins():
            self._posted[bulletin.slot] = bulletin
            self.changed.emit(bulletin)
        self.start_ticker()

    async def stop(self) -> None:
        await self.stop_ticker()

    # ---- the operator
    def post(self, slot: str, text: str) -> OwnBulletin:
        """Puts the text in the slot and sends it at once. Raises PostError, with the reason, when the call is not set, the slot or the text is wrong, or MAX_POSTED are already posted."""
        if reason := can_transmit(self._config()):
            raise PostError(reason)
        name, _, _ = slot_of(slot)
        before = self._posted.get(name)
        if before is None and len(self._posted) >= MAX_POSTED:
            raise PostError(f"{MAX_POSTED} bulletins are posted: delete one first")
        bulletin = make_bulletin(self.clock(), slot, text, before)
        self._store(bulletin)
        return bulletin

    def delete(self, slot: str) -> bool:
        """Takes the slot off the board and stops sending it; False when it holds nothing of ours."""
        bulletin = self._posted.pop(slot, None)
        if bulletin is None:
            return False
        self._refused.pop(slot, None)
        self._log.delete_bulletin(slot)
        self.removed.emit(bulletin)
        return True

    def _store(self, bulletin: OwnBulletin) -> None:
        self._posted[bulletin.slot] = bulletin
        self._log.save_bulletin(bulletin)
        self.changed.emit(bulletin)

    # ---- the schedule
    def _keys(self) -> list[str]:
        return list(self._posted)

    def _due(self, key: str) -> datetime | None:
        bulletin = self._posted.get(key)
        if bulletin is None:
            return None
        if bulletin.sent == 0:                              # new, or a new text: as soon as the last packet of the slot is a minute old
            return bulletin.created_at if bulletin.last_sent_at is None else max(bulletin.created_at, bulletin.last_sent_at + timedelta(seconds=MIN_GAP_SEC))
        assert bulletin.first_sent_at is not None and bulletin.last_sent_at is not None
        wait = bulletin_wait_sec(bulletin.plan, bulletin.sent, (bulletin.last_sent_at - bulletin.first_sent_at).total_seconds())
        return None if wait is None else bulletin.last_sent_at + timedelta(seconds=wait)

    def _transmit(self, key: str, now: datetime) -> bool:
        bulletin = self._posted[key]
        if not self._sender.send(info_of(bulletin), None):
            return False
        self._store(replace(bulletin, sent=bulletin.sent + 1, first_sent_at=bulletin.first_sent_at or now, last_sent_at=now))
        return True
