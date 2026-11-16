"""The bulletins, announcements and group bulletins of our own: posted by the operator, kept in the database, shown on the message board as ours, and sent on the air by a schedule of their own.

`post` puts a text in a slot (`BLN1`, `BLNA`, `BLN3HAMS`; a text for a slot that holds one replaces it and starts its schedule again), `delete` takes the slot off the board and stops it. What is sent is a
message without an id to the slot (`ownbulletin.info_of`): nobody acknowledges it, so it goes out a few times early and then at a long interval, as the specification says of bulletins ("a few times an hour
for a few hours") and announcements ("less frequently but perhaps for several days"): neoaprs/decay.py has the numbers (a bulletin: now, after 2 minutes, after 6, then every 20 minutes until 4 hours after
the first; an announcement the same early and then every hour until 72 hours after the first), the repeats after the early ones no more often than the floor of a radio it goes out on (30 minutes on HF and
LoRa: beaconrule.repeat_floor_sec), so that a bulletin on FM and HF repeats every 30 minutes on both. The packet goes on the bulletin's own radios (`OwnBulletin.radios`, set in the Post box; a bulletin
posted without them goes on those of the one posted last, the state row `bulletins/send_on`, and with one radio that can send on that one: sendonrule.start_set), as the set is in force
(services/sender.radios_for), in one round on all of them as an object's (services/repeater.py), each by that radio's own path (none on HF). The sender (services/sender.py)
holds back everything while the call is not set, while the radio is not usable and between two frames of ours on that radio; what is due then goes out when the radio is back, one packet however many were missed. After the last one the entry stays on the board, as
ended, until it is deleted or posted again. The time of each packet and how often it was sent are kept in the database (ownlog.py), so a restart goes on where the schedule stopped.

A bulletin of ours that comes back from a digipeater is not heard: the inbox takes a packet from our own call for a copy of what we sent, so the board of what was heard (services/bulletins.py) never holds ours.
`changed` is told with every bulletin that is new or different (and each time one is sent), `removed` with every one that is deleted."""
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

    def __init__(self, sender: Sender, config: ConfigSource, ownlog: OwnLog, clock: Clock = utcnow, tick_sec: float = TICK_SEC, memory: Memory | None = None) -> None:
        super().__init__(sender, clock, tick_sec)
        self._config = config
        self._log = ownlog
        self._remembered = Remembered(memory)
        self.last_radios: tuple[RadioId, ...] = ()          # the radios of the bulletin posted last with radios named (the state row `bulletins/send_on`): what a new one starts with
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

    def new_radios(self) -> tuple[RadioId, ...]:
        """The radios a bulletin posted without them is on (sendonrule.start_set)."""
        return start_set(self.last_radios, self._config().radios)

    def radio_sets(self) -> dict[str, tuple[RadioId, ...]]:
        """The radios of every bulletin, by slot (what a change of the radios keeps in force: neoaprs/sendonrule.py)."""
        return {slot: bulletin.radios for slot, bulletin in self._posted.items()}

    def keep_radios(self, sets: Mapping[str, tuple[RadioId, ...]]) -> None:
        """The bulletins of `sets` go out on those radios from now on, as the change of the radios that made them wrote into their rows (radiosql.put_kept); each row written again."""
        for slot, radios in sets.items():
            if (bulletin := self._posted.get(slot)) is not None:
                self._store(replace(bulletin, radios=radios))

    def forget_radio(self, radio: RadioId) -> None:
        """The radio was removed: its id leaves the radios of every bulletin in memory, as the removal's transaction took it out of their rows (radiosql.remove_radio); one on no other radio keeps it, as
        its row does, and what a new bulletin starts with loses it too."""
        for slot, bulletin in list(self._posted.items()):
            if radio in bulletin.radios and len(bulletin.radios) > 1:
                self._posted[slot] = replace(bulletin, radios=tuple(id for id in bulletin.radios if id != radio))
        self.last_radios = tuple(id for id in self.last_radios if id != radio)

    # ---- life
    async def start(self) -> None:
        """Takes our bulletins from the database, tells them, and starts the ticker."""
        for bulletin in await self._log.bulletins():
            self._posted[bulletin.slot] = bulletin
            self.changed.emit(bulletin)
        self.last_radios = ids_of(await self._remembered.get(NEW_BULLETINS))
        self.start_ticker()

    async def stop(self) -> None:
        await self.stop_ticker()
        await self._remembered.flush()

    # ---- the operator
    def post(self, slot: str, text: str, radios: Iterable[RadioId] | None = None) -> OwnBulletin:
        """Puts the text in the slot and sends it at once, on the radios `radios` (their ids), which a new bulletin then starts with; without them a text for a slot that holds one on that one's, a new one on those of the one posted last (`new_radios`). Raises
        PostError, with the reason, when the call is not set, the slot or the text is wrong, or MAX_POSTED are already posted."""
        if refusal := transmit_refusal(self._config(), PostError):
            raise refusal
        name, _, _ = slot_of(slot)
        before = self._posted.get(name)
        if before is None and len(self._posted) >= MAX_POSTED:
            raise PostError(f"{MAX_POSTED} bulletins are posted: delete one first", "bulletin.full", max=MAX_POSTED)
        bulletin = make_bulletin(self.clock(), slot, text, before, (before.radios if before is not None else self.new_radios()) if radios is None else tuple(radios))
        if radios is not None and bulletin.radios != self.last_radios:
            self.last_radios = bulletin.radios
            self._remembered.put({NEW_BULLETINS: text_of(bulletin.radios)})
        self._new_round(bulletin.slot)
        self._store(bulletin)
        return bulletin

    def delete(self, slot: str) -> bool:
        """Takes the slot off the board and stops sending it; False when it holds nothing of ours."""
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

    # ---- the schedule
    def _keys(self) -> list[str]:
        return list(self._posted)

    def _due(self, key: str) -> datetime | None:
        bulletin = self._posted.get(key)
        if bulletin is None:
            return None
        if bulletin.sent == 0:                              # new, or a new text: as soon as the last packet of the slot is a minute old
            return first_due(bulletin.created_at, bulletin.last_sent_at)
        assert bulletin.first_sent_at is not None and bulletin.last_sent_at is not None
        floor = max((repeat_floor_sec(radio.limits) for radio in self._sender.radios_for(bulletin.radios)), default=0)       # (by the radios it goes out on now)
        wait = bulletin_wait_sec(bulletin.plan, bulletin.sent, (bulletin.last_sent_at - bulletin.first_sent_at).total_seconds(), floor)
        return None if wait is None else bulletin.last_sent_at + timedelta(seconds=wait)

    def _transmit(self, key: str, now: datetime) -> bool:
        """The round of the bulletin on its radios (Repeater._round); when it is done the bulletin is counted as sent once more."""
        bulletin = self._posted[key]
        done, _ = self._round(key, self._sender.radios_for(bulletin.radios), info_of(bulletin), None, now)
        if not done:
            return False
        self._store(replace(bulletin, sent=bulletin.sent + 1, first_sent_at=bulletin.first_sent_at or now, last_sent_at=now))
        return True
