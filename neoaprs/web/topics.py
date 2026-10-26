"""The topics of the hub (neoaprs/web/hub.py) and what changes them: the table of what the pages follow, and the one place of neoaprs/web/ that connects the daemon's signals.

    stations   the station book by call            changed by StationBook.changed, .recounted and .removed; our own position in the settings moves every distance, so it is told whole
    packets    the latest 200 packets by id         changed by Tnc.packet and by the packets of APRS-IS (Services.internet_packet); the window is kept here (the daemon's database is the log, this is what a page opens with)
    tnc        the radio                             changed by Tnc.changed and Tnc.state_changed; at most four times a second
    config     the settings                          changed by Controller.config_changed, which every save emits
    messages   every message by id                   changed by Messaging.changed (a new or changed message) and .removed (one that was deleted)
    bulletins  the message board by sender/slot    changed by Bulletins.changed (a new or heard again) and .removed (one that is deleted)
    own_objects  the objects and items of ours by name     changed by OwnObjects.changed (made, changed, sent) and .removed (forgotten)
    own_bulletins  the bulletins of ours by slot           changed by OwnBulletins.changed (posted, sent) and .removed (deleted)
    station_prefs  the path and RF only of each station by call       changed by PrefBook.changed (one of them set or cleared)
    map        the base map: files, estimate, the job, and the radius of the ALOHA circle   changed by MapFetch.changed and Aloha.changed, and by every save of the settings (the area follows our position); at most four times a second
    update     Update now: whether it can, its steps    changed by SelfUpdate.changed; at most four times a second
    gps        the GPS fix, its state, and the moving station's beacon    changed by Gps.changed (a fix, a state or a problem) and by every packet of ours (the beacon went out) and every save of the settings; at most once a second

Each row's values are built in neoaprs/web/views.py and typed in `TopicValues` of neoaprs/web/protocol.py. Nothing is built for a topic nobody follows, and a patch holds the items that changed, as they are when it is made.
"""
import logging
import time
from collections.abc import Callable
from typing import Any

from neoaprs.bulletin import BulletinRecord
from neoaprs.config import Config
from neoaprs.controller import Controller
from neoaprs.message import MessageRecord
from neoaprs.ownbulletin import OwnBulletin
from neoaprs.ownobject import OwnObject
from neoaprs.packet import Packet
from neoaprs.pref import Pref
from neoaprs.signal import Signal
from neoaprs.source import Source
from neoaprs.station import Station

from .hub import StateHub, Topic
from .mapview import map_state
from .updatewire import UpdateState
from .views import bulletin_row, config_values, gps_state, message_row, own_bulletin_row, own_object_row, packet_row, pref_row, station_row, tnc_state

log = logging.getLogger("neoaprs.web")

PACKETS_KEPT = 200                      # the packets a page opens with
TNC_EVERY_SEC = 0.25                    # the TNC changes with every line it sees: told at most four times a second
GPS_EVERY_SEC = 1.0                     # the GPS gives a fix a second: told at most once a second
DISTANCES_EVERY_SEC = 30.0              # every station's distance and bearing follow our moving at most this often (our own row follows at every step of the GPS service)
PLACE_KEYS = ("station/call", "station/lat", "station/lon", "gps/source")      # (a station that turns mobile or stays moves our row between home and the fix)


class PacketWindow:
    """The latest packets as the rows a page is told, by id. The ids count up in this run of the daemon, in the order the packets came."""

    def __init__(self, size: int = PACKETS_KEPT) -> None:
        self.size = size
        self.rows: dict[int, dict[str, Any]] = {}          # in the order of their ids
        self._next = 1

    def load(self, packets: list[Packet]) -> None:
        """The packets the database holds, the newest first: they are the oldest rows of the window."""
        for packet in reversed(packets[: self.size]):
            self.add(packet)

    def add(self, packet: Packet) -> list[int]:
        """Adds the packet; the ids that changed: its own, and the one that fell out of the window."""
        number, self._next = self._next, self._next + 1
        self.rows[number] = packet_row(number, packet)
        changed = [number]
        while len(self.rows) > self.size:
            gone = next(iter(self.rows))
            del self.rows[gone]
            changed.append(gone)
        return changed

    def whole(self) -> dict[str, Any]:
        return {str(number): row for number, row in self.rows.items()}

    def item(self, key: str) -> dict[str, Any] | None:
        return self.rows.get(int(key)) if key.isdigit() else None


