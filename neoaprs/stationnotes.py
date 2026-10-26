"""What a packet says about its sender that the station book notes in the station: whether it does messages, the packets of its last hour, the frequency, storm data and sign of a position, the telemetry it reports and defines, and
whether it is an iGate (the third-party packets it put on the air, a capabilities packet that says so). Pure code; the book (stationbook.py) calls these."""
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime

from .aprstelemetry import Telemetry, TelemetryDefinition, apply_definition, is_definition
from .bulletin import board_slot
from .device import MICE_BODY, MICE_DUMB, MICE_IDENTIFIERS, inner
from .packet import DUMMY, IS, RF_GATED, ItemReport, Message, ObjectReport, Other, Packet, Position
from .route import route_of
from .station import RadioPlace, Station, add_track_point

DEFINITIONS_MAX = 500               # stations whose telemetry definitions are kept (the oldest goes first)
IGATE = "IGATE"                     # the token of a capabilities packet (`<IGATE,MSG_CNT=2,LOC_CNT=10`) with which a station says it is an iGate


def note_heard(station: Station, packet: Packet, route: bool = True) -> None:
    """A packet of the station was received: it is counted, with the time, for the channel it came by (`heard_rf`, `heard_rf_gated`, `heard_is`, `heard_dummy` and the time of the latest of each) and in `packets`, and the station
    was last heard now. One heard on the radio (the Dummy radio's too) sets the path it came by and, with `route`, is counted for its route; one from the internet came by no route and leaves them as they were."""
    station.packets += 1
    station.last_heard = packet.heard_at
    station.hour.note(packet.heard_at)
    if packet.via == IS:
        station.hour_is.note(packet.heard_at)
        station.heard_is, station.last_is_at = station.heard_is + 1, packet.heard_at
        return
    if packet.via == RF_GATED:
        station.heard_rf_gated, station.last_rf_gated_at = station.heard_rf_gated + 1, packet.heard_at
    elif packet.via == DUMMY:
        station.heard_dummy, station.last_dummy_at = station.heard_dummy + 1, packet.heard_at
    else:
        station.heard_rf, station.last_rf_at = station.heard_rf + 1, packet.heard_at
    station.last_path, station.last_via = packet.path, packet.gate
    if route:
        station.deliveries.note(route_of(packet.path, packet.gate), 1, packet.heard_at)


def note_messaging(station: Station, packet: Packet) -> None:
    """A message or an ack from the station (not a bulletin, not a definition of its own telemetry: those are not talk with a station) says it does messages; a position says what its identifier does."""
    decoded = packet.decoded
    if isinstance(decoded, Message):
        if board_slot(decoded.addressee) is None and not is_definition(decoded.text):
            station.sent_message = True
    elif isinstance(decoded, Position):
        info = inner(packet)[1]
        station.position_messaging = decoded.messaging or (info[:1] in MICE_IDENTIFIERS and info[MICE_BODY:MICE_BODY + 1] != MICE_DUMB)


def note_position(station: Station, position: Position) -> None:
    """What a position says that the station keeps besides where it is: its data extensions, the locator of a Mic-E status text (a position without one keeps the last), and its local data."""
    station.extensions = position.extensions
    station.locator = position.locator or station.locator
    note_local(station, position)


def note_local(station: Station, position: Position) -> None:
    """The frequency, the storm data and the sign of a position: a station keeps the frequency it gave last (a beacon with none leaves it), an object or an item has what its latest report says."""
    if position.frequency is not None or station.kind != "station":
        station.frequency = position.frequency
    station.storm, station.sign = position.storm, position.sign


def seed_reported(stations: Mapping[str, Station], packet: Packet) -> None:
    """The local data of a live object or item that a packet heard reports, for the station of its name when the book has it as reported by the packet's sender (our own objects are not read from the air)."""
    decoded = packet.decoded
    if packet.direction == "in" and isinstance(decoded, (ObjectReport, ItemReport)) and decoded.alive:
        reported = stations.get(decoded.name)
        if reported is not None and not reported.own and reported.reported_by == packet.sender:
            note_local(reported, decoded.position)


def seed_hour(stations: Mapping[str, Station], packets: Iterable[Packet]) -> None:
    """Counts the packets heard in the last hour that the log kept, oldest first, for the station that sent each (and for the object or item that a live report names), as the book counts a packet it takes."""
    for packet in packets:
        if packet.direction != "in":
            continue
        station, decoded = stations.get(packet.sender), packet.decoded
        if station is not None and not station.is_me:
            _note_hour(station, packet)
        if isinstance(decoded, (ObjectReport, ItemReport)) and decoded.alive and decoded.name in stations:
            _note_hour(stations[decoded.name], packet)


