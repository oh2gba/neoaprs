"""readsb's JSON, the one form of every aircraft source (own receiver and adsb.fi / adsb.lol).

Ground traffic and rows without a recent position are left out. Lists are read one item at a
time (`loads`), so a long answer read on a thread lets the loop run.
"""

import json
import math
import re
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from .clock import from_unix
from .layerthing import AIRCRAFT_HOST, AIRCRAFT_PLACES, AIRCRAFT_PORTS, Thing
from .units import FOOT_M, KNOT_KMH

FPM_MS = 0.00508  # one foot a minute in m/s
EMERGENCY_SQUAWKS = frozenset({"7500", "7600", "7700"})
# a `now` above this is in milliseconds, below it in seconds
MILLISECONDS_FROM = 1e11
TEXT_MAX = 64
SEEN_MAX_SEC = 86400.0
# a value outside its range is taken as none
SPEED_KMH_RANGE = (0.0, 4000.0)
ALTITUDE_M_RANGE = (-1000.0, 40000.0)
VERTICAL_MS_RANGE = (-150.0, 150.0)
_SPACE = re.compile(r"[ \t\n\r]*")
# json's own scanner of one value
_SCAN: Callable[[str, int], tuple[Any, int]] = json.JSONDecoder().scan_once  # type: ignore[attr-defined]


def _after_space(text: str, at: int) -> int:
    found = _SPACE.match(text, at)
    return at if found is None else found.end()


def _list(text: str, at: int) -> tuple[list[Any], int]:
    """Return the JSON list that begins at `at`, read item by item, and where it ends."""
    items: list[Any] = []
    at = _after_space(text, at + 1)
    if text.startswith("]", at):
        return items, at + 1
    while True:
        item, at = _SCAN(text, at)
        items.append(item)
        at = _after_space(text, at)
        if text.startswith(",", at):
            at = _after_space(text, at + 1)
        elif text.startswith("]", at):
            return items, at + 1
        else:
            raise ValueError("not a JSON list")


def loads(body: bytes) -> Any:
    """Return what `json.loads` gives, reading top-level lists item by item (ValueError if not)."""
    text = body.decode(json.detect_encoding(body), "surrogatepass")
    at = _after_space(text, 0)
    if text.startswith("[", at):
        items, at = _list(text, at)
        if _after_space(text, at) != len(text):
            raise ValueError("more after the JSON")
        return items
    if not text.startswith("{", at):
        return json.loads(text)
    data: dict[str, Any] = {}
    at = _after_space(text, at + 1)
    if text.startswith("}", at):
        at += 1
    else:
        while True:
            if not text.startswith('"', at):
                raise ValueError("not a JSON object")
            key, at = _SCAN(text, at)
            at = _after_space(text, at)
            if not text.startswith(":", at):
                raise ValueError("not a JSON object")
            at = _after_space(text, at + 1)
            data[key], at = _list(text, at) if text.startswith("[", at) else _SCAN(text, at)
            at = _after_space(text, at)
            if text.startswith(",", at):
                at = _after_space(text, at + 1)
            elif text.startswith("}", at):
                at += 1
                break
            else:
                raise ValueError("not a JSON object")
    if _after_space(text, at) != len(text):
        raise ValueError("more after the JSON")
    return data


