"""The topics of the hub (hub.py) and the daemon signals that change them.

This is the one place in neoaprs/web/ that connects those signals (`Topics._followed` lists them).
Row values are built in views.py and typed in `TopicValues` (protocol.py).
"""

import logging
import time
from collections.abc import Callable
from typing import Any

from neoaprs import pairsetting
from neoaprs.bulletin import BulletinRecord
from neoaprs.chat import Line
from neoaprs.config import Config
from neoaprs.callsign import normal_name
from neoaprs.controller import Controller
from neoaprs.direwolfmodem import DirewolfModem
from neoaprs.mercurymodem import Mercury
from neoaprs.message import MessageRecord, MessagingError
from neoaprs.ownbulletin import OwnBulletin
from neoaprs.ownobject import OwnObject
from neoaprs.packet import Packet
from neoaprs.pref import Fired, Pref
from neoaprs.radiospec import RadioId
from neoaprs.route import digipeaters, through_gateway
from neoaprs.shown import Shown
from neoaprs.signal import Signal
from neoaprs.station import Station
from neoaprs.stationbook import carries_path

from .callroutes import CallRoutes
from .chatwire import ChatFreshMsg, ChatLineRow
from .hub import StateHub, Topic
from .layerfeed import LayerLooks
from .satellitefeed import SatelliteLooks
from .igatefeed import IgateLooks
from .levelfeed import LevelFeed, Leveled, RadioLevels
from .mapview import map_state
from .packetwindow import PACKETS_KEPT, PacketWindow
from .scopefeed import RadioScopes, ScopeFeed
from .views import NO_PLAN
from .skedview import skeds_state
from .updatewire import UpdateState
from .radioview import radio_row
from .views import (
    StationRadios,
    bulletin_row,
    config_values,
    general_state,
    gps_state,
    igate_state,
    key_row,
    message_row,
    on_their_way,
    own_bulletin_row,
    own_object_row,
    pref_row,
    qru_state,
    station_alert_message,
    station_row,
)

log = logging.getLogger("neoaprs.web")

TNC_EVERY_SEC = 0.25  # a radio's row changes with every line its TNC sees
GPS_EVERY_SEC = 1.0  # the GPS gives a fix a second
IGATE_EVERY_SEC = 1.0  # the iGate counts every packet it hears
# Stations' distances and bearings follow our movement at most this often; our own row follows every
# GPS step.
DISTANCES_EVERY_SEC = 30.0
# Settings that move our own row between home and the GPS fix.
PLACE_KEYS = ("station/call", "station/lat", "station/lon", "gps/source")


def radios_in_force(config: Config) -> tuple[object, ...]:
    """Return the radio facts the station, message and object rows depend on.

    Names, radio settings and paths are left out; a path change is signalled by PrefBook.
    """
    return (
        tuple((s.id, s.kind, s.type, s.enabled, s.position, s.removed) for s in config.radios),
        config.email_choice,
        pairsetting.own_calls(config.station_call, config.pairs),
    )


