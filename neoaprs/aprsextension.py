"""Data extensions after the symbol of an uncompressed position (APRS101 ch. 7) and `!DAO!`.

`PHG`, `RNG`, `DFS`, the DF `/BRG/NRQ` report, area object `Tyy/Cxx`, the signpost `{55}`, and
`!DAO!` anywhere in a comment (APRS 1.2). Course and speed are read by aprsposition.py.
"""
import math
import re
from dataclasses import dataclass

from neoaprs.units import FOOT_M, MILE_KM, base91

# APRS 1.2: optional extra digit (A = 10) and "/" for hourly beacons; read, not kept
_PHG = re.compile(r"PHG(\d)([0-~])(\d)(\d)(?:[0-9A-Z]/)?")
_RNG = re.compile(r"RNG(\d{4})")
_DFS = re.compile(r"DFS(\d)([0-~])(\d)(\d)")
_BEARING = re.compile(r"/(\d{3})/(\d)(\d)(\d)")
_AREA = re.compile(r"(\d)(\d\d)([/1])(\d)(\d\d)")
_SIGN = re.compile(r"\{([^{}]{1,3})\}")
_LINE_DOWN_LEFT = 6
# an offset is sent as the square root of the degrees times this (areaobjects.txt)
_AREA_SCALE = 1500
_SHAPES = ("open circle", "line", "open ellipse", "open triangle", "open box", "filled circle", "line down-left", "filled ellipse", "filled triangle", "filled box")
_COLOURS = ("black", "blue", "green", "cyan", "red", "violet", "yellow", "gray", "dim black", "dim blue", "dim green", "dim cyan", "dim red", "dim violet", "dim yellow", "dim gray")


@dataclass(frozen=True, slots=True)
class Phg:
    """Power, height, gain, directivity and the range the spec's formula gives."""
    power_w: int
    height_m: float
    gain_db: int
    direction_deg: int | None
    range_km: float


@dataclass(frozen=True, slots=True)
class Dfs:
    strength: int
    height_m: float
    gain_db: int
    direction_deg: int | None


@dataclass(frozen=True, slots=True)
class DfBearing:
    """A DF report: bearing, hits (0 none, 1-8 share of samples, 9 manual), range (2^R mi), quality."""
    bearing_deg: int
    hits: int
    range_km: float
    quality: int


@dataclass(frozen=True, slots=True)
class Area:
    """An area object; offsets (degrees) run down and right from the position."""
    shape: str
    colour: str
    lat_offset_deg: float
    lon_offset_deg: float


@dataclass(frozen=True, slots=True)
class Extensions:
    phg: Phg | None = None
    range_km: float | None = None
    dfs: Dfs | None = None
    df_bearing: DfBearing | None = None
    area: Area | None = None


def _direction(code: str) -> int | None:
    return None if code == "0" or int(code) > 8 else int(code) * 45


def _height_m(code: str) -> float:
    return 10 * (1 << (ord(code) - ord("0"))) * FOOT_M


def phg_range_km(power_w: int, height_m: float, gain_db: int) -> float:
    """Return the range (km) of the spec's formula SQR(2 * HAAT * SQR((POWER / 10) * (GAIN / 2)))."""
    haat_ft = height_m / FOOT_M
    return math.sqrt(2 * haat_ft * math.sqrt(power_w / 10 * (10 ** (gain_db / 10) / 2))) * MILE_KM


def _phg(found: re.Match[str]) -> Phg:
    power, height, gain, direction = int(found.group(1)) ** 2, _height_m(found.group(2)), int(found.group(3)), _direction(found.group(4))
    return Phg(power, round(height, 1), gain, direction, round(phg_range_km(power, height, gain), 1))


def _area(found: re.Match[str]) -> Area:
    shape, lat, tens, colour, lon = int(found.group(1)), int(found.group(2)), found.group(3), int(found.group(4)), int(found.group(5))
    index = colour + (10 if tens == "1" else 0)
    lon_offset = lon * lon / _AREA_SCALE
    return Area(_SHAPES[shape], _COLOURS[index] if index < len(_COLOURS) else "unknown", lat * lat / _AREA_SCALE, -lon_offset if shape == _LINE_DOWN_LEFT else lon_offset)


