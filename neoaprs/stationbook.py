"""The stations as the packets tell them: who was heard, where, when, how often, and their tracks.

A name is one entry; a transmitting station wins it over an object or item of that name, and
another station's report of an object named like ours takes it over (the spec's "Replacement").
"""

from collections.abc import Callable, Collection, Iterable, Mapping
from datetime import datetime

from . import ax25
from .aprstelemetry import TelemetryDefinition
from .aprsthirdparty import header_of
from .aprsweather import Weather
from .clock import Clock, utcnow
from .device import packet_device
from .geo import bearing_deg, distance_km
from .ownobject import OwnObject
from .packet import IS, ItemReport, ObjectReport, Other, Packet, Position, Status
from .radiospec import FM_ID, RadioId, RadioSpec
from .radiotype import RadioTypeError
from .route import route_of
from .signal import Signal
from .station import Station, add_track_point
from .stationnotes import (
    came_back,
    every_radio_carries_path,
    expire_hours,
    note_gate,
    note_heard,
    note_igate,
    note_messaging,
    note_position,
    note_radio_place,
    note_telemetry,
    seed_hour,
    seed_radio,
    seed_reported,
    seed_routes,
)

# Packets read at start: the latest, and as many of those not from the internet, for routes.
ROUTES_SEEN = 1000
# Packets read at start for telemetry, definitions, locators, data extensions and the device.
DETAILS_SEEN = 2000

# (sender, path, iGate or "", count, latest heard, the one before it heard, radio)
RouteGroup = tuple[str, tuple[str, ...], str, int, datetime, datetime | None, RadioId | None]
# The same without the radio, from a packet log that predates routes by radio (all radio 1's).
OldRouteGroup = tuple[str, tuple[str, ...], str, int, datetime, datetime | None]


def carries_path(specs: Iterable[RadioSpec], radio: RadioId) -> bool:
    """Return whether our frames on the radio may carry a path (its type's `allowed.paths`).

    An unknown radio counts as one that may; an unknown type as one that may not.
    """
    spec = next((s for s in specs if s.id == radio), None)
    if spec is None:
        return True
    try:
        return spec.rtype.allowed.paths
    except RadioTypeError:
        return False


def route_groups(rows: Iterable[tuple[str, str, bytes, datetime, RadioId | None]]) -> list[RouteGroup]:
    """Group stored (source, path, frame, heard time, radio) rows by sender, path, iGate and radio.

    Groups are ordered by their latest packet. A third-party packet counts for the inner sender.
    """
    groups: dict[tuple[str, tuple[str, ...], str, RadioId | None], tuple[int, datetime, datetime | None]] = {}
    for source, path_text, raw, at, radio in rows:
        try:
            opened = header_of(ax25.decode(raw).info)
        except ax25.Ax25Error:
            continue
        key = (
            source if opened is None else opened[0].source,
            tuple(path_text.split(",")) if path_text else (),
            "" if opened is None else source,
            radio,
        )
        packets, earlier, _ = groups.pop(key, (0, at, None))
        # re-inserting moves a group to the end: the order is that of the latest packet
        groups[key] = (packets + 1, at, earlier if packets else None)
    return [
        (sender, path, gate, packets, at, before, radio)
        for (sender, path, gate, radio), (packets, at, before) in groups.items()
    ]


