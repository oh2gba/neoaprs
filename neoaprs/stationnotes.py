"""What a packet says about its sender that the station book records in the station.

That is whether it does messages, its packets of the last hour, frequency, storm data and sign,
its telemetry and definitions, and whether it is an iGate. Pure code, called by the book.
"""

from collections.abc import Callable, Collection, Iterable, Mapping
from datetime import datetime

from .aprstelemetry import Telemetry, TelemetryDefinition, apply_definition, is_definition
from .bulletin import board_slot
from .device import MICE_BODY, MICE_DUMB, MICE_IDENTIFIERS
from .packet import DUMMY, IS, RF_GATED, ItemReport, Message, ObjectReport, Other, Packet, Position
from .radiotype import FM_ID, RadioId
from .message import same_call
from .reach import mark_of, pushed, reach_of
from .route import route_of, used_path
from .station import RadioPlace, Station, add_track_point

# stations whose telemetry definitions are kept (the oldest goes first)
DEFINITIONS_MAX = 500
# the token of a capabilities packet (`<IGATE,MSG_CNT=2`) that marks an iGate
IGATE = "IGATE"


def every_radio_carries_path(radio: RadioId) -> bool:
    """Return True: with no knowledge of the radios, every radio may carry a path."""
    return True


def came_back(path: tuple[str, ...], ours: Collection[str]) -> bool:
    """Return whether the path shows one of `ours` used: our copy heard back via a digipeater."""
    return any(hop.endswith("*") and any(same_call(hop[:-1], call) for call in ours) for hop in used_path(path))


def note_heard(
    station: Station,
    packet: Packet,
    route: bool = True,
    *,
    carries_path: Callable[[RadioId], bool] = every_radio_carries_path,
    ours: Collection[str] = (),
) -> None:
    """Record a received packet: counts and times per channel, and `last_heard`.

    Counted for the packet's radio (none: radio 1); with `route` also its route.
    """
    station.packets += 1
    station.last_heard = packet.heard_at
    station.hour.note(packet.heard_at)
    if packet.via == RF_GATED:
        station.hour_gated.note(packet.heard_at)
    note_route_mark(station, packet)
    if packet.via == IS:
        station.hour_is.note(packet.heard_at)
        station.heard_is, station.last_is_at = station.heard_is + 1, packet.heard_at
        return
    if came_back(packet.path, ours):
        return
    radio = FM_ID if packet.radio_id is None else packet.radio_id
    station.note_on(radio, packet.heard_at, packet.path)
    if packet.via == RF_GATED:
        station.heard_rf_gated, station.last_rf_gated_at = station.heard_rf_gated + 1, packet.heard_at
    elif packet.via == DUMMY:
        station.heard_dummy, station.last_dummy_at = station.heard_dummy + 1, packet.heard_at
    else:
        station.heard_rf, station.last_rf_at = station.heard_rf + 1, packet.heard_at
    station.last_via = packet.gate
    if route:
        station.note_route(
            radio, route_of(packet.path, packet.gate), 1, packet.heard_at, carries_path=carries_path(radio)
        )
    if (
        station.kind == "station"
        and (packet.snr is not None or packet.rssi is not None)
        and route_of(packet.path, packet.gate).direct
    ):
        station.snr, station.rssi, station.signal_at = packet.snr, packet.rssi, packet.heard_at


def note_route_mark(station: Station, packet: Packet, place: tuple[float, float] | None = None) -> None:
    """Add the packet's route to the two the station keeps for the map, with where it was.

    The place is the packet's position, else `place`, else the station's current one.
    """
    if place is None:
        place = _reported_place(packet.decoded) or (
            None if station.lat is None or station.lon is None else (station.lat, station.lon)
        )
    reach = reach_of(packet)
    if reach is not None:
        station.internet_reach = reach
    mark = mark_of(packet, *(place or (None, None)))
    if mark is not None:
        station.route_marks = pushed(station.route_marks, mark)


def _reported_place(decoded: object) -> tuple[float, float] | None:
    if isinstance(decoded, (ObjectReport, ItemReport)):
        decoded = decoded.position
    return (decoded.lat, decoded.lon) if isinstance(decoded, Position) else None


def seed_routes(stations: Mapping[str, Station], packets: Iterable[Packet]) -> None:
    """Record routes from stored packets, oldest first, for the sender and any reported object."""
    places: dict[str, tuple[float, float]] = {}
    for packet in packets:
        if packet.direction != "in":
            continue
        station = stations.get(packet.sender)
        if station is not None and not station.is_me:
            place = _reported_place(packet.decoded)
            if place is not None:
                places[station.call] = place
            note_route_mark(station, packet, places.get(station.call))
        decoded = packet.decoded
        if isinstance(decoded, (ObjectReport, ItemReport)) and decoded.alive:
            named = stations.get(decoded.name)
            if (
                named is not None
                and named.kind == ("object" if isinstance(decoded, ObjectReport) else "item")
                and not named.own
                and not named.is_me
            ):
                note_route_mark(named, packet, (decoded.position.lat, decoded.position.lon))


