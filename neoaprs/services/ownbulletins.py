"""The operator's own bulletins, announcements and group bulletins, stored and repeated on air.

`post` puts a text in a slot (`BLN1`, `BLNA`, `BLN3HAMS`); a text for an occupied slot replaces it
and restarts its schedule. `delete` removes the slot. Sends follow the schedule in decay.py."""

from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import datetime, timedelta

from neoaprs.beaconrule import repeat_floor_sec
from neoaprs.clock import Clock, utcnow
from neoaprs.config import NEW_BULLETINS
from neoaprs.decay import bulletin_wait_sec, first_due
from neoaprs.ownbulletin import MAX_POSTED, OwnBulletin, PostError, info_of, make_bulletin, slot_of
from neoaprs.ownlog import OwnLog
from neoaprs.radiotype import RadioId
from neoaprs.sendonrule import ids_of, start_set, text_of
from neoaprs.services.common import ConfigSource, transmit_refusal
from neoaprs.services.memory import Memory, Remembered
from neoaprs.services.repeater import TICK_SEC, Repeater
from neoaprs.services.sender import Sender
from neoaprs.signal import Signal


class OwnBulletins(Repeater[str]):
    kind = "bulletin"

    def __init__(
        self,
        sender: Sender,
        config: ConfigSource,
        ownlog: OwnLog,
        clock: Clock = utcnow,
        tick_sec: float = TICK_SEC,
        memory: Memory | None = None,
    ) -> None:
        super().__init__(sender, clock, tick_sec)
        self._config = config
        self._log = ownlog
        self._remembered = Remembered(memory)
        # Radios of the bulletin last posted with radios named; a new bulletin starts with them.
        self.last_radios: tuple[RadioId, ...] = ()
        self.changed: Signal[[OwnBulletin]] = Signal("ownbulletins_changed")
        self.removed: Signal[[OwnBulletin]] = Signal("ownbulletins_removed")
        self._posted: dict[str, OwnBulletin] = {}

    def records(self) -> list[OwnBulletin]:
        """Return our bulletins, oldest first."""
        return sorted(self._posted.values(), key=lambda b: (b.created_at, b.slot))

    def get(self, slot: str) -> OwnBulletin | None:
        return self._posted.get(slot)

    def next_at(self, slot: str) -> datetime | None:
        """Return when the bulletin is next sent (past: waiting for the radio); None if over."""
        return self._due(slot)

    def new_radios(self) -> tuple[RadioId, ...]:
        """Return the radios for a bulletin posted without any (sendonrule.start_set)."""
        return start_set(self.last_radios, self._config().radios)

    def radio_sets(self) -> dict[str, tuple[RadioId, ...]]:
        """Return the radios of every bulletin by slot."""
        return {slot: bulletin.radios for slot, bulletin in self._posted.items()}

    def keep_radios(self, sets: Mapping[str, tuple[RadioId, ...]]) -> None:
        """Send the bulletins of `sets` on those radios from now on and store each row again."""
        for slot, radios in sets.items():
            if (bulletin := self._posted.get(slot)) is not None:
                self._store(replace(bulletin, radios=radios))

    def forget_radio(self, radio: RadioId) -> None:
        """Remove the radio from every bulletin in memory; a bulletin on no other radio keeps it."""
        for slot, bulletin in list(self._posted.items()):
            if radio in bulletin.radios and len(bulletin.radios) > 1:
                self._posted[slot] = replace(bulletin, radios=tuple(id for id in bulletin.radios if id != radio))
        self.last_radios = tuple(id for id in self.last_radios if id != radio)

    # ---- life
    async def start(self) -> None:
        """Load the bulletins from the database, announce them and start the ticker."""
        for bulletin in await self._log.bulletins():
            self._posted[bulletin.slot] = bulletin
            self.changed.emit(bulletin)
        self.last_radios = ids_of(await self._remembered.get(NEW_BULLETINS))
        self.start_ticker()

    async def stop(self) -> None:
        await self.stop_ticker()
        await self._remembered.flush()

    def post(self, slot: str, text: str, radios: Iterable[RadioId] | None = None) -> OwnBulletin:
        """Put the text in the slot and send it at once; raise PostError if refused.

        Without `radios` an occupied slot keeps its radios and a new one uses `new_radios`."""
        if refusal := transmit_refusal(self._config(), PostError):
            raise refusal
        name, _, _ = slot_of(slot)
        before = self._posted.get(name)
        if before is None and len(self._posted) >= MAX_POSTED:
            raise PostError(f"{MAX_POSTED} bulletins are posted: delete one first", "bulletin.full", max=MAX_POSTED)
        bulletin = make_bulletin(
            self.clock(),
            slot,
            text,
            before,
            (before.radios if before is not None else self.new_radios()) if radios is None else tuple(radios),
        )
        if radios is not None and bulletin.radios != self.last_radios:
            self.last_radios = bulletin.radios
            self._remembered.put({NEW_BULLETINS: text_of(bulletin.radios)})
        self._new_round(bulletin.slot)
        self._store(bulletin)
        return bulletin

    def delete(self, slot: str) -> bool:
        """Remove the slot and stop sending it; return False if it holds nothing of ours."""
        bulletin = self._posted.pop(slot, None)
        if bulletin is None:
            return False
        self._refused.pop(slot, None)
        self._new_round(slot)
        self._log.delete_bulletin(slot)
        self.removed.emit(bulletin)
        return True

    def _store(self, bulletin: OwnBulletin) -> None:
        self._posted[bulletin.slot] = bulletin
        self._log.save_bulletin(bulletin)
        self.changed.emit(bulletin)

    def _keys(self) -> list[str]:
        return list(self._posted)

    def _due(self, key: str) -> datetime | None:
        bulletin = self._posted.get(key)
        if bulletin is None:
            return None
        # New or changed text: due once the slot's last packet is a minute old.
        if bulletin.sent == 0:
            return first_due(bulletin.created_at, bulletin.last_sent_at)
        assert bulletin.first_sent_at is not None and bulletin.last_sent_at is not None
        floor = max((repeat_floor_sec(radio.limits) for radio in self._sender.radios_for(bulletin.radios)), default=0)
        wait = bulletin_wait_sec(
            bulletin.plan, bulletin.sent, (bulletin.last_sent_at - bulletin.first_sent_at).total_seconds(), floor
        )
        return None if wait is None else bulletin.last_sent_at + timedelta(seconds=wait)

    def _transmit(self, key: str, now: datetime) -> bool:
        """Run the round on its radios; when done, count one more send."""
        bulletin = self._posted[key]
        done, _ = self._round(key, self._sender.radios_for(bulletin.radios), info_of(bulletin), None, now)
        if not done:
            return False
        self._store(
            replace(bulletin, sent=bulletin.sent + 1, first_sent_at=bulletin.first_sent_at or now, last_sent_at=now)
        )
        return True
