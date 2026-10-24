"""What a packet says about its sender that the station book notes in the station: whether it does messages, and the packets of its last hour. Pure code; the book (stationbook.py) calls these."""
from collections.abc import Iterable, Mapping
from datetime import datetime

from .aprstelemetry import is_definition
from .bulletin import board_slot
from .device import MICE_BODY, MICE_DUMB, MICE_IDENTIFIERS, inner
from .packet import ItemReport, Message, ObjectReport, Packet, Position
from .station import Station


def note_messaging(station: Station, packet: Packet) -> None:
    """A message or an ack from the station (not a bulletin, not a definition of its own telemetry: those are not talk with a station) says it does messages; a position says what its identifier does."""
    decoded = packet.decoded
    if isinstance(decoded, Message):
        if board_slot(decoded.addressee) is None and not is_definition(decoded.text):
            station.sent_message = True
    elif isinstance(decoded, Position):
        info = inner(packet)[1]
        station.position_messaging = decoded.messaging or (info[:1] in MICE_IDENTIFIERS and info[MICE_BODY:MICE_BODY + 1] != MICE_DUMB)


def seed_hour(stations: Mapping[str, Station], packets: Iterable[Packet]) -> None:
    """Counts the packets heard in the last hour that the log kept, oldest first, for the station that sent each (and for the object or item that a live report names), as the book counts a packet it takes."""
    for packet in packets:
        if packet.direction != "in":
            continue
        station, decoded = stations.get(packet.sender), packet.decoded
        if station is not None and not station.is_me:
            station.hour.note(packet.heard_at)
        if isinstance(decoded, (ObjectReport, ItemReport)) and decoded.alive and decoded.name in stations:
            stations[decoded.name].hour.note(packet.heard_at)


def expire_hours(stations: Iterable[Station], now: datetime) -> list[Station]:
    """Lets the packets that are an hour old at `now` leave the last hour of each station; the stations whose count became smaller."""
    return [station for station in stations if station.hour.total and station.hour.expire(now)]