def number(value: Any) -> float | None:
    """Return a JSON number that is finite; None for anything else (null, string, boolean)."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        found = float(value)
    except OverflowError:
        return None
    return found if math.isfinite(found) else None


def converted(value: Any, factor: float, within: tuple[float, float]) -> float | None:
    """Return a JSON number times `factor`; None if none, not finite or outside `within`."""
    found = number(value)
    if found is None:
        return None
    result = found * factor
    return result if within[0] <= result <= within[1] else None


def text_of(value: Any) -> str:
    """Return a JSON string trimmed, unprintable characters removed, at most TEXT_MAX; else ""."""
    return "".join(c for c in value.strip() if c.isprintable())[:TEXT_MAX] if isinstance(value, str) else ""


def _heading(aircraft: dict[str, Any]) -> int | None:
    """Return where the mark points: ground track, else true heading, else magnetic heading."""
    for key in ("track", "true_heading", "mag_heading"):
        if (degrees := number(aircraft.get(key))) is not None:
            return int(round(degrees)) % 360
    return None


def _track(aircraft: dict[str, Any]) -> int | None:
    """Return the ground track only: a heading is where the nose points, not where it goes."""
    degrees = number(aircraft.get("track"))
    return None if degrees is None else int(round(degrees)) % 360


def _altitude_m(aircraft: dict[str, Any]) -> int | None:
    metres = converted(aircraft.get("alt_baro"), FOOT_M, ALTITUDE_M_RANGE)
    if metres is None:
        metres = converted(aircraft.get("alt_geom"), FOOT_M, ALTITUDE_M_RANGE)
    return None if metres is None else int(round(metres))


def vertical_ms(rate: Any) -> float | None:
    """Return a climb rate in feet a minute as m/s, one decimal; None if none or out of range."""
    metres = converted(rate, FPM_MS, VERTICAL_MS_RANGE)
    # + 0.0: a small descent is level, not -0.0
    return None if metres is None else round(metres, 1) + 0.0


def _vertical(aircraft: dict[str, Any]) -> float | None:
    found = vertical_ms(aircraft.get("baro_rate"))
    return vertical_ms(aircraft.get("geom_rate")) if found is None else found


def _emergency(aircraft: dict[str, Any]) -> bool:
    said = aircraft.get("emergency")
    return (isinstance(said, str) and said.strip().lower() not in ("", "none")) or text_of(
        aircraft.get("squawk")
    ) in EMERGENCY_SQUAWKS


def _thing(aircraft: Any, base: datetime) -> Thing | None:
    """Return one aircraft of the list, or None for one that is not shown."""
    if not isinstance(aircraft, dict) or not (id := text_of(aircraft.get("hex")).lower()):
        return None
    lat, lon = number(aircraft.get("lat")), number(aircraft.get("lon"))
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    if aircraft.get("alt_baro") == "ground" or text_of(aircraft.get("category")).upper().startswith("C"):
        return None
    seen = number(aircraft.get("seen_pos"))
    if seen is not None and seen >= SEEN_MAX_SEC:
        return None
    speed = converted(aircraft.get("gs"), KNOT_KMH, SPEED_KMH_RANGE)
    return Thing(
        id=id,
        lat=lat,
        lon=lon,
        at=base - timedelta(seconds=max(seen or 0.0, 0.0)),
        heading_deg=_heading(aircraft),
        course_deg=_track(aircraft),
        speed_kmh=None if speed is None else round(speed, 1),
        name=text_of(aircraft.get("flight")),
        emergency=_emergency(aircraft),
        altitude_m=_altitude_m(aircraft),
        vertical_ms=_vertical(aircraft),
        registration=text_of(aircraft.get("r")),
        type=text_of(aircraft.get("desc")) or text_of(aircraft.get("t")),
        category=text_of(aircraft.get("category")).upper(),
        designator=text_of(aircraft.get("t")).upper(),
    )


def read_aircraft(body: bytes, received_at: datetime | None = None) -> list[Thing] | None:
    """Return the shown aircraft, one per `hex` (the newest); None if not readsb's JSON.

    Positions are aged from `received_at` (the daemon's clock, not a receiver's), else from `now`.
    """
    try:
        data = loads(body)
    except (ValueError, RecursionError, StopIteration):
        return None
    if not isinstance(data, dict):
        return None
    listed = data.get("aircraft") if isinstance(data.get("aircraft"), list) else data.get("ac")
    now = number(data.get("now"))
    if not isinstance(listed, list) or now is None:
        return None
    if received_at is not None:
        base = received_at
    else:
        try:
            base = from_unix(now / 1000 if now > MILLISECONDS_FROM else now)
        except (OverflowError, ValueError, OSError):
            return None
    kept: dict[str, Thing] = {}
    for aircraft in listed:
        try:
            thing = _thing(aircraft, base)
        except (OverflowError, ValueError):  # that row is skipped
            continue
        if thing is not None and (thing.id not in kept or kept[thing.id].at < thing.at):
            kept[thing.id] = thing
    return list(kept.values())


def host_port(address: str) -> tuple[str, int | None]:
    """Return the host of `host` or `host:port` (IPv6 in brackets) as written, and the port."""
    host, colon, port = address.rpartition(":") if not address.endswith("]") else ("", "", address)
    if not colon or not (port.isascii() and port.isdigit()):
        host, number = address, None
    else:
        number = int(port)
    return host.replace("%", "%25") if host.startswith("[") and "%25" not in host else host, number


def is_whole_address(value: str) -> bool:
    """Return whether an address is typed whole, with its http or https (in any case)."""
    return value.lower().startswith(("http://", "https://"))


def receiver_urls(address: str) -> list[str]:
    """Return where a receiver's file is tried, in order: the address as typed, or each place."""
    value = address.strip()
    if is_whole_address(value):
        return [value]
    host, port = host_port(value or AIRCRAFT_HOST)
    ports = (port,) if port is not None else AIRCRAFT_PORTS
    return [
        f"http://{host}{'' if number == 80 else f':{number}'}{place}" for number in ports for place in AIRCRAFT_PLACES
    ]
