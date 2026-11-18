"""A jetvision Radarcape's own list of its aircraft, `aircraftlist.json` (asked with `knownposonly=1`): a JSON array of objects, one for each aircraft, read into the layer's things as readsb.py reads
readsb's file; `radarcape_url` says where it is asked. No I/O.

The fields, by jetvision's own description (wiki.jetvision.de, Radarcape:Software_Features): `hex` the ICAO address; `fli` the flight; `lat`, `lon`; `lla` the age of the last position in seconds (null when not
known: then `uti`, seconds since 1970 of the last message, gives the time); `alt` barometric feet; `vrt` the vertical rate in feet a minute; `spd` knots; `trk` the true track; `gda` G (or g, TIS-B) on the ground, A (or a) in the air; `alr` 3 a
permanent alert (7500, 7600, 7700) and `squ` the squawk; `reg` the registration; `typ` the ICAO type designator; `cat` the emitter category; `org` and `dst` the ICAO codes of the airports of departure and destination (a code is kept when it is four letters
or digits, upper case; the list does not carry the airports' names). `dis` is km or nautical miles by the device's own setting and is
not read.

An aircraft on the ground, a vehicle or an obstacle (a `cat` that begins with C), one without a position and one whose position is a day old or older are left out. A field that is null, missing, a string where
a number is meant or not finite is none; a row that cannot be read is passed over and never loses the others. The array is read one item at a time (readsb.loads)."""
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from .clock import from_unix
from .layerthing import RADARCAPE_PLACE, Thing
from .readsb import ALTITUDE_M_RANGE, EMERGENCY_SQUAWKS, FEET_M, KNOT_KMH, SEEN_MAX_SEC, SPEED_KMH_RANGE, converted, host_port, is_whole_address, loads, number, text_of, vertical_ms

AIRPORT_CODE_LENGTH = 4
PERMANENT_ALERT = 3                                          # `alr`: a squawk of 7500, 7600 or 7700


def _airport(value: Any) -> str:
    """An airport's ICAO code, upper case: four ASCII letters or digits once trimmed; anything else is none (looked at as it came: a letter that only upper-casing would make ASCII is no code)."""
    code = value.strip() if isinstance(value, str) else ""
    return code.upper() if len(code) == AIRPORT_CODE_LENGTH and code.isascii() and code.isalnum() else ""


def _squawk(value: Any) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:04d}"
    return text_of(value)


def _at(row: dict[str, Any], received_at: datetime) -> datetime | None:
    """The time of the position: `lla` seconds before the answer came; without it the time of the last message (`uti`), never after the answer; without either the answer's; None when a day old or older."""
    age = number(row.get("lla"))
    if age is None and (sent := number(row.get("uti"))) is not None:
        age = (received_at - from_unix(sent)).total_seconds()
    age = max(age or 0.0, 0.0)
    return None if age >= SEEN_MAX_SEC else received_at - timedelta(seconds=age)


def _thing(row: Any, received_at: datetime) -> Thing | None:
    """One aircraft of the list, or None for one that is not shown."""
    if not isinstance(row, dict) or not (id := text_of(row.get("hex")).lower()):
        return None
    lat, lon = number(row.get("lat")), number(row.get("lon"))
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    category = text_of(row.get("cat")).upper()
    if text_of(row.get("gda")).upper() == "G" or category.startswith("C"):
        return None
    at = _at(row, received_at)
    if at is None:
        return None
    metres, speed, track = converted(row.get("alt"), FEET_M, ALTITUDE_M_RANGE), converted(row.get("spd"), KNOT_KMH, SPEED_KMH_RANGE), number(row.get("trk"))
    designator = text_of(row.get("typ")).upper()
    return Thing(id=id, lat=lat, lon=lon, at=at, heading_deg=None if track is None else int(round(track)) % 360, speed_kmh=None if speed is None else round(speed, 1),
                 name=text_of(row.get("fli")), emergency=number(row.get("alr")) == PERMANENT_ALERT or _squawk(row.get("squ")) in EMERGENCY_SQUAWKS,
                 altitude_m=None if metres is None else int(round(metres)), vertical_ms=vertical_ms(row.get("vrt")), registration=text_of(row.get("reg")), type=designator, category=category, designator=designator,
                 destination=_airport(row.get("dst")), origin=_airport(row.get("org")))


def read_aircraft(body: bytes, received_at: datetime) -> list[Thing] | None:
    """The aircraft of a Radarcape's list that are shown, one for each `hex` (the newest position); None for anything that is not a JSON array of objects (an array with items and not one object among them is
    not the Radarcape's list). The ages are counted from `received_at`, the daemon's own clock."""
    try:
        listed = loads(body)
    except (ValueError, RecursionError, StopIteration):
        return None
    if not isinstance(listed, list) or (listed and not any(isinstance(row, dict) for row in listed)):
        return None
    kept: dict[str, Thing] = {}
    for row in listed:
        try:
            thing = _thing(row, received_at)
        except (OverflowError, ValueError):                 # (a number or a time out of range: that one row is passed over)
            continue
        if thing is not None and (thing.id not in kept or kept[thing.id].at < thing.at):
            kept[thing.id] = thing
    return list(kept.values())


def radarcape_url(address: str) -> str | None:
    """Where a Radarcape's list is asked: a whole http or https address as typed (one that names no place, as `http://192.168.1.160/`, is given the Radarcape's own); a name or address, or `host:port`, with
    the Radarcape's own place; None for an empty address (not looked for)."""
    value = address.strip()
    if not value:
        return None
    if is_whole_address(value):
        whole = urlsplit(value)
        return value if whole.path not in ("", "/") or whole.query or whole.fragment else f"{whole.scheme.lower()}://{whole.netloc}{RADARCAPE_PLACE}"
    host, port = host_port(value)
    return f"http://{host}{'' if port in (None, 80) else f':{port}'}{RADARCAPE_PLACE}"
