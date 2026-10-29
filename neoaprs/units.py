"""The units APRS writes on the air (knots, statute miles, feet, inches, degrees Fahrenheit) against the metric ones the program keeps (km/h, km, metres, millimetres, degrees Celsius): the factors, each written once.
The base-91 numbers of the compressed forms (a position, a Mic-E altitude, the telemetry of a comment, a DAO) are read and written here as well.

Pure code, like the rest of the foundation."""

KNOT_KMH = 1.852                      # a knot in km/h: the speed of a position report, an object and a storm
NAUTICAL_MILE_KM = 1.852              # a nautical mile in km: the radii of a storm
MILE_KM = 1.609344                    # a statute mile in km: the range of PHG and RNG, the radius of a query's footprint, and a mile an hour in km/h (the wind of a weather report, SmartBeaconing's slope)
FOOT_M = 0.3048                       # a foot in metres: the altitude `/A=`, the height of PHG
INCH_MM = 25.4                        # an inch in millimetres: the snow of a weather report (the rain is in hundredths of an inch, 0.254 mm each)
MS_KMH = 3.6                          # a metre a second in km/h: the speed gpsd reports


def fahrenheit_to_celsius(degrees_f: float) -> float:
    return (degrees_f - 32) * 5 / 9


BASE91_ZERO = 33                      # the character `!`, the digit 0 of a base-91 number
BASE91_LAST = 123                     # the character `{`, the digit 90


def base91(data: bytes) -> int:
    """The number the base-91 digits `!` to `{` of `data` write, the first digit the most significant. Raises ValueError for a byte that is no digit."""
    value = 0
    for byte in data:
        if not BASE91_ZERO <= byte <= BASE91_LAST:
            raise ValueError(f"byte 0x{byte:02X} is not a base-91 digit")
        value = value * 91 + byte - BASE91_ZERO
    return value


def base91_text(value: int, digits: int) -> bytes:
    """The `digits` base-91 characters (33 to 123) of a whole number, the most significant first; a number too large for them keeps the low digits."""
    text = bytearray()
    for _ in range(digits):
        value, digit = divmod(value, 91)
        text.append(BASE91_ZERO + digit)
    return bytes(reversed(text))
