"""Raw NMEA 0183 sentences from a GPS receiver, as a stand-alone tracker sends them (APRS101, chapters 6 and 8): GGA (fix data: position, altitude), GLL (position), RMC (position, speed, course, date) and
WPL (a waypoint's position) are positions; VTG (course and speed alone) and the sentences that say the fix is not valid are not. The talker may be any (`GP`, `GN`, `GL`...). The symbol comes from the packet's
destination or source call (symbols.py `tracker_symbol`), the sentence has none.

Pure code, like the rest of the foundation."""
import re
from datetime import UTC, datetime
from functools import reduce

from neoaprs.aprsposition import FUTURE_TOLERANCE, PositionError, motion, resolve_timestamp
from neoaprs.packet import Position
from neoaprs.symbols import tracker_symbol

_SENTENCE = re.compile(r"\$[A-Z]{2}(GGA|GLL|RMC|WPL)(,.*?)(?:\*([0-9A-Fa-f]{2}))?\s*$", re.DOTALL)
_COORDINATE = re.compile(r"(\d{2,3})(\d{2}\.\d*)$")


class NmeaError(ValueError):
    """A sentence that is damaged: its checksum is wrong, or a field is not what the sentence says."""


def _checksum_ok(text: str, given: str | None) -> bool:
    return given is None or reduce(lambda a, c: a ^ ord(c), text[1:text.rindex("*")], 0) == int(given, 16)


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
    """The latitude and longitude from the four fields from `at`: ddmm.mmm, N/S, dddmm.mmm, E/W."""
    if len(fields) < at + 4:
        raise NmeaError("sentence cut short")
    return _coordinate(fields[at], fields[at + 1], "S", "N", 90), _coordinate(fields[at + 2], fields[at + 3], "W", "E", 180)


def _time(field: str, now: datetime) -> datetime | None:
    """The time of day of a field hhmmss[.sss] (UTC), as the latest such time that is not in the future; None for an empty field."""
    if len(field) < 6 or not field[:6].isdigit():
        return None
    try:
        return resolve_timestamp(field[:6].encode() + b"h", now)
    except PositionError as e:
        raise NmeaError(str(e)) from e


def _number(field: str) -> float | None:
    try:
        return float(field)
    except ValueError:
        return None


def _date_time(time_field: str, date_field: str, now: datetime) -> datetime | None:
    """An RMC's date and time (ddmmyy, hhmmss): the two years' digits are 1970 to 2069."""
    at = _time(time_field, now)
    if at is None or len(date_field) != 6 or not date_field.isdigit():
        return at
    year = 2000 + int(date_field[4:]) if int(date_field[4:]) < 70 else 1900 + int(date_field[4:])
    try:
        stamp = datetime(year, int(date_field[2:4]), int(date_field[:2]), at.hour, at.minute, at.second, tzinfo=UTC)
    except ValueError as e:
        raise NmeaError("bad date") from e
    return stamp if stamp <= now + FUTURE_TOLERANCE else at


def parse_nmea(info: bytes, source: str, destination: str, now: datetime) -> Position | None:
    """The position in a raw NMEA sentence (the information field, with its `$`); None for a sentence that has none: another type, or a fix that is not valid. Raises NmeaError for a damaged one."""
    text = info.decode("latin-1")
    found = _SENTENCE.match(text)
    if not found:
        return None
    if not _checksum_ok(text.rstrip(), found.group(3)):
        raise NmeaError("the NMEA checksum is wrong")
    kind, fields = found.group(1), found.group(2).split(",")[1:]
    if kind == "WPL":
        return _position(*_place(fields, 0), source, destination, comment=fields[4].strip() if len(fields) > 4 else "")
    if kind == "GLL":
        return _position(*_place(fields, 0), source, destination, at=_time(fields[4], now) if len(fields) > 4 else None) if _valid(fields, 5, "A") else None
    if kind == "RMC":
        if len(fields) < 9 or not _valid(fields, 1, "A"):
            return None
        course, speed = motion(round(_number(fields[7]) or 0), _number(fields[6]) or 0.0)
        return _position(*_place(fields, 2), source, destination, course=course, speed=speed, at=_date_time(fields[0], fields[8], now))
    if len(fields) < 9 or not fields[5].isdigit() or int(fields[5]) == 0:                       # GGA: field 5 is the quality, 0 is no fix
        return None
    altitude = _number(fields[8]) if len(fields) > 9 and fields[9].upper() == "M" else None
    return _position(*_place(fields, 1), source, destination, altitude=altitude, at=_time(fields[0], now))


def _valid(fields: list[str], index: int, good: str) -> bool:
    """The status field says the data is valid (a sentence without the field is taken as valid)."""
    return len(fields) <= index or fields[index].upper() in (good, "", "D")


def _position(lat: float, lon: float, source: str, destination: str, *, course: int | None = None, speed: float | None = None, altitude: float | None = None,
              at: datetime | None = None, comment: str = "") -> Position:
    table, code = tracker_symbol(source, destination)
    return Position(lat, lon, table, code, comment, course, speed, altitude, at)

