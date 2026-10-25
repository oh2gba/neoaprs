"""The dispatcher: an information field and the destination and source calls to what the packet says, by its data type identifier.

`parse` never raises: a field that should have decoded and did not becomes `Undecoded` with the reason."""
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

_OTHER_KINDS = {b"T": "telemetry", b"_": "weather", b"$": "nmea", b"?": "query", b"}": "third-party", b"{": "user-defined", b"#": "weather", b"*": "weather", b",": "test", b"<": "capabilities",
                b"%": "agrelo-df", b"+": "shelter", b".": "space-weather"}
_MICE = (b"'", b"`", b"\x1c", b"\x1d")
_OBJECT_HEAD = 9 + 1 + 7                              # name, "*" or "_", timestamp: the position follows
_ITEM_NAME = range(3, 10)                             # where the "!" or "_" that ends an item's name can be
_BANG_LIMIT = 40                                      # the "!" of a position may be anywhere up to the 40th character (a digipeater of the X1J kind puts its own text first; deprecated since 2012, still read)
_AGRELO = re.compile(r"%(\d{3})%(\d)")
_ITEM_SPLIT = re.compile(r"[,\r\n]+")


def _named(name: str, position: Position) -> Position:
    """The position of an object or item whose name is a frequency (`145.775-A`, freqspec.txt) with that frequency, and the fields of the comment taken off it."""
    frequency, comment = named_frequency(name, position.frequency, position.comment)
    return position if frequency is position.frequency else replace(position, frequency=frequency, comment=comment)


def _object(body: bytes, now: datetime) -> ObjectReport:
    if len(body) <= _OBJECT_HEAD:
        raise PositionError("object too short")
    status = body[9:10]
    if status not in (b"*", b"_"):
        raise PositionError("object status is neither * nor _")
    name = decode_text(body[:9]).rstrip(" ")
    position = _named(name, parse_position(body[10:], now))
    return ObjectReport(name, status == b"*", position, position.timestamp)


def _item(body: bytes, now: datetime) -> ItemReport:
    ends = [i for i in _ITEM_NAME if body[i:i + 1] in (b"!", b"_")]
    if not ends:
        raise PositionError("item name has no ! or _ after three to nine characters")
    end = ends[0]
    name = decode_text(body[:end])
    return ItemReport(name, body[end:end + 1] == b"!", _named(name, parse_position(body[end + 1:], now)))


def _status(body: bytes, now: datetime) -> Status:
    if len(body) >= 7 and body[:6].isdigit() and body[6:7] == b"z":
        text, frequency = split_frequency(decode_text(body[7:]).strip())
        return Status(text, resolve_timestamp(body[:7], now), frequency=frequency)
    text = decode_text(body)
    locator, rest = split_locator(text)                  # (a report with a locator has no timestamp)
    text, frequency = split_frequency((rest if locator else text).strip())
    return Status(text, None, locator, frequency)


def _capabilities(info: bytes) -> Other:
    """The items of a station's capabilities, TOKEN or TOKEN=VALUE separated by commas."""
    text = decode_text(info)
    items: dict[str, str] = {}
    for piece in _ITEM_SPLIT.split(text[1:]):
        token, _, value = piece.strip().partition("=")
        if token:
            items[token] = value
    return Other("capabilities", text, items=items)


def _agrelo(info: bytes) -> Other:
    text = decode_text(info)
    found = _AGRELO.match(text)
    return Other("agrelo-df", text, items=None if found is None else {"bearing": found.group(1), "quality": found.group(2)})


def _weather_report(info: bytes, now: datetime) -> Other:
    """A positionless weather report: the observation, and the time of its MMDDhhmm when that is a date."""
    text = decode_text(info)
    try:
        at = resolve_mdhm(text[1:9], now)
    except PositionError:
        at = None
    return Other("weather", text, parse_report(info), timestamp=at)


def _locator_beacon(body: bytes) -> Position:
    found = split_beacon(decode_text(body))
    if found is None:
        raise PositionError("no Maidenhead locator")
    locator, comment = found
    return Position(locator.lat, locator.lon, locator.symbol_table, locator.symbol_code, comment.strip())


