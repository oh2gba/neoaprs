"""The dispatcher: an information field plus the calls become what the packet says.

`parse` never raises: a field that should have decoded and did not becomes `Undecoded` with the
reason.
"""
import logging
import re
from dataclasses import replace
from collections.abc import Callable
from datetime import datetime

from neoaprs.aprsfreq import named_frequency, split_frequency
from neoaprs.aprslocator import split_beacon, split_locator
from neoaprs.aprsmessage import MessageError, parse_message
from neoaprs.aprsmice import MicEError, parse_mice
from neoaprs.aprsnmea import NmeaError, parse_nmea
from neoaprs.aprsposition import PositionError, parse_position, resolve_mdhm, resolve_timestamp
from neoaprs.aprstelemetry import parse_telemetry
from neoaprs.aprsweather import parse_report
from neoaprs.packet import Decoded, ItemReport, ObjectReport, Other, Position, Status, Undecoded, decode_text

log = logging.getLogger("neoaprs.aprsparse")
DAMAGED = "the packet is damaged or not in a form NeoAPRS understands"

# data types that are only named (the decoded ones are in _HANDLERS)
_OTHER_KINDS = {b"?": "query", b"}": "third-party", b"{": "user-defined", b"#": "weather", b"*": "weather", b",": "test", b"+": "shelter", b".": "space-weather"}
POSITION_IDS = (b"!", b"=", b"/", b"@")
MICE_CURRENT_IDS = (b"'", b"`")
_MICE = (*MICE_CURRENT_IDS, b"\x1c", b"\x1d")
_OBJECT_HEAD = 9 + 1 + 7  # name, "*" or "_", timestamp: the position follows
_ITEM_NAME = range(3, 10)  # where the "!" or "_" that ends an item's name can be
# the "!" of a position may be anywhere up to the 40th character (X1J-style digipeaters put their
# own text first; deprecated since 2012, still read)
_BANG_LIMIT = 40
_AGRELO = re.compile(r"%(\d{3})%(\d)")
_ITEM_SPLIT = re.compile(r"[,\r\n]+")


def _named(name: str, position: Position) -> Position:
    """Return the position of an object or item named by a frequency (`145.775-A`)."""
    frequency, comment = named_frequency(name, position.frequency, position.comment)
    return position if frequency is position.frequency else replace(position, frequency=frequency, comment=comment)


# Every decoder takes the whole information field (type identifier first), source, destination and
# `now`, needed or not: one shape, so that _HANDLERS can hold them all.

def _object(info: bytes, source: str, destination: str, now: datetime) -> Decoded:
    body = info[1:]
    if len(body) <= _OBJECT_HEAD:
        raise PositionError("object too short")
    status = body[9:10]
    if status not in (b"*", b"_"):
        raise PositionError("object status is neither * nor _")
    name = decode_text(body[:9]).rstrip(" ")
    position = _named(name, parse_position(body[10:], now))
    return ObjectReport(name, status == b"*", position, position.timestamp)


def _item(info: bytes, source: str, destination: str, now: datetime) -> Decoded:
    body = info[1:]
    ends = [i for i in _ITEM_NAME if body[i:i + 1] in (b"!", b"_")]
    if not ends:
        raise PositionError("item name has no ! or _ after three to nine characters")
    end = ends[0]
    name = decode_text(body[:end])
    return ItemReport(name, body[end:end + 1] == b"!", _named(name, parse_position(body[end + 1:], now)))


def _status(info: bytes, source: str, destination: str, now: datetime) -> Decoded:
    body = info[1:]
    if len(body) >= 7 and body[:6].isdigit() and body[6:7] == b"z":
        text, frequency = split_frequency(decode_text(body[7:]).strip())
        try:
            return Status(text, resolve_timestamp(body[:7], now), frequency=frequency)
        except PositionError:
            pass
    text = decode_text(body)
    locator, rest = split_locator(text)  # a report with a locator has no timestamp
    text, frequency = split_frequency((rest if locator else text).strip())
    return Status(text, None, locator, frequency)


def _capabilities(info: bytes, source: str, destination: str, now: datetime) -> Decoded:
    """Return the capability items of a station, TOKEN or TOKEN=VALUE separated by commas."""
    text = decode_text(info)
    items: dict[str, str] = {}
    for piece in _ITEM_SPLIT.split(text[1:]):
        token, _, value = piece.strip().partition("=")
        if token:
            items[token] = value
    return Other("capabilities", text, items=items)


