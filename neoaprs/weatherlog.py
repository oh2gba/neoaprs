"""The weather log: every observation a weather station sent, for trend graphs and the station book.

Like the other logs it returns a failure value instead of raising when the database is closed.
`backfill` builds the log from the stored packets by parsing each again.
"""

import logging
from datetime import datetime

from .aprsthirdparty import parse_packet
from .aprsweather import Weather
from .clock import Clock, days, utcnow
from .db import Db
from .dblog import DbLog
from .packet import Packet, channel_of
from .packetcodec import info_of, parse_stamp, stamp
from .dberror import Row
from .weathersql import (
    count_weather,
    delete_weather,
    insert_weather,
    insert_weather_many,
    latest_weather,
    latest_weather_all,
    prune_weather_before,
    weather_packets,
    weather_since,
)

log = logging.getLogger("neoaprs.weatherlog")

Observation = tuple[datetime, Weather]
# columns after the station and the time, named as Weather's fields
_VALUES = (
    "wind_dir",
    "wind_kmh",
    "gust_kmh",
    "temp_c",
    "humidity",
    "pressure_hpa",
    "rain_1h_mm",
    "rain_24h_mm",
    "rain_today_mm",
    "luminosity",
)


def weather_row(station: str, at: datetime, weather: Weather) -> Row:
    return (station, stamp(at), *(getattr(weather, name) for name in _VALUES), weather.raw)


def weather_of(row: Row) -> tuple[str, datetime, Weather]:
    """Return the station, time and observation of a row; raise ValueError or TypeError if bad."""
    station, at, *values, raw = row
    return str(station), parse_stamp(str(at)), Weather(**dict(zip(_VALUES, values, strict=True)), raw=str(raw))


def report_of(
    source: str, destination: str, raw: bytes, heard_at: datetime, via: str = "rf"
) -> tuple[str, Weather] | None:
    """Parse a stored packet again and return whose weather it holds, or None."""
    info = info_of(raw, via)
    decoded, third_party = parse_packet(info, source, destination, heard_at)
    return Packet(
        heard_at,
        "in",
        raw,
        source,
        destination,
        (),
        info,
        decoded,
        third_party,
        channel_of(third_party, via == "is", via == "dummy"),
    ).weather_report


def _kept_report(row: Row) -> tuple[datetime, tuple[str, Weather] | None]:
    source, destination, raw, heard_at, via = row
    at = parse_stamp(str(heard_at))
    return at, report_of(str(source), str(destination), bytes(raw), at, str(via))


class WeatherLog(DbLog):
    def __init__(self, db: Db | None = None, clock: Clock = utcnow) -> None:
        super().__init__(db, clock, log, "the weather could not be read")

    def take(self, packet: Packet) -> bool:
        """Append the observation in a received packet (nobody waits); False if none or unqueued."""
        report = packet.weather_report if packet.direction == "in" else None
        if report is None:
            return False
        row = weather_row(report[0], packet.heard_at, report[1])
        return self._append(lambda conn: insert_weather(conn, row))

    async def series(self, station: str, since: datetime) -> list[Observation]:
        text = stamp(since)
        rows: list[Row] = await self._read(lambda conn: weather_since(conn, station, text), [])
        return [(at, weather) for _, at, weather in self._decoded(rows, weather_of, "weather")]

    async def latest(self, station: str) -> Observation | None:
        row: Row | None = await self._read(lambda conn: latest_weather(conn, station), None)
        found = [] if row is None else self._decoded([row], weather_of, "weather")
        return (found[0][1], found[0][2]) if found else None

    async def latest_all(self) -> dict[str, Observation]:
        """Return the newest observation of each station, for the station book."""
        rows: list[Row] = await self._read(latest_weather_all, [])
        return {station: (at, weather) for station, at, weather in self._decoded(rows, weather_of, "weather")}

    async def count(self) -> int:
        return await self._read(count_weather, 0)

    async def backfill(self, keep_days: int) -> int:
        """Build the log from stored weather packets of the last `keep_days` days; return count."""
        since = stamp(self.clock() - days(keep_days))
        packets: list[Row] = await self._read(lambda conn: weather_packets(conn, since), [])
        found = self._decoded(packets, _kept_report, "packet")
        rows = [weather_row(report[0], at, report[1]) for at, report in found if report is not None]
        return (
            await self._write(
                lambda conn: insert_weather_many(conn, rows), 0, "the weather could not be made from the packets"
            )
            if rows
            else 0
        )

    async def prune(self, keep_days: int) -> int:
        """Delete observations older than `keep_days` days; return the count."""
        cutoff = stamp(self.clock() - days(keep_days))
        return await self._write(lambda conn: prune_weather_before(conn, cutoff), 0, "the weather could not be pruned")

    async def forget_all(self) -> int:
        """Delete every observation; return the count."""
        return await self._write(delete_weather, 0, "the weather could not be forgotten")