class Topics:
    def __init__(
        self,
        ctl: Controller,
        hub: StateHub,
        sent: Callable[[], None] | None = None,
        reach: Callable[[], list[str]] = list,
        secure: Callable[[], dict[str, Any]] | None = None,
        tell: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.ctl = ctl
        self.hub = hub
        # called when a packet of ours went out or the settings changed, so the status is resent
        self._sent = sent
        # sends a message to every open page, for messages no topic keeps
        self._tell = tell
        self.window = PacketWindow()
        # Scope rows, receive levels and layer tables go only to the pages that asked for them.
        self.scopes = RadioScopes(self._wire_scope)
        self.levels = RadioLevels(self._wire_level)
        self.layers = LayerLooks(ctl.layers)
        self.satellites = SatelliteLooks(ctl.satellites)
        self.igate_looks = IgateLooks(ctl.igate)
        # monotonic time stations were last told whole because we moved
        self._distances_at = float("-inf")
        self._config = ctl.config  # the settings the stations were last told with
        self._follow_ticks(ctl.config)
        self.station_radios, self.call_routes = self._routes()
        hub.add(Topic("stations", self._stations, lambda call: self._station(call)))
        hub.add(Topic("packets", self.window.whole, self.window.item))
        hub.add(Topic("radios", self._radios, self._radio, interval=TNC_EVERY_SEC))
        hub.add(Topic("config", lambda: config_values(ctl.config, reach(), None if secure is None else secure())))
        hub.add(
            Topic(
                "station_prefs",
                lambda: {call: pref_row(pref) for call, pref in ctl.prefbook.all().items()},
                self._station_pref,
            )
        )
        hub.add(Topic("messages", self._messages, self._message))
        hub.add(
            Topic(
                "station_keys",
                lambda: {call: key_row(*entry) for call, entry in ctl.keyring.peers().items()},
                self._station_key,
            )
        )
        hub.add(Topic("bulletins", lambda: {b.key: bulletin_row(b) for b in ctl.bulletins.records()}, self._bulletin))
        hub.add(
            Topic(
                "own_objects",
                lambda: {o.name: self._own_object_row(o) for o in ctl.ownobjects.records()},
                self._own_object,
            )
        )
        hub.add(
            Topic(
                "own_bulletins",
                lambda: {b.slot: self._own_bulletin_row(b) for b in ctl.ownbulletins.records()},
                self._own_bulletin,
            )
        )
        hub.add(
            Topic(
                "map",
                lambda: map_state(ctl.mapfetch.status(), ctl.aloha.radii, ctl.layers.states()),
                interval=TNC_EVERY_SEC,
            )
        )
        hub.add(Topic("update", lambda: UpdateState.row(ctl.selfupdate.status()), interval=TNC_EVERY_SEC))
        hub.add(Topic("gps", self._gps, interval=GPS_EVERY_SEC))
        hub.add(Topic("igate", lambda: igate_state(ctl.config, ctl.igate), interval=IGATE_EVERY_SEC))
        hub.add(Topic("qru", lambda: qru_state(ctl.qruask)))
        hub.add(Topic("skeds", lambda: skeds_state(ctl.skeds)))
        hub.add(Topic("chat", lambda: {"state": ctl.chat.state}))
        hub.add(
            Topic(
                "chat_lines", lambda: {str(line.id): self._chat_row(line) for line in ctl.chat.lines()}, self._chat_line
            )
        )
        hub.add(Topic("general", lambda: general_state(ctl.generalask.asked(), ctl.generalask.sent_on())))
        hub.add(Topic("call_routes", self.call_routes.whole, self.call_routes.item))
        self.connected = False

    def _routes(self) -> tuple[StationRadios, CallRoutes]:
        """Return what a station's row says of the radios, and the same for calls with no row shown."""
        ctl = self.ctl
        radios = StationRadios(
            self._radio_choice, self._radio_now, self._paths_of, self._replies_of, ctl.messaging.text_max
        )
        return radios, CallRoutes(
            lambda call: self._station(call) is not None,
            lambda: [*ctl.radios.chosen(), *(call for call, pref in ctl.prefbook.all().items() if pref.rf_only)],
            lambda radio: ctl.prefbook.paths(radio),
            lambda: (spec.id for spec in ctl.config.live_radios),
            radios,
        )

    def _chat_row(self, line: Line) -> dict[str, Any]:
        return ChatLineRow.of(line, self.ctl.chat.ours(line))

    def _chat_line(self, key: str) -> dict[str, Any] | None:
        line = self.ctl.chat.line(int(key)) if key.isdigit() else None
        return None if line is None else self._chat_row(line)

    def _gps(self) -> dict[str, Any]:
        beacon = self.ctl.moving_beacon()
        return gps_state(
            self.ctl.config,
            self.ctl.gps,
            NO_PLAN if beacon is None else beacon.mobile,
            None if beacon is None else beacon.next_due,
        )

    def _stations(self) -> dict[str, Any]:
        rows = ((s.call, self._row(s)) for s in self.ctl.stationbook.stations())
        return {call: row for call, row in rows if row is not None}

    def _station(self, call: str) -> dict[str, Any] | None:
        station = self.ctl.stationbook.get(call)
        return None if station is None else self._row(station)

    def _row(self, station: Station) -> dict[str, Any] | None:
        """Return the station's row as the page is shown it.

        With the iGate off, an internet-only station has none and others show their radio side; so
        with what an iGate put on the air when that is not shown.
        """
        shown = Shown.of(self.ctl.config).station(station)
        return None if shown is None else station_row(self.ctl.stationbook, shown, self.station_radios)

    # What a station's row says of the radios; the daemon decides, the page works none of it out.
    def _radio_choice(self, call: str) -> RadioId | None:
        """Return the operator's radio for the station while it is enabled.

        Return None when the daemon chooses.
        """
        chosen = self.ctl.radios.choice(call)
        return (
            chosen if chosen is not None and any(spec.id == chosen for spec in self.ctl.config.enabled_radios) else None
        )

    def _radio_now(self, call: str) -> RadioId | None:
        """Return the radio a message to the station goes on now, or None."""
        try:
            return self.ctl.messaging.message_radios.station(call).id
        except MessagingError:
            return None

    def _paths_of(self, call: str) -> dict[RadioId, tuple[str, ...]]:
        """Return the path set for the station on each live radio, by radio id."""
        try:
            key = normal_name(call)
        except ValueError:
            return {}
        found = ((spec.id, self.ctl.prefbook.path_on(key, spec.id)) for spec in self.ctl.config.live_radios)
        return {id: path for id, path in found if path is not None}

    def _replies_of(self, call: str) -> dict[RadioId, tuple[str, ...]]:
        """Return our message or ack path to the station, without RFONLY.

        One entry per live radio that carries no path.
        """
        live = self.ctl.config.live_radios
        return {
            spec.id: digipeaters(self.ctl.prefbook.path_for(call, None, spec.id))
            for spec in live
            if not carries_path(live, spec.id)
        }

    def _radios(self) -> dict[str, Any]:
        rows = ((str(spec.id), self._radio_of(spec.id)) for spec in self.ctl.config.radios)
        return {key: row for key, row in rows if row is not None}

    def _radio(self, key: str) -> dict[str, Any] | None:
        return self._radio_of(int(key)) if key.isdigit() else None

    def _radio_of(self, id: RadioId) -> dict[str, Any] | None:
        spec = self.ctl.config.radio(id)
        return (
            None
            if spec is None
            else radio_row(
                spec, self.ctl.config.radios, self.ctl.radios.get(id), self.ctl.radios.claims, self.ctl.rigstatus
            )
        )

    def _station_pref(self, call: str) -> dict[str, Any] | None:
        pref = self.ctl.prefbook.all().get(call)
        return None if pref is None else pref_row(pref)

    def _station_key(self, call: str) -> dict[str, Any] | None:
        entry = self.ctl.keyring.peers().get(call)
        return None if entry is None else key_row(*entry)

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

    def _messages(self) -> dict[str, Any]:
        return {str(m.id): self._message_row(m) for m in self.ctl.messaging.records() if self._shown_message(m)}

    def _message(self, key: str) -> dict[str, Any] | None:
        record = self.ctl.messaging.get(int(key)) if key.isdigit() else None
        return None if record is None or not self._shown_message(record) else self._message_row(record)

    def _shown_message(self, record: MessageRecord) -> bool:
        """Return whether the message is shown: one overheard as an iGate put it on the air is not while those are not."""
        return self.ctl.config.igate_show_gated or record.state != "overheard" or not through_gateway(record.route)

    def _message_row(self, record: MessageRecord) -> dict[str, Any]:
        sending = record.direction == "out" and record.state == "sending"
        radio = self.ctl.messaging.radio_now(record) if sending else None
        return message_row(
            record,
            self.ctl.messaging.delivery.attempts_of(record.id),
            self.ctl.messaging.queued(record),
            None if radio is None else radio.id,
        )

    async def start(self) -> None:
        """Load the packet window from the database and connect the signals."""
        self.window.load(await self.ctl.packetlog.window(PACKETS_KEPT))
        self._config = self.ctl.config
        self._follow_ticks(self._config)
        self.connect()

    def _followed(self) -> list[tuple[Signal[...], Callable[..., None]]]:
        """Return each followed signal with its handler (see the table in the module docstring)."""
        ctl = self.ctl
        return [
            (ctl.stationbook.changed, self._station_changed),
            (ctl.stationbook.recounted, self._station_changed),
            (ctl.stationbook.removed, self._station_removed),
            (ctl.stationbook.cleared, self._stations_cleared),
            (ctl.radio_changed, self._radio_changed),
            (ctl.radios.claims.changed, self._radios_changed),
            (ctl.prefbook.path_changed, self._path_changed),
            (ctl.radio_packet, self._packet),
            (ctl.internet_packet, self._packet),
            (ctl.config_changed, self._config_changed),
            (ctl.gps.changed, self._gps_changed),
            (ctl.gps.moved, self._gps_moved),
            (ctl.igate.changed, self._igate_changed),
            (ctl.igate.line_sent, self.igate_looks.told),
            (ctl.messaging.changed, self._message_changed),
            (ctl.messaging.removed, self._message_changed),
            (ctl.bulletins.changed, self._bulletin_changed),
            (ctl.bulletins.removed, self._bulletin_changed),
            (ctl.ownobjects.changed, self._own_object_changed),
            (ctl.ownobjects.removed, self._own_object_changed),
            (ctl.ownbulletins.changed, self._own_bulletin_changed),
            (ctl.ownbulletins.removed, self._own_bulletin_changed),
            (ctl.prefbook.changed, self._pref_changed),
            (ctl.keyring.changed, self._key_changed),
            (ctl.keyring.own_changed, self._own_key_changed),
            (ctl.qruask.changed, self._qru_changed),
            (ctl.generalask.changed, self._general_changed),
            (ctl.skeds.changed, self._skeds_changed),
            (ctl.chat.changed, self._chat_changed),
            (ctl.chat.lines_changed, self._chat_lines_changed),
            (ctl.chat.fresh, self._chat_fresh),
            (ctl.mapfetch.changed, self._map_changed),
            (ctl.aloha.changed, self._map_changed),
            (ctl.layers.changed, self._map_changed),
            (ctl.layers.told, self.layers.told),
            (ctl.satellites.told, self.satellites.told),
            (ctl.selfupdate.changed, self._update_changed),
            (ctl.stationalerts.fired, self._station_alert),
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
        self.scopes.disconnect()
        self.levels.disconnect()

    @staticmethod
    def _wire_scope(feed: ScopeFeed, modem: Mercury, on: bool) -> None:
        """Connect or disconnect a scope feed to its modem's rows."""
        if on:
            modem.scope_row.connect(feed.row)
            modem.scope_cleared.connect(feed.cleared)
        else:
            modem.scope_row.disconnect(feed.row)
            modem.scope_cleared.disconnect(feed.cleared)

    @staticmethod
    def _wire_level(feed: LevelFeed, modem: Leveled, on: bool) -> None:
        """Connect or disconnect a level feed to its modem's level."""
        if on:
            modem.level_now.changed.connect(feed.said)
        else:
            modem.level_now.changed.disconnect(feed.said)

    def _station_changed(self, station: Station) -> None:
        self.hub.changed("stations", station.call)
        if station.call in self.call_routes.told:
            self.hub.changed("call_routes", station.call)  # heard: its row says it now

    def _station_removed(self, call: str) -> None:
        self.hub.changed("stations", call)
        self.hub.changed("call_routes", call)

    def _stations_cleared(self) -> None:
        """Drop heard packets from the window when every station but ours was forgotten."""
        self.window.drop_heard()
        self.hub.changed("stations")
        self.hub.changed("packets")
        self.hub.changed("call_routes")

    def _radio_changed(self, id: RadioId) -> None:
        self.hub.changed("radios", str(id))

    def _radios_changed(self) -> None:
        self.hub.changed("radios")

    def _path_changed(self, call: str, radio: RadioId) -> None:
        """Update the station's row `paths`; radio 1's path is also in `station_prefs`."""
        self.hub.changed("stations", call)
        self.hub.changed("call_routes", call)

    def _packet(self, packet: Packet) -> None:
        for number in self.window.add(packet):
            self.hub.changed("packets", str(number))
        if packet.direction == "out":
            self.hub.changed("gps")  # the beacon sent is the latest of its kind
            if packet.radio_id is not None:
                self.hub.changed("radios", str(packet.radio_id))  # its beacon's last and next times
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

    def _igate_changed(self) -> None:
        self.hub.changed("igate")

    def _qru_changed(self) -> None:
        self.hub.changed("qru")

    def _general_changed(self) -> None:
        self.hub.changed("general")

    def _skeds_changed(self) -> None:
        self.hub.changed("skeds")

    def _chat_changed(self) -> None:
        self.hub.changed("chat")

    def _chat_lines_changed(self, ids: list[int]) -> None:
        for ident in ids:
            self.hub.changed("chat_lines", str(ident))

    def _chat_fresh(self, lines: list[Line]) -> None:
        """Tell every open page once, while the chat's notification is on; a page opened later is not told."""
        if self._tell is not None and self.ctl.config.messages_chat_alert:
            self._tell(ChatFreshMsg.of(lines))

    def _gps_moved(self) -> None:
        """Our row follows the GPS at once.

        Other stations' distances and bearings are resent whole now and then.
        """
        now = time.monotonic()
        if now - self._distances_at >= DISTANCES_EVERY_SEC:
            self._distances_at = now
            self.hub.changed("stations")

    def _pref_changed(self, call: str, pref: Pref | None) -> None:
        self.hub.changed("station_prefs", call)
        # its text_max follows RF only
        if self.ctl.stationbook.get(call) is not None:
            self.hub.changed("stations", call)
        self.hub.changed("call_routes", call)

    def _key_changed(self, call: str) -> None:
        self.hub.changed("station_keys", call)

    def _own_key_changed(self) -> None:
        """Resend the status, which carries our key's fingerprint."""
        if self._sent is not None:
            self._sent()

    def _station_alert(self, fired: Fired) -> None:
        """Tell every open page once; a page opened later is not told."""
        if self._tell is not None:
            self._tell(station_alert_message(fired))

    def _follow_ticks(self, config: Config) -> None:
        self.window.internet, self.window.gated, self.window.own = (
            config.igate_enabled,
            config.igate_show_gated,
            config.station_call,
        )

    def _config_changed(self, config: Config) -> None:
        keys = self._config.changed(config)
        moved = any(key in PLACE_KEYS for key in keys)
        radios = radios_in_force(config) != radios_in_force(self._config)
        self._config = config
        self.hub.changed("radios")  # settings, Enable, beacon interval
        # A removed radio releases its modem's rows; only Mercury has a scope.
        self.scopes.keep(
            {radio.id: modem for radio in self.ctl.radios.all() if isinstance(modem := radio.driver.modem, Mercury)}
        )
        self.levels.keep(
            {
                radio.id: modem
                for radio in self.ctl.radios.all()
                if isinstance(modem := radio.driver.modem, DirewolfModem)
            }
        )
        if radios:
            self.hub.changed("stations")  # the radio each message takes now, and the choices in force
            self.hub.changed("call_routes")
            self.hub.changed("own_objects")  # a removed radio left the objects' radios
            for key in on_their_way(self.ctl.messaging.records()):
                self.hub.changed("messages", key)  # the radio each goes on next
        self._follow_ticks(config)
        if "igate/enabled" in keys or "igate/show_gated" in keys:
            self.hub.changed("packets")
            moved = True  # tell the stations whole: the internet ones appear or go
            self.hub.changed("call_routes")  # a call whose row goes or comes back
        if "igate/show_gated" in keys:
            self.hub.changed("messages")
        self.hub.changed("config")
        self.hub.changed("gps")
        self.hub.changed("igate")
        # a call the server blocked is a closed board for that call only
        self.hub.changed("skeds")
        self.hub.changed("chat")
        self.hub.changed("chat_lines")  # our call decides which lines are ours
        self.hub.changed("map")  # area, zoom and whether there is a position
        if moved:
            self.hub.changed("stations")  # every row has a new distance and bearing
        if self._sent is not None:
            # The status carries the unheard-call radio, email radio, beacon interval, call and
            # place.
            self._sent()
