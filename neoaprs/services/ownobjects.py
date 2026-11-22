"""The operator's own objects and items: stored, shown on the map, and repeated on air.

`set` makes or changes an object or item and restarts its decay; `kill` ends one. Sends follow
the schedule in decay.py; another station reporting an object of our name takes it over."""

import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace
from datetime import datetime, timedelta

from neoaprs.beaconrule import repeat_floor_sec
from neoaprs.clock import Clock, utcnow
from neoaprs.decay import KILL_SENDS, first_due, kill_wait_sec, object_wait_sec
from neoaprs.message import same_call
from neoaprs.ownlog import OwnLog
from neoaprs.ownobject import OwnError, OwnObject, info_of, make_object
from neoaprs.packet import DUMMY, ItemReport, ObjectReport, Packet
from neoaprs.config import NEW_OBJECTS
from neoaprs.radiotype import FM_ID, RadioId
from neoaprs.sendonrule import ids_of, start_set, text_of
from neoaprs.services.common import ConfigSource, transmit_refusal
from neoaprs.services.radioset import AirRadio, path_on
from neoaprs.services.memory import Memory, Remembered
from neoaprs.services.repeater import ROUND_HOLD_SEC as ROUND_HOLD_SEC, TICK_SEC, Repeater
from neoaprs.services.sender import Sender
from neoaprs.signal import Signal

log = logging.getLogger("neoaprs.ownobjects")

# Every object is on the air for as long as it lives, so the count is limited.
MAX_OBJECTS = 50