def split_extension(text: str, area: bool) -> tuple[Extensions | None, str]:
    """Return the extension at the start of `text` and the rest; `area` is true for symbol `\\l`."""
    if area:
        found = _AREA.match(text)
        return (Extensions(area=_area(found)), text[found.end():]) if found else (None, text)
    if found := _PHG.match(text):
        return Extensions(phg=_phg(found)), text[found.end():]
    if found := _RNG.match(text):
        return Extensions(range_km=round(int(found.group(1)) * MILE_KM, 1)), text[found.end():]
    if found := _DFS.match(text):
        return Extensions(dfs=Dfs(int(found.group(1)), round(_height_m(found.group(2)), 1), int(found.group(3)), _direction(found.group(4)))), text[found.end():]
    return None, text


def split_sign(text: str) -> tuple[str, str | None]:
    """Split a signpost (`{55}`) from the comment; None if absent."""
    found = _SIGN.match(text)
    return (text[found.end():].strip(), found.group(1)) if found else (text, None)


def split_bearing(text: str) -> tuple[DfBearing | None, str]:
    """Split a DF report `/BRG/NRQ` from the rest."""
    found = _BEARING.match(text)
    if not found or int(found.group(1)) > 360:
        return None, text
    bearing, hits, rng, quality = int(found.group(1)), int(found.group(2)), int(found.group(3)), int(found.group(4))
    return DfBearing(bearing % 360, hits, round((1 << rng) * MILE_KM, 1), quality), text[found.end():]


def _direction_text(direction: int | None) -> str:
    return "omni" if direction is None else f"{direction}°"


def extension_lines(ext: Extensions) -> list[str]:
    """Return one short line per extension."""
    lines = []
    if ext.phg:
        p = ext.phg
        lines.append(f"PHG {p.power_w} W, {p.height_m:.0f} m, {p.gain_db} dB, {_direction_text(p.direction_deg)}, range {p.range_km:.0f} km")
    if ext.range_km is not None:
        lines.append(f"range {ext.range_km:.0f} km")
    if ext.dfs:
        d = ext.dfs
        lines.append(f"DF signal S{d.strength}, {d.height_m:.0f} m, {d.gain_db} dB, {_direction_text(d.direction_deg)}")
    if ext.df_bearing:
        b = ext.df_bearing
        lines.append(f"DF bearing {b.bearing_deg}°, range {b.range_km:.0f} km, quality {b.quality}, hits {b.hits}")
    if ext.area:
        a = ext.area
        lines.append(f"area: {a.colour} {a.shape}, {a.lat_offset_deg:g}° down, {a.lon_offset_deg:g}° right")
    return lines


_DAO = re.compile(r"!([A-Z])([\d ])([\d ])!|!([a-z])([!-{ ])([!-{ ])!")


def _dao_minutes(char: str, is_base91: bool) -> float:
    """Return the minutes one `!DAO!` byte adds (a digit: thousandths; base 91: 0-0.0099)."""
    if char == " ":
        return 0.0
    return base91(char.encode("ascii")) * 1.1 / 10000 if is_base91 else int(char) / 1000


def split_dao(text: str) -> tuple[str, tuple[float, float] | None]:
    """Return the comment without `!DAO!` and the minutes it adds; with several, the last counts."""
    found = list(_DAO.finditer(text))
    if not found:
        return text, None
    last = found[-1]
    is_base91 = last.group(4) is not None
    lat, lon = (last.group(5), last.group(6)) if is_base91 else (last.group(2), last.group(3))
    return _DAO.sub("", text).strip(), (_dao_minutes(lat, is_base91), _dao_minutes(lon, is_base91))


def with_dao(lat: float, lon: float, extra: tuple[float, float] | None) -> tuple[float, float]:
    """Return latitude and longitude refined by the `!DAO!` minutes, each away from zero."""
    if extra is None:
        return lat, lon
    return max(-90.0, min(90.0, lat + math.copysign(extra[0] / 60, lat))), max(-180.0, min(180.0, lon + math.copysign(extra[1] / 60, lon)))
