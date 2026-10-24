"""The objects and items of our own: made, changed and killed by the operator, kept in the database, shown on the map as stations of their own, and sent on the air by a schedule of their own.

`set` makes an object or an item (or changes the one of that name: a changed object starts its decay again), `kill` ends one. What is sent is `ownobject.info_of`: `;NAME     *DDHHMMz<position><motion><comment>`
for an object, `)NAME!<position><comment>` for an item, from `station/call` to the tocall by the object's own path, else `beacon/path`. The schedule is the decay algorithm of the specification's Packet
Timing (neoaprs/decay.py): the new or changed object goes out at once (never sooner than a minute after the last packet of that object), then 1, 2, 4 ... minutes later, never more than the net cycle time of its
path apart, until it is changed or killed. A kill is sent as the killed form three times (0, 1 and 3 minutes after it is asked for), and then the object is forgotten; an object that was never sent is simply
removed. The sender (services/sender.py) holds back everything while the call is not set, while the radio is not usable, and between two frames of ours; what is due then goes out when the radio is back, one
packet however many were missed. The time of each packet and how often it was sent are kept in the database (ownlog.py), so a restart goes on where the schedule stopped.

Another station that reports an object with the name of one of ours takes it over (the specification's "Replacement": the original station ceases to transmit it): ours is dropped, silently, and theirs is
what the station book shows. A packet from our own call that comes back (a digipeater's copy, the TNC's echo) is nobody's report: the station book ignores it, so there is no second object.
`changed` is told with every object that is new or different (and each time one is sent), `removed` with every one that is gone."""
import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta

from neoaprs.clock import Clock, utcnow
from neoaprs.config import can_transmit
from neoaprs.decay import KILL_SENDS, MIN_GAP_SEC, kill_wait_sec, object_wait_sec
from neoaprs.message import same_call
from neoaprs.ownlog import OwnLog
from neoaprs.ownobject import OwnError, OwnObject, info_of, make_object
from neoaprs.packet import ItemReport, ObjectReport, Packet
from neoaprs.services.common import ConfigSource
from neoaprs.services.repeater import TICK_SEC, Repeater
from neoaprs.services.sender import Sender
from neoaprs.signal import Signal

log = logging.getLogger("neoaprs.ownobjects")

MAX_OBJECTS = 50                                            # objects and items of ours at once: every one is on the air for as long as it lives


