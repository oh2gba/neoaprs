"""Maidenhead locators in a status report or Mic-E status text (APRS101 ch. 6, 10, 16).

A 4 or 6 character locator, the symbol table and code, then (after a space) the text. The
position of a locator is the centre of its square. Pure code.
"""

import re
from dataclasses import dataclass

from neoaprs.symbols import table_of

# the sub-square is possessive: "IO91SX hello" is text, not IO91 with the symbol SX
_LOCATOR = re.compile(r"([A-R]{2}\d\d(?:[A-Xa-x]{2})?+)(.)(.)(?= |$)", re.DOTALL)
_GRID = re.compile(r"([A-R]{2}\d\d(?:[A-Xa-x]{2})?)\]?(?= |$)", re.DOTALL)
# width of a field, a square and a subsquare in degrees of longitude (the height is half)
_FIELD, _SQUARE, _SUB = 20.0, 2.0, 2.0 / 24


@dataclass(frozen=True, slots=True)
class Locator:
    """A locator with its symbol and the centre of its square (decimal degrees)."""

    grid: str
    lat: float
    lon: float
    symbol_table: str
    symbol_code: str


def grid_centre(grid: str) -> tuple[float, float]:
    """Return latitude and longitude of the centre of a 4 or 6 character locator."""
    letters = grid.upper()
    lon = -180 + (ord(letters[0]) - 65) * _FIELD + int(letters[2]) * _SQUARE
    lat = -90 + (ord(letters[1]) - 65) * _FIELD / 2 + int(letters[3]) * _SQUARE / 2
    if len(letters) == 6:
        return lat + (ord(letters[5]) - 65) * _SUB / 2 + _SUB / 4, lon + (ord(letters[4]) - 65) * _SUB + _SUB / 2
    return lat + _SQUARE / 4, lon + _SQUARE / 2


def split_locator(text: str) -> tuple[Locator | None, str]:
    """Split the locator at the start of `text` from the rest (leading space dropped); else None."""
    found = _LOCATOR.match(text)
    if not found:
        return None, text
    table = table_of(found.group(2))
    if table is None or not "!" <= found.group(3) <= "~":
        return None, text
    lat, lon = grid_centre(found.group(1))
    return Locator(found.group(1), round(lat, 5), round(lon, 5), table, found.group(3)), text[found.end() :].lstrip(" ")


def split_beacon(text: str) -> tuple[Locator, str] | None:
    """Parse the locator beacon (data type `[`): locator, optional symbol (`/G`), `]`, text."""
    # a bare "IO91SX" is the grid, not "IO91" with overlay S and code X
    found = _GRID.match(text)
    if found:
        lat, lon = grid_centre(found.group(1))
        return Locator(found.group(1), round(lat, 5), round(lon, 5), "/", "G"), text[found.end() :].strip()
    locator, rest = split_locator(text)
    return None if locator is None else (locator, rest)
