"""The stations as the packets tell them: who was heard, where, when last, how often, and the track of the positions they sent. Pure code: the packet log (packetlog.py) keeps the book between runs
and the composition root (wiring.py) connects the two.

A packet applies to the book in `take`. The sender of every packet heard counts as heard (a message or a telemetry packet gives no position, but the station is on the air), and the route the packet came by, direct or through which
digipeaters (route.py), is counted for the sender. A position sets where the sender is; an object or an item is a station of its own, named by the object and marked with who reported it, and removed again when the report says it was killed. A packet from our own call, heard on the air (our beacon repeated or echoed), moves only the time we were last heard: where we are is the settings'."""
from collections.abc import Collection, Iterable, Mapping
from datetime import datetime

from .aprstelemetry import Telemetry, TelemetryDefinition, apply_definition
from .aprsweather import Weather
from .clock import Clock, utcnow
from .device import packet_device
from .geo import bearing_deg, distance_km
from .ownobject import OwnObject
from .packet import ItemReport, Message, ObjectReport, Other, Packet, Position, Status
from .route import route_of
from .signal import Signal
from .station import Station
from .stationnotes import expire_hours, note_messaging, seed_hour

TRACK_MAX = 50                      # positions kept per station
TRACK_MOVED_M = 10.0                # a new position goes on the track when the station moved more than this ...
TRACK_EVERY_SEC = 300.0             # ... or when this long has passed since the last one on it
DEFINITIONS_MAX = 500               # stations whose telemetry definitions are kept (the oldest goes first)
DETAILS_SEEN = 2000                 # the packets that telemetry, its definitions, locators, data extensions and the device are read from at the start


