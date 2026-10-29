"""Mic-E: the position that is spread over the destination address and the first bytes of the information field.

The destination's six characters carry the latitude digits, three message bits, the north/south, longitude offset and west/east bits; the body carries the longitude, the speed and course, the
symbol, then an optional altitude and the comment."""
import re
from datetime import datetime
from typing import NamedTuple

from neoaprs.aprsextension import split_dao, with_dao
from neoaprs.aprsfreq import split_frequency
from neoaprs.aprslocator import Locator, split_locator
from neoaprs.aprsposition import degrees, motion
from neoaprs.aprstelemetry import split_comment_telemetry
from neoaprs.devicedata import MICE
from neoaprs.packet import Position, decode_text
from neoaprs.symbols import table_of
from neoaprs.units import base91

_STANDARD = ("Emergency", "Priority", "Special", "Committed", "Returning", "In Service", "En Route", "Off Duty")
_CUSTOM = ("Emergency", "Custom 6", "Custom 5", "Custom 4", "Custom 3", "Custom 2", "Custom 1", "Custom 0")
_DEFAULT_MESSAGE = "Off Duty"
_ALTITUDE = re.compile(rb"([\x21-\x7b]{3})\}")                             # right at the start of the status text (after the type code and the locator), and nowhere else: "QRT}" at the end of a sentence is text
_HEX = re.compile(rb"[0-9A-Fa-f]+$")
_LEGACY_SUFFIXES = {b">": (b"=", b"^", b"&"), b"]": (b"=",)}            # Kenwood: TH-D72, TH-D74, TH-D75; TM-D710 (aprs-deviceid, micelegacy)
_SUFFIXES = frozenset(suffix.encode() for suffix, _ in MICE)              # the two-byte suffixes after a leading ` or ' (aprs-deviceid's mice table, the snapshot of devicedata.py)
_MIN_BODY = 8


class MicEError(ValueError):
    """A destination or a body that is not Mic-E."""


class _Char(NamedTuple):
    """What one destination character says: a digit (None for a blank), its message bit and whether it was a custom-message letter."""
    digit: int | None
    bit: int
    custom: bool


def _dest_char(c: str, index: int) -> _Char:
    if "0" <= c <= "9":
        return _Char(int(c), 0, False)
    if "A" <= c <= "J" and index < 3:
        return _Char(ord(c) - 65, 1, True)
    if c == "K" and index < 3:
        return _Char(None, 1, True)
    if c == "L":
        return _Char(None, 0, False)
    if "P" <= c <= "Y":
        return _Char(ord(c) - 80, 1, False)
    if c == "Z":
        return _Char(None, 1, False)
    raise MicEError(f"bad character {c!r} in the destination")


def _message_name(chars: list[_Char]) -> str | None:
    """The Mic-E message of the first three destination characters, None when standard and custom bits are mixed."""
    first = chars[:3]
    custom, standard = any(c.custom for c in first), any(c.bit and not c.custom for c in first)
    if custom and standard:
        return None
    index = first[0].bit * 4 + first[1].bit * 2 + first[2].bit
    return (_CUSTOM if custom else _STANDARD)[index]


def _latitude(chars: list[_Char]) -> tuple[float, int]:
    digits = [c.digit for c in chars]
    blanks = 0
    while blanks < 4 and digits[5 - blanks] is None:
        blanks += 1
    if any(d is None for d in digits[:6 - blanks]):
        raise MicEError("blank digits inside the latitude")
    plain = [d or 0 for d in digits]
    whole, minutes, hundredths = plain[0] * 10 + plain[1], plain[2] * 10 + plain[3], plain[4] * 10 + plain[5]
    if whole > 90 or minutes > 59:
        raise MicEError("latitude out of range")
    lat = min(degrees(whole, minutes * 100 + hundredths, blanks), 90.0)
    return (lat if chars[3].bit else -lat), blanks


def _longitude(body: bytes, offset: bool, west: bool, blanks: int) -> float:
    d, m, h = body[0] - 28, body[1] - 28, body[2] - 28
    if min(d, m, h) < 0:
        raise MicEError("longitude out of range")
    d += 100 if offset else 0
    if 190 <= d <= 199:
        d -= 190
    elif 180 <= d <= 189:
        d -= 80
    if m >= 60:
        m -= 60
    if not (0 <= d <= 179 and 0 <= m <= 59 and 0 <= h <= 99):
        raise MicEError("longitude out of range")
    lon = min(degrees(d, m * 100 + h, blanks), 180.0)
    return -lon if west else lon


