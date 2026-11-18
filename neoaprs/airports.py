"""The place an airport is in, by its ICAO code (airportdata.py, credited there): "Stockholm" for ESSA. Pure code; the table is made into a dictionary the first time it is asked."""
from functools import cache


@cache
def _table() -> dict[str, str]:
    from .airportdata import AIRPORTS     # (here, so that a daemon that never looks at an aircraft does not read the table)
    return dict(AIRPORTS)


def place(code: str) -> str:
    """The place of the airport with this ICAO code (four letters or digits, upper case); "" when the table does not know it."""
    return _table().get(code, "")