class OwnObjects(Repeater[str]):
    kind = "object"

    def __init__(self, sender: Sender, config: ConfigSource, ownlog: OwnLog, is_station: Callable[[str], bool] = lambda name: False, clock: Clock = utcnow, tick_sec: float = TICK_SEC) -> None:
        super().__init__(sender, clock, tick_sec)
        self._config = config
        self._log = ownlog
        self._is_station = is_station                       # is the name that of a station of the book (not an object)? An object is never made over a station
        self.changed: Signal[[OwnObject]] = Signal("ownobjects_changed")
        self.removed: Signal[[OwnObject]] = Signal("ownobjects_removed")
        self._objects: dict[str, OwnObject] = {}

    # ---- what there is
    def records(self) -> list[OwnObject]:
        """Our objects, the oldest first."""
        return sorted(self._objects.values(), key=lambda o: (o.created_at, o.name))

    def get(self, name: str) -> OwnObject | None:
        return self._objects.get(name)

    def next_at(self, name: str) -> datetime | None:
        """When the object is sent next (a time in the past: it waits for the radio); None for one that is not."""
        return self._due(name)

    # ---- life
    async def start(self) -> None:
        """Takes our objects from the database, tells them, and starts the ticker."""
        for obj in await self._log.objects():
            self._objects[obj.name] = obj
            self.changed.emit(obj)
        self.start_ticker()

    async def stop(self) -> None:
        await self.stop_ticker()

    # ---- the operator
    def set(self, name: str, kind: str, lat: float, lon: float, symbol_table: str, symbol_code: str, comment: str = "", course_deg: int | None = None, speed_kmh: float | None = None,
            path: str | None = None) -> OwnObject:
        """Makes the object or item, or changes the one of the name: it is sent at once. Raises OwnError, with the reason, when the call is not set, the values make no object (neoaprs/ownobject.py), the
        name is our own call or a station's, or there are already MAX_OBJECTS."""
        if not self._config().station_transmit:
            raise OwnError("Receive only: nothing is sent", "transmit.off")
        if reason := can_transmit(self._config()):
            raise OwnError(reason)
        ours = self._config().station_call
        if same_call(name, ours):
            raise OwnError(f"{name} is our own call")
        if self._is_station(name):
            raise OwnError(f"{name} is a station, not the name of an object")
        before = self._objects.get(name)
        if before is None and len(self._objects) >= MAX_OBJECTS:
            raise OwnError(f"{MAX_OBJECTS} objects and items are being sent: kill one first")
        obj = make_object(self.clock(), name, kind, lat, lon, symbol_table, symbol_code, comment, course_deg, speed_kmh, path, before)
        if before is not None and before.alive and before.same_content(obj):
            return before
        self._store(obj)
        return obj

    def kill(self, name: str) -> OwnObject | None:
        """Ends the object: the killed form is sent three times and then it is forgotten. One that was never sent is removed at once (None). Raises OwnError when there is no such object of ours."""
        obj = self._objects.get(name)
        if obj is None:
            raise OwnError(f"there is no object or item {name!r} of ours")
        if not obj.alive:
            return obj
        if obj.last_sent_at is None:
            self._drop(obj)
            return None
        killed = obj.killed(self.clock())
        self._store(killed)
        return killed

    def _store(self, obj: OwnObject) -> None:
        self._objects[obj.name] = obj
        self._log.save_object(obj)
        self.changed.emit(obj)

    def _drop(self, obj: OwnObject) -> None:
        self._objects.pop(obj.name, None)
        self._refused.pop(obj.name, None)
        self._log.delete_object(obj.name)
        self.removed.emit(obj)

    # ---- the schedule
    def _keys(self) -> list[str]:
        return list(self._objects)

    def path_of(self, obj: OwnObject) -> tuple[str, ...]:
        """The digipeaters the object goes by: its own, else those of the beacon."""
        return self._config().beacon_path_calls if obj.path_calls is None else obj.path_calls

    def _due(self, key: str) -> datetime | None:
        obj = self._objects.get(key)
        if obj is None:
            return None
        if obj.sent == 0:                                   # new, changed or just killed: as soon as the last packet of it is a minute old
            return obj.updated_at if obj.last_sent_at is None else max(obj.updated_at, obj.last_sent_at + timedelta(seconds=MIN_GAP_SEC))
        assert obj.last_sent_at is not None
        wait = object_wait_sec(obj.sent, self.path_of(obj)) if obj.alive else kill_wait_sec(obj.sent)
        return None if wait is None else obj.last_sent_at + timedelta(seconds=wait)

    def _transmit(self, key: str, now: datetime) -> bool:
        obj = self._objects[key]
        if not self._sender.send(info_of(obj, now), obj.path_calls):
            return False
        sent = replace(obj, sent=obj.sent + 1, last_sent_at=now)
        if not sent.alive and sent.sent >= KILL_SENDS:
            log.info("the killed %s %s was sent %d times: forgotten", sent.kind, sent.name, sent.sent)
            self._drop(sent)
        else:
            self._store(sent)
        return True

    # ---- incoming
    def on_packet(self, packet: Packet) -> None:
        """Another station reports an object of ours as alive: it has taken it over, and we stop."""
        report = packet.decoded
        if packet.direction != "in" or not isinstance(report, (ObjectReport, ItemReport)) or not report.alive:
            return
        obj = self._objects.get(report.name)
        if obj is None or not obj.alive or same_call(packet.sender, self._config().station_call):
            return
        log.warning("%s took over our %s %s: we stop sending it", packet.sender, obj.kind, obj.name)
        self._drop(obj)