class OwnObjects(Repeater[str]):
    kind = "object"

    def __init__(
        self,
        sender: Sender,
        config: ConfigSource,
        ownlog: OwnLog,
        is_station: Callable[[str], bool] = lambda name: False,
        clock: Clock = utcnow,
        tick_sec: float = TICK_SEC,
        memory: Memory | None = None,
    ) -> None:
        super().__init__(sender, clock, tick_sec)
        self._config = config
        self._log = ownlog
        # True for the name of a station in the book; an object is never made over a station.
        self._is_station = is_station
        self.changed: Signal[[OwnObject]] = Signal("ownobjects_changed")
        self.removed: Signal[[OwnObject]] = Signal("ownobjects_removed")
        self._objects: dict[str, OwnObject] = {}
        self._remembered = Remembered(memory)
        # Radios of the object last saved with radios named; a new object starts with them.
        self.last_radios: tuple[RadioId, ...] = ()
        # By object: radios a live frame of it went on in this run.
        self._went: dict[str, set[RadioId]] = {}

    def records(self) -> list[OwnObject]:
        """Return our objects, oldest first."""
        return sorted(self._objects.values(), key=lambda o: (o.created_at, o.name))

    def get(self, name: str) -> OwnObject | None:
        return self._objects.get(name)

    def next_at(self, name: str) -> datetime | None:
        """Return when the object is next sent (past: waiting for the radio); None if never."""
        return self._due(name)

    def new_radios(self) -> tuple[RadioId, ...]:
        """Return the radios for a new object without named radios (sendonrule.start_set)."""
        return start_set(self.last_radios, self._config().radios)

    def radio_sets(self) -> dict[str, tuple[RadioId, ...]]:
        """Return the radios of every object by name."""
        return {name: obj.radios for name, obj in self._objects.items()}

    def keep_radios(self, sets: Mapping[str, tuple[RadioId, ...]]) -> None:
        """Send the objects of `sets` on those radios from now on and store each row again."""
        for name, radios in sets.items():
            if (obj := self._objects.get(name)) is not None:
                self._objects[name] = replace(obj, radios=radios)
                self._log.save_object(self._objects[name])

    def forget_radio(self, radio: RadioId) -> None:
        """Remove the radio from every object in memory; the set is never left empty."""
        for name, obj in list(self._objects.items()):
            if radio in obj.radios and len(obj.radios) > 1:
                self._objects[name] = replace(obj, radios=tuple(id for id in obj.radios if id != radio))
        self.last_radios = tuple(id for id in self.last_radios if id != radio)

    async def start(self) -> None:
        """Load the objects from the database, announce them and start the ticker."""
        for obj in await self._log.objects():
            self._objects[obj.name] = obj
            self.changed.emit(obj)
        self.last_radios = ids_of(await self._remembered.get(NEW_OBJECTS))
        self.start_ticker()

    async def stop(self) -> None:
        await self.stop_ticker()
        await self._remembered.flush()

    def set(
        self,
        name: str,
        kind: str,
        lat: float,
        lon: float,
        symbol_table: str,
        symbol_code: str,
        comment: str = "",
        course_deg: int | None = None,
        speed_kmh: float | None = None,
        path: str | None = None,
        qru_group: str = "",
        on_request: bool = False,
        *,
        radios: Iterable[RadioId] | None = None,
    ) -> OwnObject:
        """Make or change the object or item and send it at once; raise OwnError if refused.

        Without `radios` a new object uses `new_radios` and a changed one keeps its own."""
        if refusal := transmit_refusal(self._config(), OwnError):
            raise refusal
        ours = self._config().station_call
        if same_call(name, ours):
            raise OwnError(f"{name} is our own call", "object.own_call", name=name)
        if self._is_station(name):
            raise OwnError(f"{name} is a station, not the name of an object", "object.is_station", name=name)
        before = self._objects.get(name)
        if before is None and len(self._objects) >= MAX_OBJECTS:
            raise OwnError(
                f"{MAX_OBJECTS} objects and items are being sent: kill one first", "object.full", max=MAX_OBJECTS
            )
        named = radios is not None
        if radios is None:
            radios = before.radios if before is not None else self.new_radios()
        obj = make_object(
            self.clock(),
            name,
            kind,
            lat,
            lon,
            symbol_table,
            symbol_code,
            comment,
            course_deg,
            speed_kmh,
            path,
            before,
            qru_group,
            on_request,
            radios=radios,
        )
        if named and obj.radios != self.last_radios:
            self.last_radios = obj.radios
            self._remembered.put({NEW_OBJECTS: text_of(obj.radios)})
        if before is not None and before.alive and before.same_content(obj):
            return before
        self._store(obj)
        return obj

    def kill(self, name: str) -> OwnObject | None:
        """Send the killed form three times, then forget the object.

        Return None if it was never sent and is removed at once; raise OwnError if unknown."""
        obj = self._objects.get(name)
        if obj is None:
            raise OwnError(f"there is no object or item {name!r} of ours", "object.unknown", name=name)
        if not obj.alive:
            return obj
        if obj.last_sent_at is None or obj.on_request:
            self._drop(obj)
            return None
        killed = obj.killed(self.clock())
        self._store(killed)
        return killed

    def _store(self, obj: OwnObject) -> None:
        if obj.sent == 0:
            self._new_round(obj.name)  # new, changed or killed: fresh round on every radio
        self._objects[obj.name] = obj
        self._log.save_object(obj)
        self.changed.emit(obj)

    def _drop(self, obj: OwnObject) -> None:
        self._objects.pop(obj.name, None)
        self._new_round(obj.name)
        self._went.pop(obj.name, None)
        self._refused.pop(obj.name, None)
        self._log.delete_object(obj.name)
        self.removed.emit(obj)

    def _keys(self) -> list[str]:
        return list(self._objects)

    def path_of(self, obj: OwnObject) -> tuple[str, ...]:
        """Return the object's own path, else the path of radio 1 (`radio/1/path`)."""
        return self._config().path_calls(FM_ID) if obj.path_calls is None else obj.path_calls

    def _due(self, key: str) -> datetime | None:
        obj = self._objects.get(key)
        if obj is None or (obj.on_request and obj.alive):
            return None
        # New, changed or killed: due once its last packet is a minute old.
        if obj.sent == 0:
            return first_due(obj.updated_at, obj.last_sent_at)
        assert obj.last_sent_at is not None
        wait = self._live_wait(obj) if obj.alive else kill_wait_sec(obj.sent)
        return None if wait is None else obj.last_sent_at + timedelta(seconds=wait)

    def _live_wait(self, obj: OwnObject) -> int:
        """Return the wait after the latest packet: the longest over the radios of one round."""
        config = self._config()
        radios = self._sender.radios_for(obj.radios)
        return max(
            (
                object_wait_sec(obj.sent, path_on(radio, config, obj.path_calls), repeat_floor_sec(radio.limits))
                for radio in radios
            ),
            default=object_wait_sec(obj.sent, self.path_of(obj)),
        )

    def _transmit(self, key: str, now: datetime) -> bool:
        """Run the round on its radios; when done, count one more send.

        A killed object sent KILL_SENDS times is forgotten."""
        obj = self._objects[key]
        done, went = self._round(key, self._radios_of(obj), info_of(obj, now), obj.path_calls, now)
        if obj.alive and went:
            self._went.setdefault(key, set()).update(went)
        if not done:
            return False
        sent = replace(obj, sent=obj.sent + 1, last_sent_at=now)
        if not sent.alive and sent.sent >= KILL_SENDS:
            log.info("the killed %s %s was sent %d times: forgotten", sent.kind, sent.name, sent.sent)
            self._drop(sent)
        else:
            self._store(sent)
        return True

    def _radios_of(self, obj: OwnObject) -> list[AirRadio]:
        """Return the radios for a frame; a kill adds radios that took a live frame."""
        radios = self._sender.radios_for(obj.radios)
        if obj.alive or not (went := self._went.get(obj.name, set()) - {radio.id for radio in radios}):
            return radios
        return radios + [radio for radio in self._sender.radios.senders() if radio.id in went]

    def on_packet(self, packet: Packet) -> None:
        """Drop our object when another station reports it alive (it has taken it over)."""
        report = packet.decoded
        if (
            packet.direction != "in"
            or not packet.on_air
            or packet.via == DUMMY
            or not isinstance(report, (ObjectReport, ItemReport))
            or not report.alive
        ):
            return
        obj = self._objects.get(report.name)
        if obj is None or not obj.alive or same_call(packet.sender, self._config().station_call):
            return
        log.warning("%s took over our %s %s: we stop sending it", packet.sender, obj.kind, obj.name)
        self._drop(obj)
