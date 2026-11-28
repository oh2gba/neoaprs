"""The packet log and the station cache.

Every packet and station is stored so that a start does not begin with an empty map.
Writes are queued: a packet must never wait for the disk."""

import logging
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from functools import partial
from typing import NamedTuple

from . import ax25
from .aprsthirdparty import header_of
from .clock import Clock, days, utcnow
from .db import Db
from .dberror import Connection, Row
from .dblog import DbLog
from .geo import Point, Thinning
from .packet import ItemReport, ObjectReport, Packet, Position, via_of
from .packetcodec import PacketRow, info_of, packet_of, packet_row, parse_stamp, stamp
from .packetstats import FRESH_SEC, PacketCounts
from .packetsql import (
    all_stations,
    count_packets,
    delete_heard,
    delete_station,
    heard_by_hour,
    heard_by_radio,
    heard_times,
    insert_packet,
    located_from,
    located_since,
    message_packets,
    oldest_packet,
    packets_since,
    position_packets,
    prune_packets_slice,
    radio_position_packets,
    radio_routes,
    recent_packets,
    station_positions,
    station_readings,
    station_traffic,
    upsert_station,
    window_packets,
)
from .radiospec import RadioHeard, RadioId
from .route import route_of
from .shown import Shown
from .station import Station
from .stationbook import RouteGroup, route_groups

log = logging.getLogger("neoaprs.packetlog")

DELIVERIES_SEEN = 2000  # packets whose routes the station book counts at start
TRACKS_SEEN = 5000  # position packets the station book builds tracks from
THIRD_PARTY_SEEN = 20_000  # latest packets searched for third-party ones
PRUNE_SLICE = 5_000  # packets per prune transaction; keeps the WAL small
READINGS_SEEN = 1000  # most signal readings given to a station's graph
HISTORY_READ = 1_000_000  # most position packets read for the map replay


class History(NamedTuple):
    """Thinned tracks by station for the map replay, and the time they are complete from."""

    tracks: dict[str, list[Point]]
    begins: datetime | None


def station_row(station: Station) -> Row:
    return (
        station.call,
        station.kind,
        station.reported_by,
        station.symbol_table,
        station.symbol_code,
        station.lat,
        station.lon,
        station.altitude_m,
        station.course_deg,
        station.speed_kmh,
        stamp(station.first_heard),
        stamp(station.last_heard),
        None if station.last_position_at is None else stamp(station.last_position_at),
        station.last_status,
        station.last_comment,
        station.packets,
        station.heard_rf,
        station.heard_rf_gated,
        station.heard_is,
        _stamped(station.last_rf_at),
        _stamped(station.last_rf_gated_at),
        _stamped(station.last_is_at),
        station.position_via,
        station.heard_dummy,
        _stamped(station.last_dummy_at),
        station.snr,
        station.rssi,
        _stamped(station.signal_at),
    )


def heard_rows(station: Station) -> list[Row]:
    """Return (call, radio_id, heard, last_at, last_path) per radio that heard the station."""
    return [
        (station.call, radio, heard.count, _stamped(heard.last_at), ",".join(heard.last_path))
        for radio, heard in sorted(station.heard_by.items())
        if heard.count > 0
    ]


def heard_of(row: Row) -> tuple[str, RadioId, RadioHeard]:
    """Return (call, radio, what it heard) of a row. Raise ValueError or TypeError."""
    call, radio, count, last_at, path = row
    return str(call), int(radio), RadioHeard(int(count), _parsed(last_at), tuple(str(path).split(",")) if path else ())


def _stamped(at: datetime | None) -> str | None:
    return None if at is None else stamp(at)


def _parsed(text: object) -> datetime | None:
    return None if text is None else parse_stamp(str(text))


def _number(value: object) -> float | None:
    return None if value is None else float(str(value))


def _sender(source: str, raw: bytes | None, via: str) -> str:
    """Return the station inside a third-party packet, else `source`; `raw` None if not one."""
    if raw is None:
        return source
    try:
        opened = header_of(info_of(bytes(raw), via))
    except ax25.Ax25Error:
        return source
    return source if opened is None else opened[0].source


