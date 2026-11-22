"""APRS on-air units (knots, miles, feet, inches, degrees F) against the metric ones kept.

Metric: km/h, km, metres, millimetres, degrees C. The base-91 numbers of the compressed forms
are read and written here too. Pure code.
"""

KNOT_KMH = 1.852  # km/h per knot
NAUTICAL_MILE_KM = 1.852
MILE_KM = 1.609344  # a statute mile; also a mile an hour in km/h
FOOT_M = 0.3048
INCH_MM = 25.4
MS_KMH = 3.6  # km/h per metre a second (gpsd)


def fahrenheit_to_celsius(degrees_f: float) -> float:
    return (degrees_f - 32) * 5 / 9


BASE91_ZERO = 33  # the character `!`, the digit 0 of a base-91 number
BASE91_LAST = 123  # the character `{`, the digit 90


def base91(data: bytes) -> int:
    """Return the number the base-91 digits `!` to `{` of `data` write, most significant first.

    Raise ValueError for a byte that is no digit.
    """
    value = 0
    for byte in data:
        if not BASE91_ZERO <= byte <= BASE91_LAST:
            raise ValueError(f"byte 0x{byte:02X} is not a base-91 digit")
        value = value * 91 + byte - BASE91_ZERO
    return value


def base91_text(value: int, digits: int) -> bytes:
    """Return `digits` base-91 characters (33 to 123) of a number; a large one keeps low digits."""
    text = bytearray()
    for _ in range(digits):
        value, digit = divmod(value, 91)
        text.append(BASE91_ZERO + digit)
    return bytes(reversed(text))
