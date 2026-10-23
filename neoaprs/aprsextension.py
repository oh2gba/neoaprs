"""The data extensions that follow the symbol of an uncompressed position (APRS101, chapter 7): the station's power, height, gain and directivity (`PHGphgd`), a pre-calculated radio range (`RNGrrrr`), the
strength of a signal heard by a direction finder (`DFSshgd`), the bearing and quality of a DF report (`/BRG/NRQ`, after the course and speed) and the shape of an area object (`Tyy/Cxx` after the symbol `\\l`).

Course and speed (`CSE/SPD`) are read by aprsposition.py, which calls `split_extension` for the rest. Pure code, like the rest of the foundation."""
import math
import re
from dataclasses import dataclass

MILE_KM = 1.609344
FOOT_M = 0.3048
_PHG = re.compile(r"PHG(\d)([0-~])(\d)(\d)")
_RNG = re.compile(r"RNG(\d{4})")
_DFS = re.compile(r"DFS(\d)([0-~])(\d)(\d)")
_BEARING = re.compile(r"/(\d{3})/(\d)(\d)(\d)")
_AREA = re.compile(r"(\d)(\d\d)([/1])(\d)(\d\d)")
_SHAPES = ("open circle", "line", "open ellipse", "open triangle", "open box", "filled circle", "coloured line", "filled ellipse", "filled triangle", "filled box")
_COLOURS = ("black", "blue", "green", "cyan", "red", "violet", "yellow", "gray", "dim black", "dim blue", "dim green", "dim cyan", "dim red", "dim violet", "dim yellow", "dim gray")


@dataclass(frozen=True, slots=True)
class Phg:
    """Power, height above average terrain, antenna gain and directivity, and the radio range the spec's formula gives them (km)."""
    power_w: int
    height_m: float
    gain_db: int
    direction_deg: int | None                   # the direction of the best gain, None for an omni antenna
    range_km: float


@dataclass(frozen=True, slots=True)
class Dfs:
    """The strength of the signal a DF unit heard (0 to 9; 0 is where the signal is not heard), with the height, gain and directivity of its antenna."""
    strength: int
    height_m: float
    gain_db: int
    direction_deg: int | None


@dataclass(frozen=True, slots=True)
class DfBearing:
    """A DF report's bearing (degrees) and its number of hits (0 nothing, 1 to 8 the share of samples that hit, 9 a manual report), the range the line is drawn to (2^R miles, in km) and the quality (0 to 9)."""
    bearing_deg: int
    hits: int
    range_km: float
    quality: int


@dataclass(frozen=True, slots=True)
class Area:
    """An area object (symbol `\\l`): the shape, the colour and the offsets down and to the right (degrees) from the object's position, which is its upper left corner."""
    shape: str
    colour: str
    lat_offset_deg: float
    lon_offset_deg: float


@dataclass(frozen=True, slots=True)
class Extensions:
    phg: Phg | None = None
    range_km: float | None = None               # a pre-calculated radio range (RNG)
    dfs: Dfs | None = None
    df_bearing: DfBearing | None = None
    area: Area | None = None


def _direction(code: str) -> int | None:
    return None if code == "0" or int(code) > 8 else int(code) * 45


def _height_m(code: str) -> float:
    return 10 * (1 << (ord(code) - ord("0"))) * FOOT_M


def phg_range_km(power_w: int, height_m: float, gain_db: int) -> float:
    """The range of the spec's formula: SQR(2 * HAAT * SQR((POWER / 10) * (GAIN / 2))), HAAT in feet, in miles."""
    haat_ft = height_m / FOOT_M
    return math.sqrt(2 * haat_ft * math.sqrt(power_w / 10 * (10 ** (gain_db / 10) / 2))) * MILE_KM


def _phg(found: re.Match[str]) -> Phg:
    power, height, gain, direction = int(found.group(1)) ** 2, _height_m(found.group(2)), int(found.group(3)), _direction(found.group(4))
    return Phg(power, round(height, 1), gain, direction, round(phg_range_km(power, height, gain), 1))


def _area(found: re.Match[str]) -> Area:
    shape, lat, tens, colour, lon = int(found.group(1)), int(found.group(2)), found.group(3), int(found.group(4)), int(found.group(5))
    index = colour + (10 if tens == "1" else 0)
    return Area(_SHAPES[shape], _COLOURS[index] if index < len(_COLOURS) else "unknown", lat * lat / 100, lon * lon / 100)


def split_extension(text: str, area: bool) -> tuple[Extensions | None, str]:
    """The extension at the start of `text` (what follows the symbol of an uncompressed position, after any course and speed has been taken off) and the rest. `area` is true for the symbol `\\l`, whose
    extension is an area descriptor. None when there is none."""
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


def split_bearing(text: str) -> tuple[DfBearing | None, str]:
    """The `/BRG/NRQ` of a DF report at the start of `text` (right after the course and speed) and the rest."""
    found = _BEARING.match(text)
    if not found or int(found.group(1)) > 360:
        return None, text
    bearing, hits, rng, quality = int(found.group(1)), int(found.group(2)), int(found.group(3)), int(found.group(4))
    return DfBearing(bearing % 360, hits, round((1 << rng) * MILE_KM, 1), quality), text[found.end():]


def _direction_text(direction: int | None) -> str:
    return "omni" if direction is None else f"{direction}°"


def extension_lines(ext: Extensions) -> list[str]:
    """What the extensions say, one short line for each: "PHG 25 W, 6.1 m, 3 dB, 90°, range 13 km"."""
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
