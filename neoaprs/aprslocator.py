"""Maidenhead locators (grid squares) in a status report or in the status text of a Mic-E packet (APRS101, chapters 6, 10 and 16): a 4 or 6 character locator, the symbol table and the symbol code, and then
(after a space) the text. The position of a locator is the centre of its square.

Pure code, like the rest of the foundation."""
import re
from dataclasses import dataclass

from neoaprs.symbols import table_of

_LOCATOR = re.compile(r"([A-R]{2}\d\d(?:[A-Xa-x]{2})?)(.)(.)(?= |$)", re.DOTALL)
_GRID = re.compile(r"([A-R]{2}\d\d(?:[A-Xa-x]{2})?)\]?(?= |$)", re.DOTALL)
_FIELD, _SQUARE, _SUB = 20.0, 2.0, 2.0 / 24         # the width of a field, a square and a subsquare in degrees of longitude (the height is half of it)


@dataclass(frozen=True, slots=True)
class Locator:
    """A locator with the symbol that came with it, and the centre of its square (decimal degrees)."""
    grid: str
    lat: float
    lon: float
    symbol_table: str
    symbol_code: str


def grid_centre(grid: str) -> tuple[float, float]:
    """The latitude and longitude of the centre of a 4 or 6 character locator."""
    letters = grid.upper()
    lon = -180 + (ord(letters[0]) - 65) * _FIELD + int(letters[2]) * _SQUARE
    lat = -90 + (ord(letters[1]) - 65) * _FIELD / 2 + int(letters[3]) * _SQUARE / 2
    if len(letters) == 6:
        return lat + (ord(letters[5]) - 65) * _SUB / 2 + _SUB / 4, lon + (ord(letters[4]) - 65) * _SUB + _SUB / 2
    return lat + _SQUARE / 4, lon + _SQUARE / 2


def split_locator(text: str) -> tuple[Locator | None, str]:
    """The locator at the start of `text` and the rest of the text (its leading space taken off); None and the text as it is when the text does not begin with one."""
    found = _LOCATOR.match(text)
    if not found:
        return None, text
    table = table_of(found.group(2))
    if table is None or not "!" <= found.group(3) <= "~":
        return None, text
    lat, lon = grid_centre(found.group(1))
    return Locator(found.group(1), round(lat, 5), round(lon, 5), table, found.group(3)), text[found.end():].lstrip(" ")


def split_beacon(text: str) -> tuple[Locator, str] | None:
    """The locator beacon (data type `[`): a locator, perhaps with its symbol (otherwise the grid square symbol `/G`), perhaps closed by `]`, and the text after it; None when there is no locator."""
    found = _GRID.match(text)                                # (a bare "IO91SX" is the grid, not "IO91" with the overlay S and the code X)
    if found:
        lat, lon = grid_centre(found.group(1))
        return Locator(found.group(1), round(lat, 5), round(lon, 5), "/", "G"), text[found.end():].strip()
    locator, rest = split_locator(text)
    return None if locator is None else (locator, rest)