def station_of(row: Row, *, heard: Mapping[RadioId, RadioHeard] | None = None) -> Station:
    """Return the station of a row and what each radio heard. Raise ValueError or TypeError."""
    (
        call,
        kind,
        reported_by,
        table,
        code,
        lat,
        lon,
        altitude,
        course,
        speed,
        first,
        last,
        position_at,
        status,
        comment,
        packets,
        heard_rf,
        heard_rf_gated,
        heard_is,
        rf_at,
        gated_at,
        is_at,
        position_via,
        heard_dummy,
        dummy_at,
        snr,
        rssi,
        signal_at,
    ) = row
    return Station(
        str(call),
        first_heard=parse_stamp(str(first)),
        last_heard=parse_stamp(str(last)),
        kind=str(kind),
        reported_by=str(reported_by),
        symbol_table=str(table),
        symbol_code=str(code),
        lat=None if lat is None else float(lat),
        lon=None if lon is None else float(lon),
        altitude_m=None if altitude is None else float(altitude),
        course_deg=None if course is None else int(course),
        speed_kmh=None if speed is None else float(speed),
        last_position_at=None if position_at is None else parse_stamp(str(position_at)),
        last_status=str(status),
        last_comment=str(comment),
        packets=int(packets),
        heard_rf=int(heard_rf),
        heard_rf_gated=int(heard_rf_gated),
        heard_is=int(heard_is),
        last_rf_at=_parsed(rf_at),
        last_rf_gated_at=_parsed(gated_at),
        last_is_at=_parsed(is_at),
        position_via=None if position_via is None else via_of(str(position_via)),
        heard_dummy=int(heard_dummy),
        last_dummy_at=_parsed(dummy_at),
        heard_by=dict(heard or {}),
        snr=_number(snr),
        rssi=_number(rssi),
        signal_at=_parsed(signal_at),
    )


STATION_FLUSH_SEC = 30.0  # interval between writes of changed station rows