def _note_hour(station: Station, packet: Packet) -> None:
    station.hour.note(packet.heard_at)
    if packet.via == IS:
        station.hour_is.note(packet.heard_at)


def expire_hours(stations: Iterable[Station], now: datetime, changed: Callable[[Station], None]) -> None:
    """Lets the packets that are an hour old at `now` leave the last hour of each station, and tells `changed` of each station whose count became smaller."""
    for station in [s for s in stations if s.hour.total and s.hour.expire(now)]:
        changed(station)


def note_gate(stations: Mapping[str, Station], gate: str, count: int = 1, changed: Callable[[Station], None] | None = None) -> None:
    """Counts `count` third-party packets for the iGate that put them on the air (`gate`, the call of the frame we heard; empty for a packet that was none) when the book has it as a station (a gate that
    is only ever heard wrapping other stations' packets is no row, and is not counted), and tells `changed` of the station. Ours is not counted: it is the settings'."""
    station = stations.get(gate) if gate else None
    if station is not None and not station.is_me and count > 0:
        station.gated += count
        if changed is not None:
            changed(station)


def note_igate(station: Station, decoded: object) -> None:
    """A capabilities packet that holds the token IGATE says the station is an iGate."""
    if isinstance(decoded, Other) and decoded.kind == "capabilities" and decoded.items is not None and any(token.upper() == IGATE for token in decoded.items):
        station.igate = True


def note_telemetry(stations: Mapping[str, Station], definitions: dict[str, TelemetryDefinition], packet: Packet) -> Station | None:
    """Keeps a telemetry report (or the base-91 telemetry in the comment of a position) as its sender's latest, or a definition message as its addressee's in `definitions` (at most DEFINITIONS_MAX stations', the
    oldest goes first); returns the station that gained a definition (to be signalled), if it is in the book."""
    decoded = packet.decoded
    report = decoded.telemetry if isinstance(decoded, Position) else decoded
    if isinstance(report, Telemetry):
        station = stations.get(packet.sender)
        if station is not None:
            station.telemetry, station.telemetry_at = report, packet.heard_at
        return None
    if not isinstance(decoded, Message):
        return None
    updated = apply_definition(definitions.get(decoded.addressee, TelemetryDefinition()), decoded.text)
    if updated is None:
        return None
    definitions.pop(decoded.addressee, None)
    definitions[decoded.addressee] = updated
    while len(definitions) > DEFINITIONS_MAX:
        del definitions[next(iter(definitions))]
    return stations.get(decoded.addressee)


def note_radio_place(station: Station, packet: Packet, position: Position) -> None:
    """A packet is about to give the station its position. A station that is heard from the internet keeps the place the radio gave it apart (`Station.radio`), so that the internet can be hidden: the first packet from the
    internet takes a copy of the place the station has (when the radio gave it), and a packet that is not from the internet moves the radio's place. A station never heard from the internet has none."""
    place = station.radio
    if packet.via == IS:
        if place is None and station.position_via not in (None, IS) and station.lat is not None and station.lon is not None and station.last_position_at is not None:
            assert station.position_via is not None
            station.radio = RadioPlace(station.lat, station.lon, station.last_position_at, station.position_via, station.symbol_table, station.symbol_code, station.altitude_m, station.course_deg,
                                       station.speed_kmh, station.last_comment, list(station.track))
        return
    if place is None and station.heard_is == 0:
        return
    track = [] if place is None else place.track
    station.radio = place = RadioPlace(position.lat, position.lon, packet.heard_at, packet.via, position.symbol_table, position.symbol_code, position.altitude_m, position.course_deg, position.speed_kmh,
                                       position.comment, track)
    add_track_point(track, packet.heard_at, position.lat, position.lon)


def seed_radio(stations: Mapping[str, Station], packets: Iterable[Packet]) -> None:
    """The position packets that were not from the internet, oldest first, noted as the book notes a packet it takes: the place the radio gave each station that has been heard from the internet."""
    for packet in packets:
        decoded = packet.decoded
        if isinstance(decoded, Position):
            name, position = packet.sender, decoded
        elif isinstance(decoded, (ObjectReport, ItemReport)) and decoded.alive:
            name, position = decoded.name, decoded.position
        else:
            continue
        station = stations.get(name)
        if packet.direction == "in" and packet.via != IS and station is not None and not station.is_me and not station.own and station.heard_is > 0:
            note_radio_place(station, packet, position)
