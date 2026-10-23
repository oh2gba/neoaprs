"""APRS positions: the uncompressed and the compressed forms, with the symbol, the course, the speed, the altitude and the timestamp.

`parse_position` takes the bytes that follow the data type identifier ("!", "=", "/" or "@"); a timestamp is recognised by its shape, so the same function reads all four."""
import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

from neoaprs.aprsextension import Extensions, split_bearing, split_extension
from neoaprs.aprsweather import MPH_KMH, Weather, parse_weather
from neoaprs.packet import Position, decode_text
from neoaprs.symbols import table_of

KNOT_KMH = 1.852
FOOT_M = 0.3048
FUTURE_TOLERANCE = timedelta(minutes=5)               # a clock that runs ahead of ours by a few minutes is still "now"
_AMBIGUITY_UNIT = (10, 100, 1000, 6000)               # hundredths of a minute that one to four blanked digits leave unknown
_COURSE_SPEED = re.compile(r"(\d{3})/(\d{3})")
_ALTITUDE = re.compile(r"/A=(-\d{5}|\d{6})")
_UNCOMPRESSED_LEN, _COMPRESSED_LEN = 19, 13
HUNDREDTHS_PER_DEGREE = 6000


class PositionError(ValueError):
    """A body that is not a position."""


class _Fix(NamedTuple):
    lat: float
    lon: float
    table: str
    code: str
    tail: bytes                                       # what follows the position: the comment
    ambiguity: int = 0
    course: int | None = None
    speed: float | None = None
    altitude: float | None = None
    wind: tuple[int, float] | None = None             # a weather station's cs bytes: the wind direction (degrees) and speed (km/h)