class PacketLog(DbLog):
    def __init__(self, db: Db | None = None, clock: Clock = utcnow) -> None:
        super().__init__(db, clock, log, "the packet log could not be read")
        # stations changed since the last flush, by call
        self._dirty: dict[str, Station] = {}
        # (since, internet) -> (when counted, counts) for all stations
        self._history: dict[tuple[datetime, bool, bool], tuple[datetime, dict[datetime, int]]] = {}
        self.stats = PacketCounts(db, clock)

    def use(self, db: Db) -> None:
        super().use(db)
        self.stats.use(db)

    # ---- appends: nobody waits
    def append(self, packet: Packet) -> bool:
        row = packet_row(packet)
        return self._append(lambda conn: insert_packet(conn, row))

    def save_station(self, station: Station) -> bool:
        """Mark the station changed; its row is written at the next flush (saves SD card writes).

        Return False for our own objects and when the database is not open."""
        if station.own:
            return False
        if not self.is_open():
            self.dropped += 1
            return False
        self._dirty[station.call] = station
        return True

    def flush_stations(self) -> int:
        """Queue writes for changed stations; return how many were queued."""
        dirty, self._dirty = self._dirty, {}
        queued = 0
        for station in dirty.values():
            queued += self._append(partial(upsert_station, row=station_row(station), heard=heard_rows(station)))
        return queued

    def delete_station(self, call: str) -> bool:
        self._dirty.pop(call, None)
        return self._append(lambda conn: delete_station(conn, call))

    # ---- reads
    def _packets(self, rows: list[Row]) -> list[Packet]:
        return self._decoded(rows, lambda row: packet_of(PacketRow(*row)), "packet")

    async def recent(self, count: int = 100) -> list[Packet]:
        rows: list[Row] = await self._read(lambda conn: recent_packets(conn, count), [])
        return self._packets(rows)

    async def window(self, count: int) -> list[Packet]:
        """Return the latest `count` packets plus the latest `count` non-internet ones."""
        rows: list[Row] = await self._read(lambda conn: window_packets(conn, count), [])
        return self._packets(rows)

    async def since(self, when: datetime) -> list[Packet]:
        text = stamp(when)
        rows: list[Row] = await self._read(lambda conn: packets_since(conn, text), [])
        return self._packets(rows)

    async def heard_since(self, call: str, when: datetime) -> list[datetime]:
        """Return when packets from `call` were heard at or after `when`."""
        text = stamp(when)
        rows: list[str] = await self._read(lambda conn: heard_times(conn, call, text), [])
        return [parse_stamp(row) for row in rows]

    async def heard_by_hour(
        self, since: datetime, source: str | None = None, internet: bool = True, gated: bool = True
    ) -> dict[datetime, int]:
        """Return heard packets per UTC hour since `since`, keyed by hour start; empty hours absent.

        The all-stations count is cached for FRESH_SEC, as it scans a day of the log."""
        key = (since, internet, gated)
        now = self.clock()
        if (
            source is None
            and key in self._history
            and timedelta(0) <= now - self._history[key][0] < timedelta(seconds=FRESH_SEC)
        ):
            return dict(self._history[key][1])
        text = stamp(since)
        rows: list[tuple[str, int]] = await self._read(
            lambda conn: heard_by_hour(conn, text, source, internet, gated), []
        )
        counted = {parse_stamp(hour + ":00:00.000000Z"): count for hour, count in rows}
        if source is None:
            # drop stale entries
            self._history = {k: v for k, v in self._history.items() if now - v[0] < timedelta(seconds=FRESH_SEC)}
            self._history[key] = (now, counted)
        return dict(counted)

    async def traffic(
        self, call: str, own_call: str, count: int, internet: bool = True, gated: bool = True
    ) -> list[tuple[int, Packet]]:
        """Return (log number, packet) of the station's latest `count` packets, newest first.

        Packets it sent (also inside third-party ones) and messages sent to it under `own_call`."""
        rows: list[Row] = await self._read(
            lambda conn: station_traffic(conn, call, own_call, count, THIRD_PARTY_SEEN, internet, gated), []
        )
        found = self._decoded(rows, lambda row: (int(row[0]), packet_of(PacketRow(*row[1:]))), "packet")
        shown = Shown(internet, gated, own_call)
        return [
            (number, packet)
            for number, packet in found
            if (packet.source in (call, own_call) or packet.sender == call) and shown.packet(packet)
        ]

    async def speeds(
        self, source: str, since: datetime, internet: bool = True, gated: bool = True
    ) -> list[tuple[datetime, float]]:
        """Return (when, km/h) of each position from `source` since `since` with a speed."""
        text = stamp(since)
        rows: list[Row] = await self._read(lambda conn: station_positions(conn, source, text, internet, gated), [])
        found: list[tuple[datetime, float]] = []
        for packet in self._packets(rows):
            d = packet.decoded
            if isinstance(d, Position) and d.speed_kmh is not None:
                found.append((packet.heard_at, d.speed_kmh))
        return found

    async def readings(
        self, source: str, since: datetime, count: int = READINGS_SEEN
    ) -> list[tuple[datetime, float | None, float | None]]:
        """Return (when, SNR dB, RSSI dBm) of the latest `count` direct packets from `source`.

        Digipeated and third-party packets carry another station's signal and are left out."""
        text = stamp(since)
        rows: list[Row] = await self._read(lambda conn: station_readings(conn, source, text, count), [])
        return [
            (parse_stamp(str(at)), _number(snr), _number(rssi))
            for at, path, snr, rssi in rows
            if route_of(tuple(str(path).split(",")) if path else ()).direct
        ]

    async def deliveries(self, count: int = DELIVERIES_SEEN) -> list[RouteGroup]:
        """Return the route groups of the latest `count` radio-heard packets, oldest first.

        A third-party packet counts as its inner sender, with the iGate that put it on the air."""
        rows: list[Row] = await self._read(lambda conn: radio_routes(conn, count), [])
        return route_groups(
            (str(source), str(path), bytes(raw), parse_stamp(str(at)), None if radio is None else int(radio))
            for source, path, raw, at, radio in rows
        )

    async def positions(self, keep_days: int, count: int = TRACKS_SEEN) -> list[tuple[str, datetime, float, float]]:
        """Return (station, when, lat, lon) of the latest `count` positions within `keep_days`.

        The station is the sender or the name of a live object or item."""
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

    async def position_history(
        self,
        since: datetime,
        own_call: str,
        thinning: Callable[[], Thinning],
        count: int = HISTORY_READ,
        internet: bool = True,
        gated: bool = True,
    ) -> History:
        """Return the station tracks since `since` for the map replay, thinned as they are read.

        `begins` is the time of the first packet read, or of the oldest if all were read."""
        text = stamp(since)

        def read(conn: Connection) -> History:
            cut = located_from(conn, text, own_call, count, internet, gated)
            tracks: dict[str, Thinning] = {}
            first: str | None = None
            for heard_at, source, name, lat, lon, raw, via in located_since(conn, text, own_call, cut, internet, gated):
                first = first or str(heard_at)
                try:
                    station = str(name) if name else _sender(str(source), raw, str(via))
                    # strptime is too slow for a week of rows
                    point = (datetime.fromisoformat(str(heard_at)), float(lat), float(lon))
                except (TypeError, ValueError):
                    continue  # a row of unknown shape
                track = tracks.get(station)
                if track is None:
                    track = tracks[station] = thinning()
                track.add(point)
            begins = first if cut is not None else oldest_packet(conn)
            return History(
                {station: track.points() for station, track in tracks.items()},
                None if begins is None else parse_stamp(begins),
            )

        return await self._read(read, History({}, None))

    async def radio_positions(self, keep_days: int, count: int = TRACKS_SEEN) -> list[Packet]:
        """Return the latest `count` radio-heard position packets in `keep_days`, oldest first."""
        since = stamp(self.clock() - days(keep_days))
        rows: list[Row] = await self._read(lambda conn: radio_position_packets(conn, since, count), [])
        return self._packets(rows)

    async def messaging_evidence(self, keep_days: int, count: int = TRACKS_SEEN) -> list[Packet]:
        """Return the latest `count` messages, then the latest `count` positions in `keep_days`."""
        since = stamp(self.clock() - days(keep_days))
        messages: list[Row] = await self._read(lambda conn: message_packets(conn, count), [])
        positions: list[Row] = await self._read(lambda conn: position_packets(conn, since, count), [])
        return [*self._packets(messages), *self._packets(positions)]

    async def count(self) -> int:
        return await self._read(count_packets, 0)

    async def stations(self) -> list[Station]:
        """Return the cached stations, latest heard first, after flushing pending changes."""
        self.flush_stations()
        nothing: tuple[list[Row], list[Row]] = ([], [])
        rows, radios = await self._read(lambda conn: (all_stations(conn), heard_by_radio(conn)), nothing)
        heard: dict[str, dict[RadioId, RadioHeard]] = {}
        for call, radio, what in self._decoded(radios, heard_of, "station_radio"):
            heard.setdefault(call, {})[radio] = what
        return self._decoded(rows, lambda row: station_of(row, heard=heard.get(str(row[0]))), "station")

    # ---- care
    async def forget_heard(self, keep_call: str) -> int:
        """Delete every heard packet (sent ones stay) and every station but `keep_call`.

        Return the packet count, or -1 on failure."""
        self._dirty = {call: station for call, station in self._dirty.items() if call == keep_call}
        gone = await self._write(
            lambda conn: delete_heard(conn, keep_call), -1, "the heard packets could not be forgotten"
        )
        self._history.clear()
        self.stats.clear()
        await self.give_back_room()
        return gone

    async def prune(self, keep_days: int, internet_keep_days: int | None = None) -> int:
        """Delete packets older than `keep_days`, internet ones older than `internet_keep_days`.

        Return the count. Slices of PRUNE_SLICE keep the write-ahead log small."""
        removed = 0
        for keep, internet in ((keep_days, False), (internet_keep_days, True)):
            if keep is None:
                continue
            step = partial(
                prune_packets_slice, stamp=stamp(self.clock() - days(keep)), rows=PRUNE_SLICE, internet_only=internet
            )
            while True:
                gone = await self._write(step, -1, "the packet log could not be pruned")
                if gone < 0:
                    return removed  # database refused; deletions so far stand
                removed += gone
                if gone < PRUNE_SLICE:
                    break
        await self.give_back_room()
        return removed