def _nmea(info: bytes, source: str, destination: str, now: datetime) -> Decoded:
    if info[:5] == b"$ULTW":                          # an Ultimeter 2000's raw data: the format is not in the specification
        return Other("weather", decode_text(info))
    return parse_nmea(info, source, destination, now) or Other("nmea", decode_text(info))


def _position(info: bytes, source: str, destination: str, now: datetime) -> Decoded:
    if info[:2] == b"!!":                              # an Ultimeter 2000's raw data
        return Other("weather", decode_text(info))
    return parse_position(info[1:], now, messaging=info[:1] in (b"=", b"@"))


def _telemetry(info: bytes, source: str, destination: str, now: datetime) -> Decoded:
    text = decode_text(info)
    return parse_telemetry(text) or Other("telemetry", text)


def _mice(info: bytes, source: str, destination: str, now: datetime) -> Decoded:
    return parse_mice(destination, info[1:], now)


def _message(info: bytes, source: str, destination: str, now: datetime) -> Decoded:
    return parse_message(info[1:])


def _object_of(info: bytes, source: str, destination: str, now: datetime) -> Decoded:
    return _object(info[1:], now)


def _item_of(info: bytes, source: str, destination: str, now: datetime) -> Decoded:
    return _item(info[1:], now)


def _status_of(info: bytes, source: str, destination: str, now: datetime) -> Decoded:
    return _status(info[1:], now)


def _beacon_of(info: bytes, source: str, destination: str, now: datetime) -> Decoded:
    return _locator_beacon(info[1:])


def _weather_of(info: bytes, source: str, destination: str, now: datetime) -> Decoded:
    return _weather_report(info, now)


def _capabilities_of(info: bytes, source: str, destination: str, now: datetime) -> Decoded:
    return _capabilities(info)


def _agrelo_of(info: bytes, source: str, destination: str, now: datetime) -> Decoded:
    return _agrelo(info)


_Handler = Callable[[bytes, str, str, datetime], Decoded]
# The decoder of each data type identifier that has one; the others are `Other` with the word of `_OTHER_KINDS`.
_HANDLERS: dict[bytes, _Handler] = {
    **dict.fromkeys((b"!", b"=", b"/", b"@"), _position), **dict.fromkeys(_MICE, _mice), b":": _message, b";": _object_of, b")": _item_of, b">": _status_of, b"[": _beacon_of, b"_": _weather_of,
    b"$": _nmea, b"T": _telemetry, b"<": _capabilities_of, b"%": _agrelo_of}


def _dispatch(first: bytes, info: bytes, source: str, destination: str, now: datetime) -> Decoded:
    handler = _HANDLERS.get(first)
    if handler is not None:
        return handler(info, source, destination, now)
    return Other(_OTHER_KINDS.get(first, "unknown"), decode_text(info))


def _bang_position(info: bytes, now: datetime) -> Position | None:
    """The position of a `!` report that has text in front of it (up to the 40th character), the text kept as the start of the comment; None when there is none. The APRS 1.2 corrections call this
    X1J exception deprecated (2012: the `!` belongs at the start only); old digipeaters still send it, so it is read and never sent."""
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
    """What the information field `info` of a packet from `source` to `destination` says; `now` resolves timestamps. `source` gives a raw NMEA tracker its symbol when its destination does not."""
    if not info:
        return Undecoded("empty information field", "")
    try:
        decoded = _dispatch(info[:1], info, source, destination, now)
        if isinstance(decoded, Other) and info[:1] not in (b"}", b"{", b","):          # (test data is never a position)
            return _bang_position(info, now) or decoded
        return decoded
    except (PositionError, MicEError, MessageError, NmeaError) as e:
        return Undecoded(str(e), info.decode("latin-1"))
    except (ValueError, IndexError) as e:
        return Undecoded(f"malformed field ({type(e).__name__}: {e})", info.decode("latin-1"))