def degrees(whole: int, minutes_hundredths: int, ambiguity: int = 0) -> float:
    """Degrees from whole degrees and hundredths of a minute; with `ambiguity` 1 to 4 the centre of the square that the blanked digits leave."""
    if ambiguity:
        unit = _AMBIGUITY_UNIT[ambiguity - 1]
        return whole + (minutes_hundredths // unit * unit + unit / 2) / 6000
    return whole + minutes_hundredths / 6000


def motion(course_raw: int, speed_knots: float) -> tuple[int | None, float | None]:
    """Course in degrees (0-359, None when unknown) and speed in km/h (None when there is nothing) from what the packet says; 360 is north, 0 with a speed of 0 is no data."""
    if course_raw == 0 and speed_knots == 0:
        return None, None
    return (course_raw % 360 if course_raw else None), speed_knots * KNOT_KMH


def _nearest_dhm(day: int, hour: int, minute: int, now: datetime) -> datetime:
    limit = now + FUTURE_TOLERANCE
    for step in range(1, -13, -1):                    # next month first (a clock a few minutes ahead), then back; a day that month lacks is skipped
        index = now.year * 12 + now.month - 1 + step
        try:
            candidate = datetime(index // 12, index % 12 + 1, day, hour, minute, tzinfo=UTC)
        except ValueError:
            continue
        if candidate <= limit:
            return candidate
    raise PositionError("timestamp matches no date")


def resolve_mdhm(raw: str, now: datetime) -> datetime:
    """The instant of the 8 digits MMDDhhmm (UTC) that start a positionless weather report: the latest one, going back as far as a leap day takes, that is not more than a few minutes after `now`."""
    if len(raw) != 8 or not raw.isdigit():
        raise PositionError("bad timestamp")
    now = now.astimezone(UTC)
    month, day, hour, minute = int(raw[0:2]), int(raw[2:4]), int(raw[4:6]), int(raw[6:8])
    for year in range(now.year, now.year - 5, -1):
        try:
            candidate = datetime(year, month, day, hour, minute, tzinfo=UTC)
        except ValueError:
            continue
        if candidate <= now + FUTURE_TOLERANCE:
            return candidate
    raise PositionError("timestamp matches no date")


def resolve_timestamp(raw: bytes, now: datetime) -> datetime:
    """The instant of a 7-byte timestamp ("DDHHMMz", "DDHHMM/" in the sender's local time, which is kept as it is sent, "HHMMSSh"): the latest one that is not more than a few minutes after `now`."""
    if len(raw) != 7 or not raw[:6].isdigit() or raw[6:7] not in (b"z", b"/", b"h"):
        raise PositionError("bad timestamp")
    now = now.astimezone(UTC)
    a, b, c = int(raw[0:2]), int(raw[2:4]), int(raw[4:6])
    if raw[6:7] == b"h":
        if a > 23 or b > 59 or c > 59:
            raise PositionError("bad time of day in the timestamp")
        candidate = now.replace(hour=a, minute=b, second=c, microsecond=0)
        return candidate - timedelta(days=1) if candidate > now + FUTURE_TOLERANCE else candidate
    if not 1 <= a <= 31 or b > 23 or c > 59:
        raise PositionError("bad day or time in the timestamp")
    return _nearest_dhm(a, b, c, now)


def _has_timestamp(body: bytes) -> bool:
    return len(body) >= 7 and body[:6].isdigit() and body[6:7] in (b"z", b"/", b"h")


def _coordinate(text: str, whole_digits: int, negative: str, positive: str) -> tuple[float, int]:
    """A coordinate "DDMM.mmN" or "DDDMM.mmW" with blanks for ambiguity: its value and the number of blanked digits."""
    sign, digits = text[-1].upper(), text[:-1]
    if sign not in (negative, positive) or len(digits) != whole_digits + 5 or digits[whole_digits + 2] != ".":
        raise PositionError(f"bad coordinate {text!r}")
    w = whole_digits
    blank_order = (w + 4, w + 3, w + 1, w)            # the digits that a blank replaces, last digit first
    blanks = digits.count(" ")
    if blanks > 4 or any(digits[i] != " " for i in blank_order[:blanks]):
        raise PositionError(f"bad ambiguity in {text!r}")
    plain = digits.replace(" ", "0")
    if not (plain[:w + 2] + plain[w + 3:]).isdigit():
        raise PositionError(f"bad coordinate {text!r}")
    whole, minutes = int(plain[:w]), int(plain[w:w + 2])
    if minutes > 59 or whole > (90 if w == 2 else 180):
        raise PositionError(f"coordinate {text!r} out of range")
    value = degrees(whole, minutes * 100 + int(plain[w + 3:]), blanks)
    value = min(value, 90.0 if w == 2 else 180.0)
    return (-value if sign == negative else value), blanks


def _base91(data: bytes) -> int:
    value = 0
    for b in data:
        if not 33 <= b <= 123:
            raise PositionError("bad base-91 character in a compressed position")
        value = value * 91 + b - 33
    return value


def _symbol(table: str, code: str) -> tuple[str, str]:
    t = table_of(table)
    if t is None:
        raise PositionError(f"bad symbol table {table!r}")
    if not 33 <= ord(code) <= 126:
        raise PositionError("bad symbol code")
    return t, code


def _compressed_wind(cs: bytes) -> tuple[int, float] | None:
    """The wind direction and speed in the cs bytes of a weather station's compressed position (the same coding as course and speed; the speed is in miles per hour, like the other wind speeds of a weather report)."""
    if cs[0] == 0x20 or cs[0] - 33 > 89:
        return None
    return (cs[0] - 33) * 4, round((1.08 ** (cs[1] - 33) - 1) * MPH_KMH, 1)


def _compressed_motion(cs: bytes, t: int) -> tuple[int | None, float | None, float | None]:
    """Course, speed and altitude from the two cs bytes and the type byte of a compressed position."""
    if cs[0] == 0x20:
        return None, None, None
    c, s = cs[0] - 33, cs[1] - 33
    if ((t - 33) >> 3) & 3 == 2:                        # the fix came from a GGA sentence: cs is the altitude
        return None, None, 1.002 ** (c * 91 + s) * FOOT_M
    if c <= 89:
        course, speed = motion(c * 4, 1.08 ** s - 1)
        return course, speed, None
    return None, None, None                           # "{": the radio range, which nobody here needs


def _compressed(rest: bytes) -> _Fix:
    if len(rest) < _COMPRESSED_LEN:
        raise PositionError("compressed position too short")
    table, code = _symbol(chr(rest[0]), chr(rest[9]))
    lat = 90 - _base91(rest[1:5]) / 380926
    lon = -180 + _base91(rest[5:9]) / 190463
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise PositionError("compressed position out of range")
    if code == "_":                                   # a weather station's cs is the wind
        return _Fix(lat, lon, table, code, rest[_COMPRESSED_LEN:], wind=_compressed_wind(rest[10:12]))
    course, speed, altitude = _compressed_motion(rest[10:12], rest[12])
    return _Fix(lat, lon, table, code, rest[_COMPRESSED_LEN:], 0, course, speed, altitude)


def _uncompressed(rest: bytes) -> _Fix:
    if len(rest) < _UNCOMPRESSED_LEN:
        raise PositionError("position too short")
    text = rest[:_UNCOMPRESSED_LEN].decode("latin-1")
    lat, lat_blanks = _coordinate(text[0:8], 2, "S", "N")
    lon, lon_blanks = _coordinate(text[9:18], 3, "W", "E")
    table, code = _symbol(text[8], text[18])
    return _Fix(lat, lon, table, code, rest[_UNCOMPRESSED_LEN:], max(lat_blanks, lon_blanks))


class _Tail(NamedTuple):
    comment: str
    course: int | None
    speed: float | None
    altitude: float | None
    extensions: Extensions | None


def _data_extension(text: str, table: str, code: str) -> tuple[str, int | None, float | None, Extensions | None]:
    """The 7-byte data extension of an uncompressed position taken off the front of the comment: course and speed (a weather station's "220/004" is wind, the weather's), with the bearing of a DF report
    that may follow, or PHG, RNG, DFS or the descriptor of an area object. Returns the rest of the comment, the course, the speed and the extensions."""
    ext, rest = split_extension(text, table == "\\" and code == "l")
    if ext is not None:
        return rest, None, None, ext
    found = _COURSE_SPEED.match(text)
    if not found or int(found.group(1)) > 360:
        return text, None, None, None
    course, speed = motion(int(found.group(1)), int(found.group(2)))
    bearing, rest = split_bearing(text[7:])
    return rest, course, speed, None if bearing is None else Extensions(df_bearing=bearing)


def _comment_and_extensions(text: str, table: str, code: str, extensions: bool) -> _Tail:
    """The comment of a position without its data extension (uncompressed positions only) and without its "/A=" altitude, and what they said."""
    course = speed = altitude = ext = None
    if extensions and code != "_":
        text, course, speed, ext = _data_extension(text, table, code)
    found = _ALTITUDE.search(text)
    if found:
        altitude = int(found.group(1)) * FOOT_M
        text = text[:found.start()] + text[found.end():]
    return _Tail(text.strip(), course, speed, altitude, ext)


def _with_wind(weather: Weather | None, wind: tuple[int, float] | None) -> Weather | None:
    """The weather with the wind of a compressed position's cs bytes."""
    if wind is None:
        return weather
    return replace(weather or Weather(), wind_dir=wind[0], wind_kmh=wind[1])


def parse_position(body: bytes, now: datetime, *, messaging: bool = False) -> Position:
    """The position in `body` (what follows the data type identifier); `now` resolves a timestamp; `messaging` is true for the identifiers "=" and "@"."""
    timestamp, local = None, False
    if _has_timestamp(body):
        timestamp, local, body = resolve_timestamp(body[:7], now), body[6:7] == b"/", body[7:]
    if not body:
        raise PositionError("no position")
    compressed = not (body[0:1].isdigit() or body[0] == 0x20)
    fix = (_compressed if compressed else _uncompressed)(body)
    text = decode_text(fix.tail)
    weather, text = parse_weather(text) if fix.code == "_" else (None, text)
    tail = _comment_and_extensions(text, fix.table, fix.code, not compressed)
    return Position(fix.lat, fix.lon, fix.table, fix.code, tail.comment, tail.course if tail.course is not None else fix.course, tail.speed if tail.speed is not None else fix.speed,
                    tail.altitude if tail.altitude is not None else fix.altitude, timestamp, messaging, compressed, fix.ambiguity, _with_wind(weather, fix.wind), tail.extensions, local)


def _coordinate_text(value: float, whole_digits: int, negative: str, positive: str) -> str:
    """DDMM.mmN or DDDMM.mmE: the minutes rounded to hundredths (a rounding that reaches 60 minutes carries into the degrees)."""
    total = round(abs(value) * HUNDREDTHS_PER_DEGREE)
    degrees, rest = divmod(total, HUNDREDTHS_PER_DEGREE)
    return f"{degrees:0{whole_digits}d}{rest // 100:02d}.{rest % 100:02d}{negative if value < 0 and total else positive}"


def uncompressed_position(lat: float, lon: float, symbol_table: str, symbol_code: str) -> bytes:
    """The 19 bytes DDMM.mmN/DDDMM.mmE- of an uncompressed position: latitude, symbol table, longitude, symbol code."""
    return f"{_coordinate_text(lat, 2, 'S', 'N')}{symbol_table}{_coordinate_text(lon, 3, 'W', 'E')}{symbol_code}".encode("ascii")