def note_messaging(station: Station, packet: Packet) -> None:
    """Note that a station does messages: a message or ack (no bulletin) or its position says so."""
    decoded = packet.decoded
    if isinstance(decoded, Message):
        if board_slot(decoded.addressee) is None and not is_definition(decoded.text):
            station.sent_message = True
    elif isinstance(decoded, Position):
        info = packet.inner_info
        station.position_messaging = decoded.messaging or (
            info[:1] in MICE_IDENTIFIERS and info[MICE_BODY : MICE_BODY + 1] != MICE_DUMB
        )


def note_position(station: Station, position: Position) -> None:
    """Keep extensions, locator and local data; a digipeater may send its PHG only sometimes."""
    station.extensions = position.extensions or station.extensions
    station.locator = position.locator or station.locator
    note_local(station, position)


def note_local(station: Station, position: Position) -> None:
    """Keep frequency, storm data and sign; an object or item has what its latest report says."""
    if position.frequency is not None or station.kind != "station":
        station.frequency = position.frequency
    station.storm, station.sign = position.storm, position.sign


def seed_reported(stations: Mapping[str, Station], packet: Packet) -> None:
    """Note the local data of a live object or item, if the book has it from the packet's sender."""
    decoded = packet.decoded
    if packet.direction == "in" and isinstance(decoded, (ObjectReport, ItemReport)) and decoded.alive:
        reported = stations.get(decoded.name)
        if reported is not None and not reported.own and reported.reported_by == packet.sender:
            note_local(reported, decoded.position)


def seed_hour(stations: Mapping[str, Station], packets: Iterable[Packet]) -> None:
    """Count stored packets of the last hour for the sender and any live object or item named."""
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
    elif packet.via == RF_GATED:
        station.hour_gated.note(packet.heard_at)


def expire_hours(stations: Iterable[Station], now: datetime, changed: Callable[[Station], None]) -> None:
    """Expire hour-old packets and call `changed` for each station whose count fell."""
    for station in [s for s in stations if s.hour.total and s.hour.expire(now)]:
        changed(station)


def note_gate(
    stations: Mapping[str, Station], gate: str, count: int = 1, changed: Callable[[Station], None] | None = None
) -> None:
    """Count `count` third-party packets for the iGate `gate`, if the book has it (not ours)."""
    station = stations.get(gate) if gate else None
    if station is not None and not station.is_me and count > 0:
        station.gated += count
        if changed is not None:
            changed(station)


def note_igate(station: Station, decoded: object) -> None:
    """Mark the station as an iGate if a capabilities packet holds the token IGATE."""
    if (
        isinstance(decoded, Other)
        and decoded.kind == "capabilities"
        and decoded.items is not None
        and any(token.upper() == IGATE for token in decoded.items)
    ):
        station.igate = True


def note_telemetry(
    stations: Mapping[str, Station], definitions: dict[str, TelemetryDefinition], packet: Packet
) -> Station | None:
    """Keep a telemetry report as the sender's latest, or a definition message in `definitions`.

    Return the station that gained a definition, if it is in the book.
    """
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


def note_radio_place(station: Station, packet: Packet, position: Position, replay: bool = False) -> None:
    """Keep apart the place the radio gave a station that is also heard from the internet.

    The place is copied to `Station.radio` at the first internet packet; later positions move it.
    """
    place = station.radio
    if (
        place is None
        and not replay
        and station.position_via not in (None, IS)
        and station.lat is not None
        and station.lon is not None
        and station.last_position_at is not None
        and (packet.via == IS or station.heard_is > 0)
    ):
        assert station.position_via is not None
        place = station.radio = RadioPlace(
            station.lat,
            station.lon,
            station.last_position_at,
            station.position_via,
            station.symbol_table,
            station.symbol_code,
            station.altitude_m,
            station.course_deg,
            station.speed_kmh,
            station.last_comment,
            list(station.track),
            station.extensions,
            station.storm,
            station.sign,
        )
    if packet.via == IS or (place is None and station.heard_is == 0):
        return
    track = [] if place is None else place.track
    station.radio = RadioPlace(
        position.lat,
        position.lon,
        packet.heard_at,
        packet.via,
        position.symbol_table,
        position.symbol_code,
        position.altitude_m,
        position.course_deg,
        position.speed_kmh,
        position.comment,
        track,
        position.extensions or (None if place is None else place.extensions),
        position.storm,
        position.sign,
    )
    add_track_point(track, packet.heard_at, position.lat, position.lon)


def seed_radio(stations: Mapping[str, Station], packets: Iterable[Packet]) -> None:
    """Replay stored non-internet position packets, oldest first, through `note_radio_place`."""
    for packet in packets:
        decoded = packet.decoded
        if isinstance(decoded, Position):
            name, position = packet.sender, decoded
        elif isinstance(decoded, (ObjectReport, ItemReport)) and decoded.alive:
            name, position = decoded.name, decoded.position
        else:
            continue
        station = stations.get(name)
        if (
            packet.direction == "in"
            and packet.via != IS
            and station is not None
            and not station.is_me
            and not station.own
            and station.heard_is > 0
        ):
            note_radio_place(station, packet, position, replay=True)
