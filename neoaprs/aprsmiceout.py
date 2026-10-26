"""A position as a Mic-E packet (the other direction of aprsmice.py): the destination address that carries the latitude, and the information field that carries the longitude, speed, course and symbol. Used by the
Dummy radio (dummyscene.py) to make traffic that the parser reads like a car's tracker."""
from neoaprs.aprsposition import HUNDREDTHS_PER_DEGREE
from neoaprs.units import KNOT_KMH

OFF_DUTY = (1, 1, 1)                 # the standard message bits of "Off Duty", which trackers send as a rule (index 7 of aprsmice's list); the three bits of the first three destination characters


def _lat_digits(lat: float) -> tuple[list[int], bool]:
    """The six digits DDMMHH of the latitude (hundredths of a minute) and whether it is north."""
    total = round(abs(lat) * HUNDREDTHS_PER_DEGREE)
    degrees, rest = divmod(total, HUNDREDTHS_PER_DEGREE)
    minutes, hundredths = divmod(rest, 100)
    return [degrees // 10, degrees % 10, minutes // 10, minutes % 10, hundredths // 10, hundredths % 10], lat >= 0


def _destination(lat: float, lon_deg: int, west: bool, message: tuple[int, int, int]) -> str:
    """Each digit is a letter P-Y instead (digit + 'P') when its bit is set: the message bits for the first three, then north, the longitude offset (100 degrees or more, or under 10) and west."""
    digits, north = _lat_digits(lat)
    offset = lon_deg < 10 or lon_deg >= 100
    bits = [*message, int(north), int(offset), int(west)]
    return "".join(chr(ord("P" if bit else "0") + digit) for digit, bit in zip(digits, bits))


def _longitude(lon: float) -> tuple[bytes, int]:
    """The three bytes of the longitude (degrees, minutes, hundredths of a minute, each plus 28, with the offsets of the specification) and the whole degrees."""
    total = round(abs(lon) * HUNDREDTHS_PER_DEGREE)
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
    course = course_deg % 360 or 360
    return bytes((knots // 10 + 28, knots % 10 * 10 + course // 100 + 28, course % 100 + 28))


def mice_packet(lat: float, lon: float, symbol_table: str, symbol_code: str, course_deg: int, speed_kmh: float, comment: str = "", message: tuple[int, int, int] = OFF_DUTY) -> tuple[str, bytes]:
    """The destination address and the information field of a Mic-E position: `` `lon speed course symbol table comment``. The comment may start with ']' and end with '=' to say a Kenwood mobile."""
    longitude, degrees = _longitude(lon)
    destination = _destination(lat, degrees, lon < 0, message)
    return destination, b"`" + longitude + _motion(course_deg, speed_kmh) + symbol_code.encode("ascii") + symbol_table.encode("ascii") + comment.encode("ascii")
