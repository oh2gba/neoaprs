"""readsb's JSON, the one form of every aircraft source: the `aircraft.json` of an own receiver (readsb, dump1090, tar1090: `now` in seconds and the list `aircraft`) and the answer of adsb.fi and adsb.lol
(`now` in milliseconds and the list `ac`). `read_aircraft` turns it into the layer's things; `receiver_urls` says where an own receiver keeps the file. No I/O.

An aircraft on the ground (`alt_baro` "ground") and a vehicle or an obstacle (a `category` that begins with C) are left out, and so is one without a position or with one a day old or older.

The lists of the answer are read one item at a time (`loads`), so that a long answer read on a thread of its own lets the daemon's loop run between the items."""
import json
import re
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from .clock import from_unix
from .layerthing import AIRCRAFT_HOST, AIRCRAFT_PLACES, AIRCRAFT_PORTS, Thing

FEET_M = 0.3048
KNOT_KMH = 1.852
EMERGENCY_SQUAWKS = frozenset({"7500", "7600", "7700"})      # unlawful interference, radio failure, emergency
MILLISECONDS_FROM = 1e11                                     # a `now` above this is in milliseconds (the services), below it in seconds (a receiver's file)
TEXT_MAX = 64                                                # the longest flight, registration or type kept
SEEN_MAX_SEC = 86400.0                                       # a position older than this is taken as none
_SPACE = re.compile(r"[ \t\n\r]*")
# json's own scanner of one value: (text, where it begins) -> (the value, where it ends)
_SCAN: Callable[[str, int], tuple[Any, int]] = json.JSONDecoder().scan_once     # type: ignore[attr-defined]


def _after_space(text: str, at: int) -> int:
    found = _SPACE.match(text, at)
    return at if found is None else found.end()


def _list(text: str, at: int) -> tuple[list[Any], int]:
    """The JSON list that begins at `at`, read item by item, and where it ends."""
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
    """What `json.loads` gives for `body`, the lists of a top-level object read item by item (each item by json's own scanner); ValueError for what is not JSON."""
    text = body.decode(json.detect_encoding(body), "surrogatepass")
    at = _after_space(text, 0)
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


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value == value and abs(value) != float("inf") else None


def _text(value: Any) -> str:
    return "".join(c for c in value.strip() if c.isprintable())[:TEXT_MAX] if isinstance(value, str) else ""


def _heading(aircraft: dict[str, Any]) -> int | None:
    """Where the mark points: the track over the ground, else the true heading, else the magnetic one."""
    for key in ("track", "true_heading", "mag_heading"):
        if (degrees := _number(aircraft.get(key))) is not None:
            return int(round(degrees)) % 360
    return None


def _altitude_m(aircraft: dict[str, Any]) -> int | None:
    feet = _number(aircraft.get("alt_baro"))
    if feet is None:
        feet = _number(aircraft.get("alt_geom"))
    return None if feet is None else int(round(feet * FEET_M))


def _emergency(aircraft: dict[str, Any]) -> bool:
    said = aircraft.get("emergency")
    return (isinstance(said, str) and said.strip().lower() not in ("", "none")) or _text(aircraft.get("squawk")) in EMERGENCY_SQUAWKS


def _thing(aircraft: Any, base: datetime) -> Thing | None:
    """One aircraft of the list, or None for one that is not shown (no position, on the ground, a vehicle or an obstacle, not an object with a `hex`)."""
    if not isinstance(aircraft, dict) or not (id := _text(aircraft.get("hex")).lower()):
        return None
    lat, lon = _number(aircraft.get("lat")), _number(aircraft.get("lon"))
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    if aircraft.get("alt_baro") == "ground" or _text(aircraft.get("category")).upper().startswith("C"):
        return None
    seen = _number(aircraft.get("seen_pos"))
    if seen is not None and seen >= SEEN_MAX_SEC:
        return None
    speed = _number(aircraft.get("gs"))
    return Thing(id=id, lat=lat, lon=lon, at=base - timedelta(seconds=max(seen or 0.0, 0.0)), heading_deg=_heading(aircraft),
                 speed_kmh=None if speed is None or speed < 0 else round(speed * KNOT_KMH, 1), name=_text(aircraft.get("flight")), emergency=_emergency(aircraft),
                 altitude_m=_altitude_m(aircraft), registration=_text(aircraft.get("r")), type=_text(aircraft.get("desc")) or _text(aircraft.get("t")))


def read_aircraft(body: bytes, received_at: datetime | None = None) -> list[Thing] | None:
    """The aircraft of readsb's JSON that are shown, one for each `hex` (the newest position); None for anything that is not that JSON (an object with a number `now` and a list `aircraft` or `ac`).

    The time of a position is `seen_pos` seconds before `received_at` when it is given (the daemon's own clock: a receiver whose clock is wrong does not age its aircraft away), else before the answer's `now`."""
    try:
        data = loads(body)
    except (ValueError, RecursionError, StopIteration):
        return None
    if not isinstance(data, dict):
        return None
    listed = data.get("aircraft") if isinstance(data.get("aircraft"), list) else data.get("ac")
    now = _number(data.get("now"))
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
        except (OverflowError, ValueError):                 # (a time out of the calendar's range: that one row is passed over)
            continue
        if thing is not None and (thing.id not in kept or kept[thing.id].at < thing.at):
            kept[thing.id] = thing
    return list(kept.values())


def _host_port(address: str) -> tuple[str, int | None]:
    """`host` or `host:port` (an IPv6 address in brackets) as the host, as an address writes it, and the port (None when none is given)."""
    host, colon, port = address.rpartition(":") if not address.endswith("]") else ("", "", address)
    if not colon or not (port.isascii() and port.isdigit()):
        host, number = address, None
    else:
        number = int(port)
    return host.replace("%", "%25") if host.startswith("[") and "%25" not in host else host, number


def receiver_urls(address: str) -> list[str]:
    """Where an own aircraft receiver's file is tried, in order: a whole http or https address as typed; on a `host:port` each of the known places on that port; on a bare host each of them on port 80 and
    then on 8080; empty, the same on this computer."""
    value = address.strip()
    if value.startswith(("http://", "https://")):
        return [value]
    host, port = _host_port(value or AIRCRAFT_HOST)
    ports = (port,) if port is not None else AIRCRAFT_PORTS
    return [f"http://{host}{'' if number == 80 else f':{number}'}{place}" for number in ports for place in AIRCRAFT_PLACES]
