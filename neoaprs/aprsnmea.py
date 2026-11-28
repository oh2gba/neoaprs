"""Raw NMEA 0183 sentences from a stand-alone tracker's GPS receiver (APRS101 ch. 6, 8).

GGA, GLL, RMC and WPL give positions; any talker is accepted. The symbol comes from the packet's
destination or source call (`tracker_symbol`); the sentence has none.
"""

import math
import re
from datetime import UTC, datetime
from functools import reduce

from neoaprs.aprsposition import FUTURE_TOLERANCE, PositionError, motion, resolve_timestamp
from neoaprs.packet import Position
from neoaprs.symbols import tracker_symbol

_SENTENCE = re.compile(r"\$[A-Z]{2}(GGA|GLL|RMC|WPL)(,.*?)(?:\*([0-9A-Fa-f]{2}))?$", re.DOTALL)
# a measured value beyond this is a damaged field (and a product with a unit stays finite)
_NUMBER_LIMIT = 1e9
_COORDINATE = re.compile(r"(\d{2,3})(\d{2}\.\d*)$")


class NmeaError(ValueError):
    """A damaged sentence: wrong checksum, or a field that is not what the sentence says."""


def _checksum_ok(text: str, given: str | None) -> bool:
    return given is None or reduce(lambda a, c: a ^ ord(c), text[1 : text.rindex("*")], 0) == int(given, 16)


def _coordinate(value: str, hemisphere: str, negative: str, positive: str, limit: int) -> float:
    found = _COORDINATE.match(value)
    if not found or hemisphere not in (negative, positive):
        raise NmeaError(f"bad coordinate {value!r}")
    whole, minutes = int(found.group(1)), float(found.group(2))
    degrees = whole + minutes / 60
    if minutes >= 60 or degrees > limit:
        raise NmeaError(f"coordinate {value!r} out of range")
    return -degrees if hemisphere == negative else degrees


def _place(fields: list[str], at: int) -> tuple[float, float]:
    """Return latitude and longitude from four fields (ddmm.mmm, N/S, dddmm.mmm, E/W)."""
    if len(fields) < at + 4:
        raise NmeaError("sentence cut short")
    return _coordinate(fields[at], fields[at + 1], "S", "N", 90), _coordinate(
        fields[at + 2], fields[at + 3], "W", "E", 180
    )


def _time(field: str, now: datetime) -> datetime | None:
    """Return the latest time of day (UTC) of hhmmss[.sss] not in the future; None if empty."""
    if len(field) < 6 or not field[:6].isdecimal():
        return None
    try:
        return resolve_timestamp(field[:6].encode() + b"h", now)
    except PositionError as e:
        raise NmeaError(str(e)) from e


def _number(field: str) -> float | None:
    """Return the number in a field; None if empty, not finite (`inf`, `nan`) or too large."""
    try:
        value = float(field)
    except ValueError:
        return None
    return value if math.isfinite(value) and abs(value) <= _NUMBER_LIMIT else None


def _measured(field: str) -> float | None:
    """Return the number in a possibly empty field (None); raise NmeaError for a non-number."""
    if not field.strip():
        return None
    value = _number(field)
    if value is None:
        raise NmeaError(f"bad number {field!r}")
    return value


def _date_time(time_field: str, date_field: str, now: datetime) -> datetime | None:
    """Return an RMC date and time; two-digit years are 1970 to 2069."""
    at = _time(time_field, now)
    if at is None or len(date_field) != 6 or not date_field.isdecimal():
        return at
    year = 2000 + int(date_field[4:]) if int(date_field[4:]) < 70 else 1900 + int(date_field[4:])
    try:
        stamp = datetime(year, int(date_field[2:4]), int(date_field[:2]), at.hour, at.minute, at.second, tzinfo=UTC)
    except ValueError as e:
        raise NmeaError("bad date") from e
    return stamp if stamp <= now + FUTURE_TOLERANCE else at


def parse_nmea(info: bytes, source: str, destination: str, now: datetime) -> Position | None:
    """Return the position in a raw NMEA information field (with its `$`).

    None for another sentence type or an invalid fix; raise NmeaError for a damaged sentence.
    """
    text = info.decode("latin-1").rstrip()
    found = _SENTENCE.match(text)
    if not found:
        return None
    if not _checksum_ok(text, found.group(3)):
        raise NmeaError("the NMEA checksum is wrong")
    kind, fields = found.group(1), found.group(2).split(",")[1:]
    if kind == "WPL":
        return _position(*_place(fields, 0), source, destination, comment=fields[4].strip() if len(fields) > 4 else "")
    if kind == "GLL":
        return (
            _position(*_place(fields, 0), source, destination, at=_time(fields[4], now) if len(fields) > 4 else None)
            if _valid(fields, 5, "A")
            else None
        )
    if kind == "RMC":
        if len(fields) < 9 or not _valid(fields, 1, "A"):
            return None
        knots = _measured(fields[6]) or 0.0
        if knots < 0:
            raise NmeaError(f"negative speed {fields[6]!r}")
        course, speed = motion(round(_measured(fields[7]) or 0), knots)
        return _position(
            *_place(fields, 2),
            source,
            destination,
            course=course,
            speed=speed,
            at=_date_time(fields[0], fields[8], now),
        )
    # GGA: field 5 is the quality, 0 is no fix
    if len(fields) < 9 or not fields[5].isdecimal() or int(fields[5]) == 0:
        return None
    altitude = _measured(fields[8]) if len(fields) > 9 and fields[9].upper() == "M" else None
    return _position(*_place(fields, 1), source, destination, altitude=altitude, at=_time(fields[0], now))


def _valid(fields: list[str], index: int, good: str) -> bool:
    """Return whether the status field says the data is valid (no field counts as valid)."""
    return len(fields) <= index or fields[index].upper() in (good, "", "D")


def _position(
    lat: float,
    lon: float,
    source: str,
    destination: str,
    *,
    course: int | None = None,
    speed: float | None = None,
    altitude: float | None = None,
    at: datetime | None = None,
    comment: str = "",
) -> Position:
    table, code = tracker_symbol(source, destination)
    return Position(lat, lon, table, code, comment, course, speed, altitude, at)
