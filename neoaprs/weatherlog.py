"""The weather log: every observation a weather station sent, kept for the trend graphs, and the latest of each station for the station book to start with.

Like the other logs this runs on the database thread (db.py) and says no instead of raising when the database is not open (dblog.py). `take` is an append that nobody waits for, in order with everything else
the thread was asked; the reads are awaited. The statements are weathersql.py's. `backfill` makes the log from the packets the database already holds: the parser reads
each one again."""
import logging
from datetime import datetime

from .aprsthirdparty import parse_packet
from .aprsweather import Weather
from .clock import Clock, days, utcnow
from .db import Db
from .dblog import DbLog
from .packet import Packet, channel_of
from .packetcodec import info_of, parse_stamp, stamp
from .weathersql import (Row, count_weather, insert_weather, insert_weather_many, latest_weather, latest_weather_all, prune_weather_before, weather_packets, weather_since)

log = logging.getLogger("neoaprs.weatherlog")

Observation = tuple[datetime, Weather]
_VALUES = ("wind_dir", "wind_kmh", "gust_kmh", "temp_c", "humidity", "pressure_hpa", "rain_1h_mm", "rain_24h_mm", "rain_today_mm", "luminosity")      # the columns after the station and the time, as Weather's fields


def weather_row(station: str, at: datetime, weather: Weather) -> Row:
    """The columns of the weather table, in order."""
    return (station, stamp(at), *(getattr(weather, name) for name in _VALUES), weather.raw)


def weather_of(row: Row) -> tuple[str, datetime, Weather]:
    """The station, the time and the observation from a row. Raises ValueError (or TypeError) for a row this program did not write."""
    station, at, *values, raw = row
    return str(station), parse_stamp(str(at)), Weather(**dict(zip(_VALUES, values, strict=True)), raw=str(raw))


def report_of(source: str, destination: str, raw: bytes, heard_at: datetime, via: str = "rf") -> tuple[str, Weather] | None:
    """The weather in a packet that was kept, read again with the parser as it is now: whose it is and what it says; None for a packet that has none. `via` is the packet's channel (a packet from the
    internet has no AX.25 frame to read the information field from)."""
    info = info_of(raw, via)
    decoded, third_party = parse_packet(info, source, destination, heard_at)
    return Packet(heard_at, "in", raw, source, destination, (), info, decoded, third_party, channel_of(third_party, via == "is", via == "dummy")).weather_report


def _kept_report(row: Row) -> tuple[datetime, tuple[str, Weather] | None]:
    """When a kept weather packet was heard and what it says."""
    source, destination, raw, heard_at, via = row
    at = parse_stamp(str(heard_at))
    return at, report_of(str(source), str(destination), bytes(raw), at, str(via))


class WeatherLog(DbLog):
    def __init__(self, db: Db | None = None, clock: Clock = utcnow) -> None:
        super().__init__(db, clock, log, "the weather could not be read")

    # ---- appends: nobody waits
    def take(self, packet: Packet) -> bool:
        """Keeps the observation a packet heard on the air carries (any other packet is left alone); False when there was none or it could not be queued."""
        report = packet.weather_report if packet.direction == "in" else None
        if report is None:
            return False
        row = weather_row(report[0], packet.heard_at, report[1])
        return self._append(lambda conn: insert_weather(conn, row))

    # ---- reads
    async def series(self, station: str, since: datetime) -> list[Observation]:
        """The observations of the station made at or after `since`, the oldest first."""
        text = stamp(since)
        rows: list[Row] = await self._read(lambda conn: weather_since(conn, station, text), [])
        return [(at, weather) for _, at, weather in self._decoded(rows, weather_of, "weather")]

    async def latest(self, station: str) -> Observation | None:
        """The newest observation of the station."""
        row: Row | None = await self._read(lambda conn: latest_weather(conn, station), None)
        found = [] if row is None else self._decoded([row], weather_of, "weather")
        return (found[0][1], found[0][2]) if found else None

    async def latest_all(self) -> dict[str, Observation]:
        """The newest observation of each station that has one: what the station book starts with."""
        rows: list[Row] = await self._read(latest_weather_all, [])
        return {station: (at, weather) for station, at, weather in self._decoded(rows, weather_of, "weather")}

    async def count(self) -> int:
        return await self._read(count_weather, 0)

    # ---- care
    async def backfill(self, keep_days: int) -> int:
        """Makes the log from the weather packets of the last `keep_days` days that the packet table holds; how many observations. The caller does this once, for a log that is empty."""
        since = stamp(self.clock() - days(keep_days))
        packets: list[Row] = await self._read(lambda conn: weather_packets(conn, since), [])
        found = self._decoded(packets, _kept_report, "packet")
        rows = [weather_row(report[0], at, report[1]) for at, report in found if report is not None]
        return await self._write(lambda conn: insert_weather_many(conn, rows), 0, "the weather could not be made from the packets") if rows else 0

    async def prune(self, keep_days: int) -> int:
        """Deletes the observations made more than `keep_days` days ago; how many."""
        cutoff = stamp(self.clock() - days(keep_days))
        return await self._write(lambda conn: prune_weather_before(conn, cutoff), 0, "the weather could not be pruned")
