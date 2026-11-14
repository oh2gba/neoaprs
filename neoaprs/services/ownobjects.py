"""The objects and items of our own: made, changed and killed by the operator, kept in the database, shown on the map as stations of their own, and sent on the air by a schedule of their own.

`set` makes an object or an item (or changes the one of that name: a changed object starts its decay again), `kill` ends one. What is sent is `ownobject.info_of`: `;NAME     *DDHHMMz<position><motion><comment>`
for an object, `)NAME!<position><comment>` for an item, from `station/call` to the tocall by the object's own path, else `beacon/path`. The schedule is the decay algorithm of the specification's Packet
Timing (neoaprs/decay.py): the new or changed object goes out at once (never sooner than a minute after the last packet of that object), then 1, 2, 4 ... minutes later, never more than the net cycle time of its
path apart, until it is changed or killed. A kill is sent as the killed form three times (0, 1 and 3 minutes after it is asked for), and then the object is forgotten; an object that was never sent is simply
removed. An object that is `on_request` (with or without a QRU group, services/qru.py) is kept and shown on the map but never sent on this schedule, so a kill of it is simply removal too: it goes out only as an answer
to a station that asks, `?APRSO` or its group (services/queries.py, services/qru.py). The sender (services/sender.py) holds back everything while the call is not set, while the radio is not usable, and between two frames of ours; what is due then goes out when the radio is back, one
packet however many were missed. The time of each packet and how often it was sent are kept in the database (ownlog.py), so a restart goes on where the schedule stopped. An object goes out on the radios
its choice names (`OwnObject.radios`, by id: `fm` radio 1, `hf` radio 2, `both` the two) that are enabled, else on the main radio; on each of them when it is due, and a radio that is held at that moment (the HF
modem transmitting or hearing a busy channel, for up to a minute) is given it at a later tick without another radio sending it again: the object remembers the ids of the radios that have taken this round
(`_taken`, in memory: a restart sends on all of them, which is one packet more); a radio that is away (not connected, silent) does not hold the round up, the next one goes on every radio when it is back.
The object's one path is used on each of its radios that may carry a path (none on HF), and its wait is the longest of those radios'. A new object for which no radio is named is ticked for the main radio (an
object that is changed without one keeps its own); the kill goes where the object went: on its radios in force and on every radio that is on and took a live frame of it since it was made (`_went`, in
memory: after a restart the kill goes on its radios in force alone). A radio that is removed leaves the radios of every object (`forget_radio`), as its rows leave the database.

Another station that reports an object with the name of one of ours takes it over (the specification's "Replacement": the original station ceases to transmit it): ours is dropped, silently, and theirs is
what the station book shows. A packet from our own call that comes back (a digipeater's copy, the TNC's echo) is nobody's report: the station book ignores it, so there is no second object.
`changed` is told with every object that is new or different (and each time one is sent), `removed` with every one that is gone."""
import logging
from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import datetime, timedelta