class StationBook:
    def __init__(
        self,
        clock: Clock = utcnow,
        *,
        carries_path: Callable[[RadioId], bool] = every_radio_carries_path,
        own_calls: Callable[[], Collection[str]] = tuple,
    ) -> None:
        self.clock = clock
        # a packet showing one of these calls is our own copy heard back
        self._own_calls = own_calls
        self._carries_path = carries_path
        # `changed` passes the live station: read it, do not keep it
        self.changed: Signal[[Station]] = Signal("stationbook.changed")
        self.removed: Signal[[str]] = Signal("stationbook.removed")
        # a station's last hour became fewer; not saved, told to the page
        self.recounted: Signal[[Station]] = Signal("stationbook.recounted")
        # every station but ours was forgotten at once; the caller clears the database
        self.cleared: Signal[[]] = Signal("stationbook.cleared")
        self._stations: dict[str, Station] = {}
        self._me = ""
        self._me_position: tuple[float, float] | None = None
        self._definitions: dict[str, TelemetryDefinition] = {}

    def stations(self) -> list[Station]:
        return sorted(self._stations.values(), key=lambda s: (s.last_heard, s.call), reverse=True)

    def get(self, call: str) -> Station | None:
        return self._stations.get(call)

    def __len__(self) -> int:
        return len(self._stations)

    def seed(self, stations: list[Station]) -> None:
        for station in stations:
            station.is_me = station.call == self._me
            if station.has_position and station.last_position_at is not None and not station.track:
                assert station.lat is not None and station.lon is not None
                station.track.append((station.last_position_at, station.lat, station.lon))
            self._stations[station.call] = station

    def seed_deliveries(self, counts: Iterable[RouteGroup | OldRouteGroup]) -> None:
        """Load the groups of `route_groups`; none for a radio means radio 1; nothing is signalled.

        A group showing one of our own calls is our own copy heard back and is no route.
        """
        for sender, path, gate, count, at, before, *given in counts:
            radio = FM_ID if not given or given[0] is None else given[0]
            note_gate(self._stations, gate, count)
            station = self._stations.get(sender)
            if station is not None and not came_back(path, self._own_calls()):
                station.note_route(
                    radio, route_of(path, gate), count, at, before, carries_path=self._carries_path(radio)
                )
                station.seed_path(radio, path)
                station.last_via = gate

    def seed_tracks(self, positions: Iterable[tuple[str, datetime, float, float]]) -> None:
        """Load tracks from stored (station, when, lat, lon) positions, oldest first; no signal.

        Points join by the live rule (add_track_point). Our own station is skipped.
        """
        started: set[str] = set()
        for call, when, lat, lon in positions:
            station = self._stations.get(call)
            if station is None or station.is_me or station.own:
                continue
            if call not in started:
                started.add(call)
                station.track.clear()
            add_track_point(station.track, when, lat, lon)

    def seed_weather(self, latest: Mapping[str, tuple[datetime, Weather]]) -> None:
        """Load the newest weather observation per station; unknown stations are skipped."""
        for call, (at, weather) in latest.items():
            station = self._stations.get(call)
            if station is not None:
                station.weather, station.weather_at = weather, at

    def seed_details(self, packets: Iterable[Packet]) -> None:
        """Load what the stored packets (newest first) say beyond the station cache.

        Telemetry, locator, extensions, frequency and device; definitions read oldest first.
        """
        for packet in reversed(list(packets)):
            station, decoded = self._stations.get(packet.sender), packet.decoded
            seed_reported(self._stations, packet)
            if packet.direction != "in" or station is None or station.is_me:
                continue
            station.device = packet_device(packet) or station.device
            note_igate(station, decoded)
            note_telemetry(self._stations, self._definitions, packet)
            if isinstance(decoded, Position):
                note_position(station, decoded)
            elif isinstance(decoded, Status):
                station.locator, station.frequency = (
                    decoded.locator or station.locator,
                    decoded.frequency or station.frequency,
                )

    def seed_routes(self, packets: Iterable[Packet]) -> None:
        """Load each station's latest internet route and two latest different routes."""
        seed_routes(self._stations, packets)

    def seed_radio(self, packets: Iterable[Packet]) -> None:
        """Load Station.radio from non-internet position packets, oldest first."""
        seed_radio(self._stations, packets)

    def seed_recent(self, packets: Iterable[Packet]) -> None:
        seed_hour(self._stations, packets)

    def recount(self) -> None:
        """Drop packets an hour old from each station's last hour; signal `recounted` on change."""
        expire_hours(self._stations.values(), self.clock(), self.recounted.emit)

    def seed_messaging(self, packets: Iterable[Packet]) -> None:
        """Load who does messages from stored packets, oldest first (a later position wins)."""
        for packet in packets:
            station = self._stations.get(packet.sender)
            if station is not None and packet.direction == "in" and not station.is_me:
                note_messaging(station, packet)

    def telemetry_definition(self, call: str) -> TelemetryDefinition | None:
        return self._definitions.get(call)

    def forget(self, call: str) -> bool:
        """Remove a station, never our own or our objects; return whether one was removed."""
        station = self._stations.get(call)
        if station is None or station.is_me or station.own:
            return False
        del self._stations[call]
        self.removed.emit(call)
        return True

    def forget_all(self) -> int:
        """Remove every station but ours and the telemetry definitions; signal `cleared` once."""
        gone = [call for call, s in self._stations.items() if not s.is_me and not s.own]
        for call in gone:
            del self._stations[call]
        self._definitions.clear()
        self.cleared.emit()
        return len(gone)

    def prune(self, older_than: datetime) -> list[str]:
        """Remove stations not heard since `older_than`, except ours; return their calls."""
        gone = [s.call for s in self._stations.values() if s.last_heard < older_than and not s.is_me and not s.own]
        for call in gone:
            del self._stations[call]
            self.removed.emit(call)
        return gone

    def set_me(
        self,
        call: str,
        lat: float,
        lon: float,
        symbol_table: str = "",
        symbol_code: str = "",
        comment: str = "",
        *,
        course_deg: int | None = None,
        speed_kmh: float | None = None,
        altitude_m: float | None = None,
        at: datetime | None = None,
    ) -> Station:
        """Put our own station in the book as `is_me`; the settings are the truth about us."""
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
        before = (
            station.is_me,
            station.lat,
            station.lon,
            station.symbol_table,
            station.symbol_code,
            station.last_comment,
            station.course_deg,
            station.speed_kmh,
            station.altitude_m,
        )
        station.is_me, station.lat, station.lon = True, lat, lon
        station.track.clear()
        station.symbol_table, station.symbol_code, station.last_comment = symbol_table, symbol_code, comment
        station.course_deg, station.speed_kmh, station.altitude_m = course_deg, speed_kmh, altitude_m
        station.last_position_at = at or station.last_position_at or now
        if before != (True, lat, lon, symbol_table, symbol_code, comment, course_deg, speed_kmh, altitude_m):
            self.changed.emit(station)
        return station

    def clear_me(self) -> None:
        """Forget who we are (no call or position, or a new call); the old station is ordinary."""
        if self._me and self._me in self._stations:
            previous = self._stations[self._me]
            previous.is_me = False
            self.changed.emit(previous)
        self._me, self._me_position = "", None

    def own_object(self, obj: OwnObject) -> Station | None:
        """Put our object or item in the book as an `own` station, replacing what was heard.

        A killed one leaves the book.
        """
        if not obj.alive:
            self._forget_own(obj.name)
            return None
        station = self._stations.get(obj.name)
        if station is None or not station.own:
            station = self._stations[obj.name] = Station(
                obj.name, first_heard=obj.created_at, last_heard=obj.updated_at, kind=obj.kind, own=True
            )
        station.reported_by, station.packets = self._me, obj.sent
        station.last_heard, station.last_position_at = obj.last_sent_at or obj.updated_at, obj.updated_at
        station.symbol_table, station.symbol_code, station.lat, station.lon = (
            obj.symbol_table,
            obj.symbol_code,
            obj.lat,
            obj.lon,
        )
        station.course_deg, station.speed_kmh, station.last_comment, station.own_path = (
            obj.course_deg,
            obj.speed_kmh,
            obj.comment,
            obj.path_calls or (),
        )
        self.changed.emit(station)
        return station

    def forget_own(self, obj: OwnObject) -> None:
        """Remove our object (killed or taken over) unless another station has taken its name."""
        self._forget_own(obj.name)

    def _forget_own(self, name: str) -> None:
        station = self._stations.get(name)
        if station is not None and station.own:
            del self._stations[name]
            self.removed.emit(name)

    @property
    def me(self) -> Station | None:
        return self._stations.get(self._me)

    @property
    def me_position(self) -> tuple[float, float] | None:
        return self._me_position

    def distance_km(self, station: Station) -> float | None:
        if self._me_position is None or station.lat is None or station.lon is None:
            return None
        return distance_km(*self._me_position, station.lat, station.lon)

    def bearing_deg(self, station: Station) -> float | None:
        if self._me_position is None or station.lat is None or station.lon is None:
            return None
        return bearing_deg(*self._me_position, station.lat, station.lon)

    def take(self, packet: Packet) -> Station | None:
        """Apply a received packet; return the sender or the object it names, or None."""
        if packet.direction != "in":
            return None
        if packet.sender == self._me:
            # Our own call over the internet does not prove the radio was heard.
            return None if packet.via == IS else self._heard_ourselves(packet)
        if (held := self._stations.get(packet.sender)) is not None and held.own:
            # A station named like one of our objects does not take the entry.
            return None
        sender = self._heard(packet.sender, packet)
        sender.device = packet_device(packet) or sender.device
        about: Station | None = sender
        decoded = packet.decoded
        note_messaging(sender, packet)
        note_igate(sender, decoded)
        note_gate(self._stations, packet.gate, 1, self.changed.emit)
        if isinstance(decoded, Position):
            self._place(sender, decoded, packet)
        elif isinstance(decoded, Status):
            sender.last_status = decoded.text
            sender.locator, sender.frequency = decoded.locator or sender.locator, decoded.frequency or sender.frequency
        elif isinstance(decoded, Other) and decoded.weather is not None:
            sender.weather, sender.weather_at = decoded.weather, packet.heard_at
        defined = note_telemetry(self._stations, self._definitions, packet)
        if defined is not None and defined is not sender:
            self.changed.emit(defined)
        self.changed.emit(sender)
        if isinstance(decoded, (ObjectReport, ItemReport)):
            about = self._named(packet, decoded)
        return about

    def _heard_ourselves(self, packet: Packet) -> Station | None:
        """Handle our own call heard on the air: only the last-heard time changes."""
        station = self._stations.get(self._me)
        if station is None:
            return None
        station.last_heard = packet.heard_at
        self.changed.emit(station)
        return station

    def _heard(self, call: str, packet: Packet) -> Station:
        station = self._stations.get(call)
        # An object heard under this call before gives way to the station that transmits under it.
        if station is None or station.kind != "station":
            station = self._stations[call] = Station(call, first_heard=packet.heard_at, last_heard=packet.heard_at)
        note_heard(station, packet, carries_path=self._carries_path, ours=self._own_calls())
        return station

    def _place(self, station: Station, position: Position, packet: Packet) -> None:
        when = packet.heard_at
        note_radio_place(station, packet, position)
        station.position_via = packet.via
        station.symbol_table, station.symbol_code = position.symbol_table, position.symbol_code
        station.lat, station.lon = position.lat, position.lon
        station.altitude_m, station.course_deg, station.speed_kmh = (
            position.altitude_m,
            position.course_deg,
            position.speed_kmh,
        )
        station.last_comment = position.comment
        note_position(station, position)
        station.last_position_at = when
        if position.weather is not None:
            station.weather, station.weather_at = position.weather, when
        add_track_point(station.track, when, position.lat, position.lon)

    def _named(self, packet: Packet, report: ObjectReport | ItemReport) -> Station | None:
        """Return the station an object or item report is about; None for a kill or a taken name."""
        station = self._stations.get(report.name)
        if station is not None and (station.is_me or station.kind == "station"):
            return None
        if not report.alive:
            # Another station's kill does not end an object of ours.
            if station is not None and not station.own:
                del self._stations[report.name]
                self.removed.emit(report.name)
            return None
        kind = "object" if isinstance(report, ObjectReport) else "item"
        # An object of ours that another station reports is theirs now.
        if station is None or station.kind != kind or station.own:
            station = self._stations[report.name] = Station(
                report.name, first_heard=packet.heard_at, last_heard=packet.heard_at, kind=kind
            )
        station.reported_by = packet.sender
        note_heard(station, packet, route=False)
        self._place(station, report.position, packet)
        self.changed.emit(station)
        return station