def _agrelo(info: bytes, source: str, destination: str, now: datetime) -> Decoded:
    text = decode_text(info)
    found = _AGRELO.match(text)
    return Other("agrelo-df", text, items=None if found is None else {"bearing": found.group(1), "quality": found.group(2)})


def _weather_report(info: bytes, source: str, destination: str, now: datetime) -> Decoded:
    """Return a positionless weather report: the observation and its MMDDhhmm time if a date."""
    text = decode_text(info)
    try:
        at = resolve_mdhm(text[1:9], now)
    except PositionError:
        at = None
    return Other("weather", text, parse_report(info), timestamp=at)


def _locator_beacon(info: bytes, source: str, destination: str, now: datetime) -> Decoded:
    found = split_beacon(decode_text(info[1:]))
    if found is None:
        raise PositionError("no Maidenhead locator")
    locator, comment = found
    return Position(locator.lat, locator.lon, locator.symbol_table, locator.symbol_code, comment.strip())


def _nmea(info: bytes, source: str, destination: str, now: datetime) -> Decoded:
    if info[:5] == b"$ULTW":  # Ultimeter 2000 raw data: not in the specification
        return Other("weather", decode_text(info))
    return parse_nmea(info, source, destination, now) or Other("nmea", decode_text(info))


def _position(info: bytes, source: str, destination: str, now: datetime) -> Decoded:
    if info[:2] == b"!!":  # Ultimeter 2000 raw data
        return Other("weather", decode_text(info))
    return parse_position(info[1:], now, messaging=info[:1] in (b"=", b"@"))


def _telemetry(info: bytes, source: str, destination: str, now: datetime) -> Decoded:
    text = decode_text(info)
    return parse_telemetry(text) or Other("telemetry", text)


def _mice(info: bytes, source: str, destination: str, now: datetime) -> Decoded:
    return parse_mice(destination, info[1:], now)


def _message(info: bytes, source: str, destination: str, now: datetime) -> Decoded:
    return parse_message(info[1:])


_Handler = Callable[[bytes, str, str, datetime], Decoded]
# The decoder of each data type identifier that has one; the others are `Other` named by
# `_OTHER_KINDS`.
_HANDLERS: dict[bytes, _Handler] = {
    **dict.fromkeys(POSITION_IDS, _position), **dict.fromkeys(_MICE, _mice), b":": _message, b";": _object, b")": _item, b">": _status, b"[": _locator_beacon, b"_": _weather_report,
    b"$": _nmea, b"T": _telemetry, b"<": _capabilities, b"%": _agrelo}


def _dispatch(first: bytes, info: bytes, source: str, destination: str, now: datetime) -> Decoded:
    handler = _HANDLERS.get(first)
    if handler is not None:
        return handler(info, source, destination, now)
    return Other(_OTHER_KINDS.get(first, "unknown"), decode_text(info))


def _bang_position(info: bytes, now: datetime) -> Position | None:
    """Return the position of a `!` report with text before it (within 40 characters), else None.

    The text becomes the start of the comment. A deprecated X1J form that is read, never sent.
    """
    bang = info.find(b"!", 1, _BANG_LIMIT)
    if bang < 0:
        return None
    try:
        position = parse_position(info[bang + 1:], now)
    except PositionError:
        return None
    prefix = decode_text(info[:bang]).strip()
    return replace(position, comment=f"{prefix} {position.comment}".strip())


def parse(info: bytes, source: str, destination: str, now: datetime) -> Decoded:
    """Return what the information field says; `now` resolves timestamps.

    `source` gives a raw NMEA tracker its symbol when its destination does not.
    """
    if not info:
        return Undecoded("empty information field", "", "empty")
    try:
        decoded = _dispatch(info[:1], info, source, destination, now)
        # test data is never a position
        if isinstance(decoded, Other) and info[:1] not in (b"}", b"{", b","):
            return _bang_position(info, now) or decoded
        return decoded
    except (PositionError, MicEError, MessageError, NmeaError) as e:
        code = "mice" if isinstance(e, MicEError) else "message" if isinstance(e, MessageError) else "nmea" if isinstance(e, NmeaError) else "position"
        return Undecoded(str(e), info.decode("latin-1"), code)
    except (ValueError, IndexError, OverflowError) as e:
        log.debug("undecoded %r: %s: %s", info, type(e).__name__, e)
        return Undecoded(DAMAGED, info.decode("latin-1"), "damaged")
