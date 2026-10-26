"""The packets of the Dummy radio's world (dummyscene.py), as AX.25 frames: the information fields of the kinds of station it makes up, and the way a digipeater repeats a frame. Every call is made up (see
dummyscene.py); nothing here knows a clock or a radio."""
import math
from datetime import datetime

from neoaprs import ax25
from neoaprs.aprsmessage import format_ack, format_message
from neoaprs.aprsmiceout import mice_packet
from neoaprs.aprsposition import compressed_position, uncompressed_position
from neoaprs.units import KNOT_KMH

PATH = "WIDE1-1,WIDE2-1"                    # what a mobile asks for: the nearest fill-in digipeater, then a wide one


def address(text: str) -> ax25.Address:
    return ax25.Address.parse(text)


def air(source: str, info: bytes, path: str = PATH, destination: str = "APRS") -> ax25.Frame:
    """A frame as a station sends it: `path` is the digipeaters it asks for, none of them used yet."""
    return ax25.Frame(address(destination), address(source), tuple(address(p) for p in path.split(",") if p), info=info)


def repeated(frame: ax25.Frame, digipeater: str) -> ax25.Frame:
    """The frame as `digipeater` sends it again: it takes the place of the first digipeater the frame asked for, marked as used (`Q2DIG-2*,WIDE2-1`); a wide digipeater (WIDEn-N with N above 1) is counted down instead."""
    asked = list(frame.path)
    used = address(digipeater + "*")
    if asked and asked[0].ssid > 1:
        asked[0] = ax25.Address(asked[0].call, asked[0].ssid - 1)
        return ax25.Frame(frame.destination, frame.source, (used, *asked), info=frame.info)
    return ax25.Frame(frame.destination, frame.source, (used, *asked[1:]), info=frame.info)


def _motion(course: int, speed_kmh: float) -> str:
    return f"{course % 360 or 360:03d}/{min(999, round(speed_kmh / KNOT_KMH)):03d}"


def fixed(lat: float, lon: float, symbol: str, comment: str, messaging: bool = False) -> bytes:
    """A position of a station that stays: `!` or, for one that takes messages, `=`."""
    return (b"=" if messaging else b"!") + uncompressed_position(lat, lon, symbol[0], symbol[1]) + comment.encode("ascii")


def walking(lat: float, lon: float, symbol: str, comment: str, course: int, speed_kmh: float) -> bytes:
    """A position with the course and speed after it, from a station that takes messages."""
    return b"=" + uncompressed_position(lat, lon, symbol[0], symbol[1]) + _motion(course, speed_kmh).encode("ascii") + comment.encode("ascii")


def compressed(lat: float, lon: float, symbol: str, comment: str, course: int, speed_kmh: float) -> bytes:
    """A compressed position with course and speed, from a station that takes messages."""
    return b"=" + compressed_position(lat, lon, symbol[0], symbol[1], course, speed_kmh) + comment.encode("ascii")


def mice(lat: float, lon: float, symbol: str, comment: str, course: int, speed_kmh: float) -> tuple[str, bytes]:
    """The destination and the information field of a Mic-E position."""
    return mice_packet(lat, lon, symbol[0], symbol[1], course, speed_kmh, comment)


def weather(lat: float, lon: float, comment: str, direction: int, wind_kmh: float, gust_kmh: float, temp_c: float, rain_hour_mm: float, rain_day_mm: float, humidity: int, hpa: float) -> bytes:
    """A weather station's position with the weather symbol and its fields: wind in miles an hour, temperature in degrees F, rain in hundredths of an inch, pressure in tenths of a hPa."""
    def mph(kmh: float) -> int:
        return round(kmh / 1.609344)

    def hundredths(mm: float) -> int:
        return round(mm / 0.254)

    f = round(temp_c * 9 / 5 + 32)
    temp = f"t{f:03d}" if f >= 0 else f"t-{-f:02d}"
    fields = f"{direction % 360:03d}/{mph(wind_kmh):03d}g{mph(gust_kmh):03d}{temp}r{hundredths(rain_hour_mm):03d}p{hundredths(rain_day_mm):03d}P{hundredths(rain_day_mm):03d}h{humidity % 100:02d}b{round(hpa * 10):05d}"
    return b"!" + uncompressed_position(lat, lon, "/", "_") + (fields + comment).encode("ascii")


def object_report(name: str, now: datetime, lat: float, lon: float, symbol: str, comment: str) -> bytes:
    """A live object: `;NAME     *DDHHMMz` and its position."""
    return b";" + name.ljust(9).encode("ascii") + b"*" + now.strftime("%d%H%M").encode("ascii") + b"z" + uncompressed_position(lat, lon, symbol[0], symbol[1]) + comment.encode("ascii")


def status(text: str) -> bytes:
    return b">" + text.encode("ascii")


def bulletin(slot: str, text: str) -> bytes:
    return b":" + format_message(slot, text)


def message(to: str, text: str, msg_id: str | None = None) -> bytes:
    return b":" + format_message(to, text, msg_id)


def ack(to: str, msg_id: str) -> bytes:
    return b":" + format_ack(to, msg_id)


def is_position(info: bytes) -> bool:
    """Whether the information field is a position report (a beacon): the identifiers `! = / @` and Mic-E's two."""
    return info[:1] in (b"!", b"=", b"/", b"@", b"`", b"'")


def cosine_day(now: datetime, peak_hour: float) -> float:
    """1 at `peak_hour` (UTC) of the day, -1 twelve hours away: the shape of a day's temperature."""
    hour = now.hour + now.minute / 60
    return math.cos((hour - peak_hour) / 24 * 2 * math.pi)
