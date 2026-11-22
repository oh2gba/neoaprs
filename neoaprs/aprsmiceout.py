"""A position as a Mic-E packet (the inverse of aprsmice.py).

The destination address carries the latitude; the information field the longitude, speed, course
and symbol. Used by the Dummy radio (dummyscene.py) to make traffic like a car tracker's.
"""

from neoaprs.aprsposition import HUNDREDTHS_PER_DEGREE, north_as_360
from neoaprs.units import KNOT_KMH

MAX_LON_HUNDREDTHS = 180 * HUNDREDTHS_PER_DEGREE - 1  # Mic-E has no code for 180 degrees
# the message bits of "Off Duty" (index 7 of aprsmice's list), which trackers send as a rule
OFF_DUTY = (1, 1, 1)


def _lat_digits(lat: float) -> tuple[list[int], bool]:
    """Return the six latitude digits DDMMHH (hundredths of a minute) and whether it is north."""
    total = round(abs(lat) * HUNDREDTHS_PER_DEGREE)
    degrees, rest = divmod(total, HUNDREDTHS_PER_DEGREE)
    minutes, hundredths = divmod(rest, 100)
    return [degrees // 10, degrees % 10, minutes // 10, minutes % 10, hundredths // 10, hundredths % 10], lat >= 0


def _destination(lat: float, lon_deg: int, west: bool, message: tuple[int, int, int]) -> str:
    """Return the destination: a digit becomes a letter P-Y when its bit is set.

    The bits are message (3), north, longitude offset (100 degrees or more, or under 10), west.
    """
    digits, north = _lat_digits(lat)
    offset = lon_deg < 10 or lon_deg >= 100
    bits = [*message, int(north), int(offset), int(west)]
    return "".join(chr(ord("P" if bit else "0") + digit) for digit, bit in zip(digits, bits))


def _longitude(lon: float) -> tuple[bytes, int]:
    """Return the three longitude bytes (degrees, minutes, hundredths, +28) and whole degrees."""
    total = min(round(abs(lon) * HUNDREDTHS_PER_DEGREE), MAX_LON_HUNDREDTHS)
    degrees, rest = divmod(total, HUNDREDTHS_PER_DEGREE)
    minutes, hundredths = rest // 100, rest % 100
    if degrees < 10:
        d = degrees + 118 - 28
    elif degrees < 100:
        d = degrees
    elif degrees < 110:
        d = degrees + 8 - 28
    else:
        d = degrees - 72 - 28
    return bytes((d + 28, minutes + 28 + (60 if minutes < 10 else 0), hundredths + 28)), degrees


def _motion(course_deg: int, speed_kmh: float) -> bytes:
    knots = min(799, round(speed_kmh / KNOT_KMH))
    course = north_as_360(course_deg)
    return bytes((knots // 10 + 28, knots % 10 * 10 + course // 100 + 28, course % 100 + 28))


def mice_packet(
    lat: float,
    lon: float,
    symbol_table: str,
    symbol_code: str,
    course_deg: int,
    speed_kmh: float,
    comment: str = "",
    message: tuple[int, int, int] = OFF_DUTY,
) -> tuple[str, bytes]:
    """Return the destination and information field of a Mic-E position.

    The comment may start with ']' and end with '=' to mark a Kenwood mobile.
    """
    longitude, degrees = _longitude(lon)
    destination = _destination(lat, degrees, lon < 0, message)
    return destination, b"`" + longitude + _motion(course_deg, speed_kmh) + symbol_code.encode(
        "ascii"
    ) + symbol_table.encode("ascii") + comment.encode("ascii")