class StationBook:
    def __init__(self, clock: Clock = utcnow) -> None:
        self.clock = clock
        self.changed: Signal[[Station]] = Signal("stationbook.changed")       # a station was added or changed (the live object: read it, do not keep it)
        self.removed: Signal[[str]] = Signal("stationbook.removed")           # its call
        self.recounted: Signal[[Station]] = Signal("stationbook.recounted")   # the packets of its last hour became fewer (minute by minute, as old ones leave the hour): not saved, told to the page
        self._stations: dict[str, Station] = {}
        self._me = ""
        self._me_position: tuple[float, float] | None = None
        self._definitions: dict[str, TelemetryDefinition] = {}

    # ---- what is in it
    def stations(self) -> list[Station]:
        """The latest heard first."""
        return sorted(self._stations.values(), key=lambda s: (s.last_heard, s.call), reverse=True)

    def get(self, call: str) -> Station | None:
        return self._stations.get(call)

    def __len__(self) -> int:
        return len(self._stations)

    def seed(self, stations: list[Station]) -> None:
        """The stations a run starts with (the rows the database kept); nothing is signalled. Each one with a position has it as the one point of its track."""
        for station in stations:
            station.is_me = station.call == self._me
            if station.has_position and station.last_position_at is not None and not station.track:
                assert station.lat is not None and station.lon is not None
                station.track.append((station.last_position_at, station.lat, station.lon))
            self._stations[station.call] = station

    def seed_deliveries(self, counts: Iterable[tuple[str, tuple[str, ...], str, int, datetime, datetime | None]]) -> None:
        """The routes of the packets the database kept, as (sender, path, iGate or "", how many, when the latest of them was heard, when the one before it was) with the group of the oldest latest packet first; a sender that is not
        in the book is left out. The latest group of a station says how its latest packet came. Nothing is signalled."""
        for sender, path, gate, count, at, before in counts:
            station = self._stations.get(sender)
            if station is not None:
                station.deliveries.note(route_of(path, gate), count, at, before)
                station.last_path, station.last_via = path, gate

    def seed_tracks(self, positions: Iterable[tuple[str, datetime, float, float]]) -> None:
        """The tracks of the positions the database kept, as (station, when, lat, lon) oldest first (an object's own name for an object or an item): each station named replaces the one point it was seeded
        with by the track the positions make by the rule of a live one (a point joins when the station moved more than TRACK_MOVED_M or TRACK_EVERY_SEC passed), the latest TRACK_MAX of them. Our own station
        and a station not in the book are left out. Nothing is signalled."""
        started: set[str] = set()
        for call, when, lat, lon in positions:
            station = self._stations.get(call)
            if station is None or station.is_me or station.own:
                continue
            if call not in started:
                started.add(call)
                station.track.clear()
            self._track(station, when, lat, lon)

    def seed_weather(self, latest: Mapping[str, tuple[datetime, Weather]]) -> None:
        """The newest observation of each station the weather log kept, as (when, what); a station that is not in the book is left out. Nothing is signalled."""
        for call, (at, weather) in latest.items():
            station = self._stations.get(call)
            if station is not None:
                station.weather, station.weather_at = weather, at

    def seed_details(self, packets: Iterable[Packet]) -> None:
        """What the latest packets kept say that the station cache does not keep, newest first as the log gives them: the latest telemetry report, the locator, the data extensions and the device of each station, and
        the telemetry definitions (read oldest first, so that a later one wins). A station that is not in the book is left out. Nothing is signalled."""
        for packet in reversed(list(packets)):
            station, decoded = self._stations.get(packet.sender), packet.decoded
            if packet.direction != "in" or station is None or station.is_me:
                continue
            station.device = packet_device(packet) or station.device
            self._note_telemetry(packet)
            if isinstance(decoded, Position):
                station.extensions, station.locator = decoded.extensions, decoded.locator or station.locator
            elif isinstance(decoded, Status):
                station.locator = decoded.locator or station.locator

    def seed_recent(self, packets: Iterable[Packet]) -> None:
        """The packets of the last hour that the log kept, oldest first, counted for the stations that sent them. Nothing is signalled."""
        seed_hour(self._stations, packets)

    def recount(self) -> list[Station]:
        """Lets the packets that are an hour old now leave the last hour of each station; the stations whose count became smaller are signalled as `recounted` (and returned)."""
        fewer = expire_hours(self._stations.values(), self.clock())
        for station in fewer:
            self.recounted.emit(station)
        return fewer

    def seed_messaging(self, packets: Iterable[Packet]) -> None:
        """What the packets kept say about who does messages, oldest first (a later position wins): a message or an ack from a station, the flag of a station's position. A station that is not in the book is
        left out. Nothing is signalled."""
        for packet in packets:
            station = self._stations.get(packet.sender)
            if station is not None and packet.direction == "in" and not station.is_me:
                note_messaging(station, packet)

    def telemetry_definition(self, call: str) -> TelemetryDefinition | None:
        """What the definition messages of the station said, None when it sent none."""
        return self._definitions.get(call)

    def forget(self, call: str) -> bool:
        """Removes a station (not our own, and not an object of ours: it is killed); whether there was one."""
        station = self._stations.get(call)
        if station is None or station.is_me or station.own:
            return False
        del self._stations[call]
        self.removed.emit(call)
        return True

    def prune(self, older_than: datetime, keep: Collection[str] = ()) -> list[str]:
        """Removes the stations not heard since `older_than` (ours stays, our objects too, and so do those named in `keep`); their calls."""
        gone = [s.call for s in self._stations.values() if s.last_heard < older_than and not s.is_me and not s.own and s.call not in keep]
        for call in gone:
            del self._stations[call]
            self.removed.emit(call)
        return gone

    # ---- us
    def set_me(self, call: str, lat: float, lon: float, symbol_table: str = "", symbol_code: str = "", comment: str = "") -> Station:
        """Where we are, what we are called and how we look: our own station is in the book from now on, marked `is_me`, with the position, the symbol and the comment of the settings (the
        settings are the truth about us, whatever a packet says). The station of a call we had before is an ordinary one again."""
        if self._me != call:
            self.clear_me()
        self._me, self._me_position = call, (lat, lon)
        for mine in self._stations.values():
            if mine.own:
                mine.reported_by = call
        now = self.clock()
        station = self._stations.get(call)
        if station is None:
            station = self._stations[call] = Station(call, first_heard=now, last_heard=now)
        before = (station.is_me, station.lat, station.lon, station.symbol_table, station.symbol_code, station.last_comment)
        station.is_me, station.lat, station.lon = True, lat, lon
        station.track.clear()                                      # (we have no track: the map shows where we are)
        station.symbol_table, station.symbol_code, station.last_comment = symbol_table, symbol_code, comment
        if station.last_position_at is None:
            station.last_position_at = now
        if before != (True, lat, lon, symbol_table, symbol_code, comment):
            self.changed.emit(station)
        return station

    def clear_me(self) -> None:
        """We are nobody yet (no call or no position in the settings), or somebody else now: the station of the call we had is an ordinary one again, and there is no own station."""
        if self._me and self._me in self._stations:
            previous = self._stations[self._me]
            previous.is_me = False
            self.changed.emit(previous)
        self._me, self._me_position = "", None

    def own_object(self, obj: OwnObject) -> Station | None:
        """Our object or item as a station of its own, marked `own`, reported by us, at the place and with the symbol, comment, course and speed we send; what was heard under its name before is replaced. A
        killed one is out of the book. Not signalled to the cache: it is not kept there."""
        if not obj.alive:
            self._forget_own(obj.name)
            return None
        station = self._stations.get(obj.name)
        if station is None or not station.own:
            station = self._stations[obj.name] = Station(obj.name, first_heard=obj.created_at, last_heard=obj.updated_at, kind=obj.kind, own=True)
        station.reported_by, station.packets = self._me, obj.sent
        station.last_heard, station.last_position_at = obj.last_sent_at or obj.updated_at, obj.updated_at
        station.symbol_table, station.symbol_code, station.lat, station.lon = obj.symbol_table, obj.symbol_code, obj.lat, obj.lon
        station.course_deg, station.speed_kmh, station.last_comment, station.last_path = obj.course_deg, obj.speed_kmh, obj.comment, obj.path_calls or ()
        self.changed.emit(station)
        return station

    def forget_own(self, obj: OwnObject) -> None:
        """Our object is gone (killed and sent as that, or taken over): it leaves the book, unless another station has taken its name."""
        self._forget_own(obj.name)

    def _forget_own(self, name: str) -> None:
        station = self._stations.get(name)
        if station is not None and station.own:
            del self._stations[name]
            self.removed.emit(name)

    @property
    def me(self) -> Station | None:
        return self._stations.get(self._me)

    def distance_km(self, station: Station) -> float | None:
        """From our position to the station's; None while either is not known."""
        if self._me_position is None or station.lat is None or station.lon is None:
            return None
        return distance_km(*self._me_position, station.lat, station.lon)

    def bearing_deg(self, station: Station) -> float | None:
        """The direction from our position to the station's, degrees from north; None while either is not known."""
        if self._me_position is None or station.lat is None or station.lon is None:
            return None
        return bearing_deg(*self._me_position, station.lat, station.lon)

    # ---- packets
    def take(self, packet: Packet) -> Station | None:
        """Applies a packet heard on the air (the ones we sent are not heard). Returns the station it is about: the sender's, or the object's or item's own; None for a packet that is not
        taken and for an object that was killed."""
        if packet.direction != "in":
            return None
        if packet.sender == self._me:
            return self._heard_ourselves(packet)
        sender = self._heard(packet.sender, packet)
        sender.device = packet_device(packet) or sender.device
        about: Station | None = sender
        decoded = packet.decoded
        note_messaging(sender, packet)
        if isinstance(decoded, Position):
            self._place(sender, decoded, packet.heard_at)
        elif isinstance(decoded, Status):
            sender.last_status = decoded.text
            sender.locator = decoded.locator or sender.locator
        elif isinstance(decoded, Other) and decoded.weather is not None:
            sender.weather, sender.weather_at = decoded.weather, packet.heard_at
        defined = self._note_telemetry(packet)
        if defined is not None and defined is not sender:
            self.changed.emit(defined)
        self.changed.emit(sender)
        if isinstance(decoded, (ObjectReport, ItemReport)):
            about = self._named(packet, decoded)
        return about

    def _note_telemetry(self, packet: Packet) -> Station | None:
        """Keeps a telemetry report (or the base-91 telemetry in the comment of a position) as its sender's latest, or a definition message as its addressee's; returns the station that gained a definition (to be signalled), if it is in the book."""
        decoded = packet.decoded
        report = decoded.telemetry if isinstance(decoded, Position) else decoded
        if isinstance(report, Telemetry):
            station = self._stations.get(packet.sender)
            if station is not None:
                station.telemetry, station.telemetry_at = report, packet.heard_at
            return None
        if not isinstance(decoded, Message):
            return None
        updated = apply_definition(self._definitions.get(decoded.addressee, TelemetryDefinition()), decoded.text)
        if updated is None:
            return None
        self._definitions.pop(decoded.addressee, None)
        self._definitions[decoded.addressee] = updated
        while len(self._definitions) > DEFINITIONS_MAX:
            del self._definitions[next(iter(self._definitions))]
        return self._stations.get(decoded.addressee)

    def _heard_ourselves(self, packet: Packet) -> Station | None:
        """A packet with our call as its source, heard on the air (our beacon repeated by a digipeater, or echoed by the TNC): proof that we are heard, nothing more. Where we are, how we look
        and what we say come from the settings, so only the time we were last heard changes."""
        station = self._stations.get(self._me)
        if station is None:
            return None
        station.last_heard = packet.heard_at
        self.changed.emit(station)
        return station

    def _heard(self, call: str, packet: Packet) -> Station:
        station = self._stations.get(call)
        if station is None:
            station = self._stations[call] = Station(call, first_heard=packet.heard_at, last_heard=packet.heard_at, is_me=call == self._me)
        station.packets += 1
        station.last_heard = packet.heard_at
        station.last_path, station.last_via = packet.path, packet.via
        station.deliveries.note(route_of(packet.path, packet.via), 1, packet.heard_at)
        station.hour.note(packet.heard_at)
        return station

    def _place(self, station: Station, position: Position, when: datetime) -> None:
        station.symbol_table, station.symbol_code = position.symbol_table, position.symbol_code
        station.lat, station.lon = position.lat, position.lon
        station.altitude_m, station.course_deg, station.speed_kmh = position.altitude_m, position.course_deg, position.speed_kmh
        station.last_comment = position.comment
        station.extensions = position.extensions
        station.locator = position.locator or station.locator
        station.last_position_at = when
        if position.weather is not None:
            station.weather, station.weather_at = position.weather, when
        self._track(station, when, position.lat, position.lon)

    @staticmethod
    def _track(station: Station, when: datetime, lat: float, lon: float) -> None:
        if station.track:
            last_time, last_lat, last_lon = station.track[-1]
            if distance_km(last_lat, last_lon, lat, lon) * 1000.0 <= TRACK_MOVED_M and (when - last_time).total_seconds() < TRACK_EVERY_SEC:
                return
        station.track.append((when, lat, lon))
        del station.track[:-TRACK_MAX]

    def _named(self, packet: Packet, report: ObjectReport | ItemReport) -> Station | None:
        """The station an object or item report is about."""
        station = self._stations.get(report.name)
        if not report.alive:
            if station is not None and not station.own:         # (another station's kill does not end an object of ours)
                del self._stations[report.name]
                self.removed.emit(report.name)
            return None
        kind = "object" if isinstance(report, ObjectReport) else "item"
        if station is None or station.kind != kind or station.own:                   # (an object of ours that another station reports is theirs now)
            station = self._stations[report.name] = Station(report.name, first_heard=packet.heard_at, last_heard=packet.heard_at, kind=kind)
        station.reported_by = packet.sender
        station.packets += 1
        station.hour.note(packet.heard_at)
        station.last_heard = packet.heard_at
        station.last_path, station.last_via = packet.path, packet.via
        self._place(station, report.position, packet.heard_at)
        self.changed.emit(station)
        return station