from neoaprs.clock import Clock, utcnow
from neoaprs.decay import KILL_SENDS, first_due, kill_wait_sec, object_wait_sec
from neoaprs.message import same_call
from neoaprs.ownlog import OwnLog
from neoaprs.ownobject import OwnError, OwnObject, info_of, make_object
from neoaprs.packet import DUMMY, ItemReport, ObjectReport, Packet
from neoaprs.radiotype import FM_ID, RadioId
from neoaprs.services.common import ConfigSource, transmit_refusal
from neoaprs.services.radioset import AirRadio, path_on
from neoaprs.services.repeater import TICK_SEC, Repeater
from neoaprs.services.sender import Sender
from neoaprs.signal import Signal
from neoaprs.source import Source

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
        self._taken: dict[str, set[RadioId]] = {}           # by object: the ids of the radios that have taken the round of it that is being sent
        self._went: dict[str, set[RadioId]] = {}            # by object: the ids of the radios a live frame of it went on since it was made (in this run)

    # ---- what there is
    def records(self) -> list[OwnObject]:
        """Our objects, the oldest first."""
        return sorted(self._objects.values(), key=lambda o: (o.created_at, o.name))

    def get(self, name: str) -> OwnObject | None:
        return self._objects.get(name)

    def next_at(self, name: str) -> datetime | None:
        """When the object is sent next (a time in the past: it waits for the radio); None for one that is not."""
        return self._due(name)

    def forget_radio(self, radio: RadioId) -> None:
        """The radio was removed: its id leaves the radios of every object in memory, as the removal's transaction took it out of their rows (radiosql.remove_radio); an object on no other radio
        keeps it, as its row does."""
        for name, obj in list(self._objects.items()):
            if radio in obj.radios and len(obj.radios) > 1:
                self._objects[name] = replace(obj, radios=tuple(id for id in obj.radios if id != radio))

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
            path: str | None = None, qru_group: str = "", on_request: bool = False, radio: str | None = None, *, radios: Iterable[RadioId] | None = None) -> OwnObject:
        """Makes the object or item, or changes the one of the name: it is sent at once. It goes out on the radios `radios` (their ids), else those the old word `radio` names (`fm`, `hf`, `both`, as the
        page says it until wave 4); with neither, a new object on the main radio and a changed one on its own. Raises OwnError, with the reason, when the call is not set, the values make no object
        (neoaprs/ownobject.py), the name is our own call or a station's, or there are already MAX_OBJECTS."""
        if refusal := transmit_refusal(self._config(), OwnError):
            raise refusal
        ours = self._config().station_call
        if same_call(name, ours):
            raise OwnError(f"{name} is our own call")
        if self._is_station(name):
            raise OwnError(f"{name} is a station, not the name of an object")
        before = self._objects.get(name)
        if before is None and len(self._objects) >= MAX_OBJECTS:
            raise OwnError(f"{MAX_OBJECTS} objects and items are being sent: kill one first")
        if radios is None and radio is None:
            radios = before.radios if before is not None else (self._main(),)
        obj = make_object(self.clock(), name, kind, lat, lon, symbol_table, symbol_code, comment, course_deg, speed_kmh, path, before, qru_group, on_request, "fm" if radio is None else radio, radios=radios)
        if before is not None and before.alive and before.same_content(obj):
            return before
        self._store(obj)
        return obj

    def _main(self) -> RadioId:
        """The id of the main radio, which a new object is ticked for; radio 1 while there is none (the object goes out once a radio is there)."""
        main = self._sender.radios.main
        return FM_ID if main is None else main.id

    def kill(self, name: str) -> OwnObject | None:
        """Ends the object: the killed form is sent three times and then it is forgotten. One that was never sent is removed at once (None). Raises OwnError when there is no such object of ours."""
        obj = self._objects.get(name)
        if obj is None:
            raise OwnError(f"there is no object or item {name!r} of ours")
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
            self._taken.pop(obj.name, None)                   # (new, changed or just killed: a fresh round for every radio)
        self._objects[obj.name] = obj
        self._log.save_object(obj)
        self.changed.emit(obj)

    def _drop(self, obj: OwnObject) -> None:
        self._objects.pop(obj.name, None)
        self._taken.pop(obj.name, None)
        self._went.pop(obj.name, None)
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
        if obj is None or (obj.on_request and obj.alive):
            return None
        if obj.sent == 0:                                   # new, changed or just killed: as soon as the last packet of it is a minute old
            return first_due(obj.updated_at, obj.last_sent_at)
        assert obj.last_sent_at is not None
        wait = self._live_wait(obj) if obj.alive else kill_wait_sec(obj.sent)
        return None if wait is None else obj.last_sent_at + timedelta(seconds=wait)

    def _live_wait(self, obj: OwnObject) -> int:
        """The wait after the latest packet of a live object, by the net cycle time of the path its frames really carry on each of its radios (radioset.path_on: none on HF, where every frame is direct, the
        object's path, else the radio's own, on FM); the longest of them when it goes on several."""
        config = self._config()
        radios = self._sender.radios_for(obj.radios)
        return max((object_wait_sec(obj.sent, path_on(radio, config, obj.path_calls)) for radio in radios), default=object_wait_sec(obj.sent, self.path_of(obj)))

    def _transmit(self, key: str, now: datetime) -> bool:
        """The round of the object on its radios: each that has not taken it yet and takes a frame now is given it; the round is done when every radio that is there has taken it (one that is away does not hold it up),
        and False until then (the next tick tries the radios that are still owed it, and no other sends it again). The radios are told apart by their ids."""
        obj = self._objects[key]
        taken = self._taken.setdefault(key, set())
        radios = self._radios_of(obj)
        for radio in radios:
            if radio.id not in taken and self._sender.send(info_of(obj, now), obj.path_calls, radio):
                taken.add(radio.id)
                if obj.alive:
                    self._went.setdefault(key, set()).add(radio.id)
        if not taken or any(radio.id not in taken and radio.state is Source.State.CONNECTED for radio in radios):
            return False
        self._taken.pop(key, None)
        sent = replace(obj, sent=obj.sent + 1, last_sent_at=now)
        if not sent.alive and sent.sent >= KILL_SENDS:
            log.info("the killed %s %s was sent %d times: forgotten", sent.kind, sent.name, sent.sent)
            self._drop(sent)
        else:
            self._store(sent)
        return True

    def _radios_of(self, obj: OwnObject) -> list[AirRadio]:
        """The radios a frame of the object goes on: its own (`Sender.radios_for`); for the killed form also every radio that is on and took a live frame of it, by position after those."""
        radios = self._sender.radios_for(obj.radios)
        if obj.alive or not (went := self._went.get(obj.name, set()) - {radio.id for radio in radios}):
            return radios
        return radios + [radio for radio in self._sender.radios.enabled() if radio.id in went]

    # ---- incoming
    def on_packet(self, packet: Packet) -> None:
        """Another station reports an object of ours as alive: it has taken it over, and we stop. The made-up stations of the Dummy radio take nothing over: an object of the operator's is not lost to a station that is not there."""
        report = packet.decoded
        if packet.direction != "in" or not packet.on_air or packet.via == DUMMY or not isinstance(report, (ObjectReport, ItemReport)) or not report.alive:
            return
        obj = self._objects.get(report.name)
        if obj is None or not obj.alive or same_call(packet.sender, self._config().station_call):
            return
        log.warning("%s took over our %s %s: we stop sending it", packet.sender, obj.kind, obj.name)
        self._drop(obj)
