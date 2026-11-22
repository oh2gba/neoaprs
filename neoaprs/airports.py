"""Place name of an airport by ICAO code ("Stockholm" for ESSA), from airportdata.py."""
from functools import cache


@cache
def _table() -> dict[str, str]:
    from .airportdata import AIRPORTS     # imported lazily: the table is large
    return dict(AIRPORTS)


def place(code: str) -> str:
    """Return the place of the airport with this upper-case ICAO code, or "" if unknown."""
    return _table().get(code, "")
