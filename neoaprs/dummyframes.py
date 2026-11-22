"""The packets of the Dummy radio's world (dummyscene.py) as AX.25 frames.

Information fields of the made-up kinds of station, and how a digipeater repeats a frame.
"""

import math
from datetime import datetime

from neoaprs import ax25
from neoaprs.aprsmessage import format_ack, format_message
from neoaprs.aprsmiceout import mice_packet
from neoaprs.aprsparse import MICE_CURRENT_IDS, POSITION_IDS
from neoaprs.aprsposition import compressed_position, uncompressed_position
from neoaprs.route import WIDE_PATH
from neoaprs.units import INCH_MM, KNOT_KMH, MILE_KM

PATH = WIDE_PATH  # what a mobile asks for


def address(text: str) -> ax25.Address:
    return ax25.Address.parse(text)


def air(source: str, info: bytes, path: str = PATH, destination: str = "APRS") -> ax25.Frame:
    """Return a frame as a station sends it: `path` is the digipeaters asked for, none used yet."""
    return ax25.Frame(address(destination), address(source), tuple(address(p) for p in path.split(",") if p), info=info)


def repeated(frame: ax25.Frame, digipeater: str) -> ax25.Frame:
    """Return the frame as `digipeater` repeats it: marked used, or a WIDEn-N counted down."""
    asked = list(frame.path)
    used = address(digipeater + "*")
    if asked and asked[0].ssid > 1:
        asked[0] = ax25.Address(asked[0].call, asked[0].ssid - 1)
        return ax25.Frame(frame.destination, frame.source, (used, *asked), info=frame.info)
    return ax25.Frame(frame.destination, frame.source, (used, *asked[1:]), info=frame.info)


def _motion(course: int, speed_kmh: float) -> str:
    return f"{course % 360 or 360:03d}/{min(999, round(speed_kmh / KNOT_KMH)):03d}"


def fixed(lat: float, lon: float, symbol: str, comment: str, messaging: bool = False) -> bytes:
    """Return a position of a station that stays: `!`, or `=` for one that takes messages."""
    return (
        (b"=" if messaging else b"!") + uncompressed_position(lat, lon, symbol[0], symbol[1]) + comment.encode("ascii")
    )


def walking(lat: float, lon: float, symbol: str, comment: str, course: int, speed_kmh: float) -> bytes:
    return (
        b"="
        + uncompressed_position(lat, lon, symbol[0], symbol[1])
        + _motion(course, speed_kmh).encode("ascii")
        + comment.encode("ascii")
    )


def compressed(lat: float, lon: float, symbol: str, comment: str, course: int, speed_kmh: float) -> bytes:
    return b"=" + compressed_position(lat, lon, symbol[0], symbol[1], course, speed_kmh) + comment.encode("ascii")


def mice(lat: float, lon: float, symbol: str, comment: str, course: int, speed_kmh: float) -> tuple[str, bytes]:
    return mice_packet(lat, lon, symbol[0], symbol[1], course, speed_kmh, comment)


def weather(
    lat: float,
    lon: float,
    comment: str,
    direction: int,
    wind_kmh: float,
    gust_kmh: float,
    temp_c: float,
    rain_hour_mm: float,
    rain_day_mm: float,
    humidity: int,
    hpa: float,
) -> bytes:
    """Return a weather station's position; units are mph, degrees F, 0.01 inch, 0.1 hPa."""

    def mph(kmh: float) -> int:
        return round(kmh / MILE_KM)

    def hundredths(mm: float) -> int:
        return round(mm / (INCH_MM / 100))

    f = round(temp_c * 9 / 5 + 32)
    temp = f"t{f:03d}" if f >= 0 else f"t-{-f:02d}"
    fields = f"{direction % 360:03d}/{mph(wind_kmh):03d}g{mph(gust_kmh):03d}{temp}r{hundredths(rain_hour_mm):03d}p{hundredths(rain_day_mm):03d}P{hundredths(rain_day_mm):03d}h{humidity % 100:02d}b{round(hpa * 10):05d}"
    return b"!" + uncompressed_position(lat, lon, "/", "_") + (fields + comment).encode("ascii")


def object_report(name: str, now: datetime, lat: float, lon: float, symbol: str, comment: str) -> bytes:
    """Return a live object: `;NAME     *DDHHMMz` and its position."""
    return (
        b";"
        + name.ljust(9).encode("ascii")
        + b"*"
        + now.strftime("%d%H%M").encode("ascii")
        + b"z"
        + uncompressed_position(lat, lon, symbol[0], symbol[1])
        + comment.encode("ascii")
    )


def status(text: str) -> bytes:
    return b">" + text.encode("ascii")


def bulletin(slot: str, text: str) -> bytes:
    return b":" + format_message(slot, text)


def message(to: str, text: str, msg_id: str | None = None) -> bytes:
    return b":" + format_message(to, text, msg_id)


def ack(to: str, msg_id: str) -> bytes:
    return b":" + format_ack(to, msg_id)


def is_position(info: bytes) -> bool:
    """Return whether the information field is a position report (`! = / @`, two Mic-E types)."""
    return info[:1] in (*POSITION_IDS, *MICE_CURRENT_IDS)


def cosine_day(now: datetime, peak_hour: float) -> float:
    """Return 1 at `peak_hour` (UTC), -1 twelve hours away: the shape of a day's temperature."""
    hour = now.hour + now.minute / 60
    return math.cos((hour - peak_hour) / 24 * 2 * math.pi)
