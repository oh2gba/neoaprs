"""Storm data (APRS101, chapter 12): a tropical storm, hurricane or tropical depression as an object, with the symbol `@` (`\\@` the storm now, `/@` a hurricane predicted).

The course and speed of the storm are the data extension `088/036`, read as for any position. The comment then begins `/HC/150^200/0980>090&030%040`: `/ST` the type (TS tropical storm, HC hurricane, TD
tropical depression), `/www` the sustained wind and `^GGG` the gusts (knots), `/pppp` the central pressure (millibars), `>RRR` the radius of hurricane winds, `&rrr` the radius of tropical storm winds
and `%ggg` the radius of whole gale winds (nautical miles; the last is optional). Pure code, like the rest of the foundation."""
import re
from dataclasses import dataclass

from neoaprs.units import KNOT_KMH, NAUTICAL_MILE_KM

_STORM = re.compile(r"/(TS|HC|TD)(?![A-Za-z])(?:/(\d{3})(?!\d))?(?:\^(\d{3})(?!\d))?(?:/(\d{4})(?!\d))?(?:>(\d{3})(?!\d))?(?:&(\d{3})(?!\d))?(?:%(\d{3})(?!\d))?")


@dataclass(frozen=True, slots=True)
class Storm:
    """The storm data of an object or a position: wind in km/h, pressure in hPa, radii in km; None for a field the report did not have. The movement is the course and speed of the position."""
    storm_type: str                             # TS (tropical storm), HC (hurricane) or TD (tropical depression)
    wind_kmh: float | None = None               # the sustained wind
    gust_kmh: float | None = None
    pressure_hpa: int | None = None             # the central pressure
    hurricane_radius_km: float | None = None    # the radius of hurricane winds
    storm_radius_km: float | None = None        # the radius of tropical storm winds
    gale_radius_km: float | None = None         # the radius of whole gale (50 knot) winds


def _scaled(raw: str | None, unit: float) -> float | None:
    return None if raw is None else round(int(raw) * unit, 1)


def split_storm(text: str) -> tuple[str, Storm | None]:
    """The storm data at the start of `text` (the comment of a position or object with the symbol `@`, after the data extension) and the text without it; None, and the text as it is, when it does not begin with any."""
    found = _STORM.match(text)
    if not found:
        return text, None
    storm_type, wind, gust, pressure, hurricane, tropical, gale = found.groups()
    storm = Storm(storm_type, _scaled(wind, KNOT_KMH), _scaled(gust, KNOT_KMH), None if pressure is None else int(pressure), _scaled(hurricane, NAUTICAL_MILE_KM), _scaled(tropical, NAUTICAL_MILE_KM),
                  _scaled(gale, NAUTICAL_MILE_KM))
    return text[found.end():].strip(), storm


_NAMES = {"TS": "tropical storm", "HC": "hurricane", "TD": "tropical depression"}


def storm_text(storm: Storm) -> str:
    """What the storm data says, on one line: "hurricane, wind 278 km/h, gusts 370 km/h, 980 hPa, hurricane winds to 167 km"."""
    parts = [_NAMES[storm.storm_type]]
    for label, value, unit in (("wind", storm.wind_kmh, "km/h"), ("gusts", storm.gust_kmh, "km/h"), ("", storm.pressure_hpa, "hPa"), ("hurricane winds to", storm.hurricane_radius_km, "km"),
                               ("storm winds to", storm.storm_radius_km, "km"), ("gale winds to", storm.gale_radius_km, "km")):
        if value is not None:
            parts.append(f"{label + ' ' if label else ''}{value:.0f} {unit}")
    return ", ".join(parts)