class Topics:
    def __init__(self, ctl: Controller, hub: StateHub, sent: Callable[[], None] | None = None, reach: Callable[[], list[str]] = list, secure: Callable[[], dict[str, Any]] | None = None) -> None:
        self.ctl = ctl
        self.hub = hub
        self._sent = sent                           # told when a packet of ours went out: the status (the count of packets, the time of the beacon) has changed
        self.window = PacketWindow()
        self._distances_at = float("-inf")          # when every station was last told whole because we moved (the monotonic clock)
        self._config = ctl.config                   # the settings the stations were last told with
        book = ctl.stationbook
        hub.add(Topic("stations", lambda: {s.call: station_row(book, s) for s in book.stations()}, lambda call: self._station(call)))
        hub.add(Topic("packets", self.window.whole, self.window.item))
        hub.add(Topic("tnc", lambda: tnc_state(ctl.tnc), interval=TNC_EVERY_SEC))
        hub.add(Topic("config", lambda: config_values(ctl.config, reach(), None if secure is None else secure())))
        hub.add(Topic("station_prefs", lambda: {call: pref_row(pref) for call, pref in ctl.prefbook.all().items()}, self._station_pref))
        hub.add(Topic("messages", lambda: {str(m.id): self._message_row(m) for m in ctl.messaging.records()}, self._message))
        hub.add(Topic("bulletins", lambda: {b.key: bulletin_row(b) for b in ctl.bulletins.records()}, self._bulletin))
        hub.add(Topic("own_objects", lambda: {o.name: self._own_object_row(o) for o in ctl.ownobjects.records()}, self._own_object))
        hub.add(Topic("own_bulletins", lambda: {b.slot: self._own_bulletin_row(b) for b in ctl.ownbulletins.records()}, self._own_bulletin))
        hub.add(Topic("map", lambda: map_state(ctl.mapfetch.status(), ctl.aloha.radius_km), interval=TNC_EVERY_SEC))
        hub.add(Topic("update", lambda: UpdateState.row(ctl.selfupdate.status()), interval=TNC_EVERY_SEC))
        hub.add(Topic("gps", lambda: gps_state(ctl.config, ctl.gps, ctl.beacon.mobile, ctl.beacon.next_due), interval=GPS_EVERY_SEC))
        self.connected = False

    def _station(self, call: str) -> dict[str, Any] | None:
        station = self.ctl.stationbook.get(call)
        return None if station is None else station_row(self.ctl.stationbook, station)

    def _station_pref(self, call: str) -> dict[str, Any] | None:
        pref = self.ctl.prefbook.all().get(call)
        return None if pref is None else pref_row(pref)

    def _bulletin(self, key: str) -> dict[str, Any] | None:
        record = self.ctl.bulletins.get(key)
        return None if record is None else bulletin_row(record)

    def _own_object(self, name: str) -> dict[str, Any] | None:
        record = self.ctl.ownobjects.get(name)
        return None if record is None else self._own_object_row(record)

    def _own_object_row(self, obj: OwnObject) -> dict[str, Any]:
        return own_object_row(obj, self.ctl.ownobjects.next_at(obj.name))

    def _own_bulletin(self, slot: str) -> dict[str, Any] | None:
        record = self.ctl.ownbulletins.get(slot)
        return None if record is None else self._own_bulletin_row(record)

    def _own_bulletin_row(self, bulletin: OwnBulletin) -> dict[str, Any]:
        return own_bulletin_row(bulletin, self.ctl.ownbulletins.next_at(bulletin.slot))

    def _message(self, key: str) -> dict[str, Any] | None:
        record = self.ctl.messaging.get(int(key)) if key.isdigit() else None
        return None if record is None else self._message_row(record)

    def _message_row(self, record: MessageRecord) -> dict[str, Any]:
        return message_row(record, self.ctl.messaging.delivery.attempts_of(record.id))

    async def start(self) -> None:
        """The window starts with the packets the database holds, and from then on the signals tell the hub."""
        self.window.load(await self.ctl.packetlog.recent(PACKETS_KEPT))
        self._config = self.ctl.config
        self.connect()

    def _followed(self) -> list[tuple[Signal[...], Callable[..., None]]]:
        """Each signal of the daemon a topic follows, with what tells the hub (the table in this module's docstring)."""
        ctl = self.ctl
        return [
            (ctl.stationbook.changed, self._station_changed), (ctl.stationbook.recounted, self._station_changed), (ctl.stationbook.removed, self._station_removed),
            (ctl.tnc.packet, self._packet), (ctl.internet_packet, self._packet), (ctl.tnc.changed, self._tnc_changed), (ctl.tnc.state_changed, self._tnc_state_changed),
            (ctl.config_changed, self._config_changed), (ctl.gps.changed, self._gps_changed), (ctl.gps.moved, self._gps_moved),
            (ctl.messaging.changed, self._message_changed), (ctl.messaging.removed, self._message_changed),
            (ctl.bulletins.changed, self._bulletin_changed), (ctl.bulletins.removed, self._bulletin_changed),
            (ctl.ownobjects.changed, self._own_object_changed), (ctl.ownobjects.removed, self._own_object_changed),
            (ctl.ownbulletins.changed, self._own_bulletin_changed), (ctl.ownbulletins.removed, self._own_bulletin_changed),
            (ctl.prefbook.changed, self._pref_changed), (ctl.mapfetch.changed, self._map_changed), (ctl.aloha.changed, self._map_changed), (ctl.selfupdate.changed, self._update_changed),
        ]

    def connect(self) -> None:
        if self.connected:
            return
        self.connected = True
        for signal, handler in self._followed():
            signal.connect(handler)

    def disconnect(self) -> None:
        if not self.connected:
            return
        self.connected = False
        for signal, handler in self._followed():
            signal.disconnect(handler)

    def _station_changed(self, station: Station) -> None:
        self.hub.changed("stations", station.call)

    def _station_removed(self, call: str) -> None:
        self.hub.changed("stations", call)

    def _tnc_changed(self) -> None:
        self.hub.changed("tnc")

    def _tnc_state_changed(self, state: Source.State) -> None:
        self.hub.changed("tnc")

    def _packet(self, packet: Packet) -> None:
        for number in self.window.add(packet):
            self.hub.changed("packets", str(number))
        if packet.direction == "out":
            self.hub.changed("gps")                 # (the beacon that went out is the latest of its kind)
            if self._sent is not None:
                self._sent()

    def _message_changed(self, record: MessageRecord) -> None:
        self.hub.changed("messages", str(record.id))

    def _bulletin_changed(self, record: BulletinRecord) -> None:
        self.hub.changed("bulletins", record.key)

    def _own_object_changed(self, obj: OwnObject) -> None:
        self.hub.changed("own_objects", obj.name)

    def _own_bulletin_changed(self, bulletin: OwnBulletin) -> None:
        self.hub.changed("own_bulletins", bulletin.slot)

    def _map_changed(self) -> None:
        self.hub.changed("map")

    def _update_changed(self) -> None:
        self.hub.changed("update")

    def _gps_changed(self) -> None:
        self.hub.changed("gps")

    def _gps_moved(self) -> None:
        """Our row follows the GPS at once (the book tells it); the distance and bearing of every other station are told whole now and then."""
        now = time.monotonic()
        if now - self._distances_at >= DISTANCES_EVERY_SEC:
            self._distances_at = now
            self.hub.changed("stations")

    def _pref_changed(self, call: str, pref: Pref | None) -> None:
        self.hub.changed("station_prefs", call)

    def _config_changed(self, config: Config) -> None:
        moved = any(key in PLACE_KEYS for key in self._config.changed(config))
        self._config = config
        self.hub.changed("config")
        self.hub.changed("gps")
        self.hub.changed("map")                     # (the area and the zoom it asks for, and whether there is a position)
        if moved:
            self.hub.changed("stations")            # (every row has a new distance and bearing)