def _motion(body: bytes) -> tuple[int | None, float | None]:
    sp, dc, se = body[3] - 28, body[4] - 28, body[5] - 28
    if min(sp, dc, se) < 0:
        raise MicEError("bad speed or course")
    speed = sp * 10 + dc // 10
    course = dc % 10 * 100 + se
    speed -= 800 if speed >= 800 else 0
    course -= 400 if course >= 400 else 0
    if course > 360:
        raise MicEError("course out of range")
    return motion(course, speed)


class MicType(NamedTuple):
    """What a Mic-E status text starts and ends with: the radio's type code (`lead`: the first byte, empty when the text has none) and its `suffix` (the one or two bytes at the end that tell the models apart,
    empty when there is none), and the `text` without them."""
    lead: bytes
    suffix: bytes
    text: bytes


def mice_type(rest: bytes) -> MicType:
    """The type code, the suffix and the status text of the bytes that follow the symbol of a Mic-E packet (any CR or LF the radio ends them with is not part of them: Kenwood and Yaesu add a CR). The type code
    (aprs-deviceid's mice and micelegacy tables): a leading ">" with an optional trailing "=", "^" or "&" of Kenwood's handhelds, "]" with an optional "=" of its mobiles, or a leading "`" or "'" and one of the
    two-byte suffixes of the newer radios and trackers; a suffix that is not in the table stays in the text. The telemetry of the original Mic-E (obsolete since the type codes took the same first bytes) is
    taken off the text and has no type code: the flag "`" and two values in two hex digits each, the flag "'" and five, the flag 0x1d and five binary values. A text that ends with a known suffix is a radio's,
    whatever its first characters look like: "`1296 MHz_3" is a Yaesu saying 1296 MHz, not telemetry."""
    rest = rest.rstrip(b"\r\n")
    lead = rest[:1]
    if lead in (b"`", b"'") and rest[-2:] in _SUFFIXES:
        return MicType(lead, rest[-2:], rest[1:-2])
    if lead == b"`" and len(rest) >= 5 and _HEX.match(rest[1:5]):
        return MicType(b"", b"", rest[5:])
    if lead == b"'" and len(rest) >= 11 and _HEX.match(rest[1:11]):
        return MicType(b"", b"", rest[11:])
    if lead == b"\x1d" and len(rest) >= 6:
        return MicType(b"", b"", rest[6:])
    if lead not in (b">", b"]", b"`", b"'"):
        return MicType(b"", b"", rest)
    rest = rest[1:]
    if rest[-1:] in _LEGACY_SUFFIXES.get(lead, ()):
        return MicType(lead, rest[-1:], rest[:-1])
    return MicType(lead, b"", rest)


def _altitude_in(rest: bytes) -> tuple[float | None, bytes]:
    """The altitude `xxx}` (metres above 10 km below mean sea level, three base-91 digits) at the start of the status text, and the text without it."""
    found = _ALTITUDE.match(rest)
    if not found:
        return None, rest
    return base91(found.group(1)) - 10000.0, rest[:found.start()] + rest[found.end():]


def _altitude_and_comment(rest: bytes) -> tuple[float | None, str, Locator | None]:
    """The altitude, the comment and the Maidenhead locator of the status text: the locator is first in the text, the altitude right after it (or first, without one)."""
    text = decode_text(mice_type(rest).text)
    locator, text = split_locator(text)
    altitude, remains = _altitude_in(text.encode("utf-8"))
    return altitude, decode_text(remains).strip(), locator


def parse_mice(destination: str, body: bytes, now: datetime) -> Position:
    """The position of a Mic-E packet from the destination call and the bytes after the data type identifier; `now` is not needed (Mic-E has no timestamp) and kept for the same shape as the others."""
    dest = destination.split("-")[0]
    if len(dest) < 6:
        raise MicEError("destination shorter than six characters")
    if len(body) < _MIN_BODY:
        raise MicEError("body shorter than eight bytes")
    chars = [_dest_char(c, i) for i, c in enumerate(dest[:6])]
    lat, blanks = _latitude(chars)
    lon = _longitude(body, bool(chars[4].bit), bool(chars[5].bit), blanks)
    course, speed = _motion(body)
    table = table_of(chr(body[7]))
    if table is None or not 33 <= body[6] <= 126:
        raise MicEError("bad symbol")
    altitude, comment, locator = _altitude_and_comment(body[8:])
    comment, frequency = split_frequency(comment)
    comment, telemetry = split_comment_telemetry(comment)
    comment, extra = split_dao(comment)
    if not blanks:
        lat, lon = with_dao(lat, lon, extra)
    name = _message_name(chars)
    if name is not None and name != _DEFAULT_MESSAGE:
        comment = f"Mic-E: {name} - {comment}" if comment else f"Mic-E: {name}"
    return Position(lat, lon, table, chr(body[6]), comment, course, speed, altitude, ambiguity=blanks, locator=locator, telemetry=telemetry, frequency=frequency)
