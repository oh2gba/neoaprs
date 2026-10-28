"""The packet log and the station cache: every packet heard or sent is kept, and the stations of the station book are kept beside them so that a start does not begin with an empty map.

Like the message log it runs on the database thread (db.py) and says no instead of raising when the database is not open (dblog.py). `append` and the station writes are appends that nobody waits
for (the hot path: a packet must never wait for the disk); the reads are awaited. The statements are packetsql.py's, the rows of a packet packetcodec.py's."""
import logging
from datetime import datetime

from . import ax25
from .aprsthirdparty import header_of
from .clock import Clock, days, utcnow
from .db import Db
from .dblog import DbLog
from .packet import ItemReport, ObjectReport, Packet, Position, via_of
from .packetcodec import PacketRow, packet_of, packet_row, parse_stamp, stamp
from .packetsql import (Row, all_stations, count_packets, delete_heard, delete_station, heard_by_hour, heard_routes, heard_times, insert_packet, message_packets, packets_since, position_packets, prune_packets_before, radio_position_packets,
                        recent_packets, upsert_station, window_packets)
from .station import Station

log = logging.getLogger("neoaprs.packetlog")

DELIVERIES_SEEN = 2000                   # the packets the station book counts the routes of at its start
TRACKS_SEEN = 5000                       # the position packets the station book makes the tracks from at its start


def station_row(station: Station) -> Row:
    """The columns of the station table, in order (the track and `is_me` are not kept)."""
    return (station.call, station.kind, station.reported_by, station.symbol_table, station.symbol_code, station.lat, station.lon, station.altitude_m, station.course_deg,
            station.speed_kmh, stamp(station.first_heard), stamp(station.last_heard), None if station.last_position_at is None else stamp(station.last_position_at),
            station.last_status, station.last_comment, station.packets, ",".join(station.last_path), station.heard_rf, station.heard_rf_gated, station.heard_is,
            _stamped(station.last_rf_at), _stamped(station.last_rf_gated_at), _stamped(station.last_is_at), station.position_via, station.heard_dummy, _stamped(station.last_dummy_at))


def _stamped(at: datetime | None) -> str | None:
    return None if at is None else stamp(at)


def _parsed(text: object) -> datetime | None:
    return None if text is None else parse_stamp(str(text))


def station_of(row: Row) -> Station:
    """The station from its row. Raises ValueError (or TypeError) for a row this program did not write."""
    (call, kind, reported_by, table, code, lat, lon, altitude, course, speed, first, last, position_at, status, comment, packets, path, heard_rf, heard_rf_gated, heard_is, rf_at, gated_at, is_at, position_via, heard_dummy, dummy_at) = row
    return Station(str(call), first_heard=parse_stamp(str(first)), last_heard=parse_stamp(str(last)), kind=str(kind), reported_by=str(reported_by), symbol_table=str(table),
                   symbol_code=str(code), lat=None if lat is None else float(lat), lon=None if lon is None else float(lon), altitude_m=None if altitude is None else float(altitude),
                   course_deg=None if course is None else int(course), speed_kmh=None if speed is None else float(speed),
                   last_position_at=None if position_at is None else parse_stamp(str(position_at)), last_status=str(status), last_comment=str(comment),
                   packets=int(packets), last_path=tuple(str(path).split(",")) if path else (), heard_rf=int(heard_rf), heard_rf_gated=int(heard_rf_gated), heard_is=int(heard_is),
                   last_rf_at=_parsed(rf_at), last_rf_gated_at=_parsed(gated_at), last_is_at=_parsed(is_at), position_via=None if position_via is None else via_of(str(position_via)), heard_dummy=int(heard_dummy), last_dummy_at=_parsed(dummy_at))


class PacketLog(DbLog):
    def __init__(self, db: Db | None = None, clock: Clock = utcnow) -> None:
        super().__init__(db, clock, log, "the packet log could not be read")

    # ---- appends: nobody waits
    def append(self, packet: Packet) -> bool:
        """Keeps a packet, heard or sent; False when it could not be queued."""
        row = packet_row(packet)
        return self._append(lambda conn: insert_packet(conn, row))

    def save_station(self, station: Station) -> bool:
        """Keeps the station as it is now (the row is made at once: the station goes on changing). An object of ours is not a station of the cache (ownlog.py keeps it); False for that."""
        if station.own:
            return False
        row = station_row(station)
        return self._append(lambda conn: upsert_station(conn, row))

    def delete_station(self, call: str) -> bool:
        return self._append(lambda conn: delete_station(conn, call))

    # ---- reads
    def _packets(self, rows: list[Row]) -> list[Packet]:
        return self._decoded(rows, lambda row: packet_of(PacketRow(*row)), "packet")

    async def recent(self, count: int = 100) -> list[Packet]:
        """The latest `count` packets, the newest first."""
        rows: list[Row] = await self._read(lambda conn: recent_packets(conn, count), [])
        return self._packets(rows)

    async def window(self, count: int) -> list[Packet]:
        """The latest `count` packets and the latest `count` that were not from the internet, together, the newest first: what the window of the page's Packets tab is made of."""
        rows: list[Row] = await self._read(lambda conn: window_packets(conn, count), [])
        return self._packets(rows)

    async def since(self, when: datetime) -> list[Packet]:
        """The packets heard at or after the time, the oldest first."""
        text = stamp(when)
        rows: list[Row] = await self._read(lambda conn: packets_since(conn, text), [])
        return self._packets(rows)

    async def heard_since(self, call: str, when: datetime) -> list[datetime]:
        """When the packets from the call were heard at or after the time, the oldest first."""
        text = stamp(when)
        rows: list[str] = await self._read(lambda conn: heard_times(conn, call, text), [])
        return [parse_stamp(row) for row in rows]

    async def heard_by_hour(self, since: datetime, source: str | None = None) -> dict[datetime, int]:
        """How many packets were heard (not sent by us) in each hour of the clock at or after `since`, all of them or those whose source is `source` (one station's), by the top of the hour (UTC); hours with
        none are not in it."""
        text = stamp(since)
        rows: list[tuple[str, int]] = await self._read(lambda conn: heard_by_hour(conn, text, source), [])
        return {parse_stamp(hour + ":00:00.000000Z"): count for hour, count in rows}

    async def deliveries(self, count: int = DELIVERIES_SEEN) -> list[tuple[str, tuple[str, ...], str, int, datetime, datetime | None]]:
        """(sender, path, iGate or "", how many, when the latest was heard, when the one before it was) over the latest `count` packets heard, the group whose latest packet is the oldest first: how the
        stations' packets reached us, for the station book to start with. A third-party packet is the sender inside it, with the iGate that put it on the air."""
        rows: list[Row] = await self._read(lambda conn: heard_routes(conn, count), [])
        groups: dict[tuple[str, tuple[str, ...], str], tuple[int, datetime, datetime | None]] = {}
        for source, path_text, raw, heard_at in rows:
            at = parse_stamp(str(heard_at))
            try:
                opened = header_of(ax25.decode(bytes(raw)).info)
            except ax25.Ax25Error:
                continue
            key = (str(source) if opened is None else opened[0].source, tuple(str(path_text).split(",")) if path_text else (), "" if opened is None else str(source))
            packets, earlier, _ = groups.pop(key, (0, at, None))
            groups[key] = (packets + 1, at, earlier if packets else None)       # (a group moves to the end each time: the order is that of the latest packet)
        return [(sender, path, gate, packets, at, before) for (sender, path, gate), (packets, at, before) in groups.items()]

    async def positions(self, keep_days: int, count: int = TRACKS_SEEN) -> list[tuple[str, datetime, float, float]]:
        """(station, when, lat, lon) of the latest `count` positions heard within `keep_days` days, the oldest first: the station is the sender (the one inside a third-party packet) or the name of a live
        object or item. What the station book makes the tracks from at its start."""
        since = stamp(self.clock() - days(keep_days))
        rows: list[Row] = await self._read(lambda conn: position_packets(conn, since, count), [])
        found: list[tuple[str, datetime, float, float]] = []
        for packet in self._packets(rows):
            d = packet.decoded
            if isinstance(d, Position):
                found.append((packet.sender, packet.heard_at, d.lat, d.lon))
            elif isinstance(d, (ObjectReport, ItemReport)) and d.alive:
                found.append((d.name, packet.heard_at, d.position.lat, d.position.lon))
        return found

    async def radio_positions(self, keep_days: int, count: int = TRACKS_SEEN) -> list[Packet]:
        """The latest `count` packets heard within `keep_days` days that carry a position and were not from the internet, the oldest first: the station book makes the radio's side of the stations that were heard from the internet from them."""
        since = stamp(self.clock() - days(keep_days))
        rows: list[Row] = await self._read(lambda conn: radio_position_packets(conn, since, count), [])
        return self._packets(rows)

    async def messaging_evidence(self, keep_days: int, count: int = TRACKS_SEEN) -> list[Packet]:
        """The packets that say who does messages, for the station book to start with: the latest `count` messages heard, then the latest `count` positions heard within `keep_days` days (each part oldest first)."""
        since = stamp(self.clock() - days(keep_days))
        messages: list[Row] = await self._read(lambda conn: message_packets(conn, count), [])
        positions: list[Row] = await self._read(lambda conn: position_packets(conn, since, count), [])
        return [*self._packets(messages), *self._packets(positions)]

    async def count(self) -> int:
        return await self._read(count_packets, 0)

    async def stations(self) -> list[Station]:
        """The cached stations, the latest heard first: what the station book starts with."""
        rows: list[Row] = await self._read(all_stations, [])
        return self._decoded(rows, station_of, "station")

    # ---- care
    async def forget_heard(self, keep_call: str) -> int:
        """Deletes every packet that was heard (those we sent stay) and every cached station but `keep_call`, ours; how many packets. -1 when the database would not."""
        return await self._write(lambda conn: delete_heard(conn, keep_call), -1, "the heard packets could not be forgotten")

    async def prune(self, keep_days: int) -> int:
        """Deletes the packets heard more than `keep_days` days ago; how many. The stations are the station book's to prune (the cache follows through `delete_station`)."""
        cutoff = stamp(self.clock() - days(keep_days))
        return await self._write(lambda conn: prune_packets_before(conn, cutoff), 0, "the packet log could not be pruned")
