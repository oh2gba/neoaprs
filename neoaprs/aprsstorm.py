"""Storm data (APRS101 ch. 12): a tropical storm, hurricane or depression as an object, symbol `@`.

`\\@` is the storm now, `/@` a predicted hurricane. The comment begins
`/HC/150^200/0980>090&030%040`: type, wind and gusts (knots), pressure (mbar), radii (nautical miles).
"""
import re
from dataclasses import dataclass

from neoaprs.units import KNOT_KMH, NAUTICAL_MILE_KM

_STORM = re.compile(r"/(TS|HC|TD)(?![A-Za-z])(?:/(\d{3})(?!\d))?(?:\^(\d{3})(?!\d))?(?:/(\d{4})(?!\d))?(?:>(\d{3})(?!\d))?(?:&(\d{3})(?!\d))?(?:%(\d{3})(?!\d))?")


@dataclass(frozen=True, slots=True)
class Storm:
    """Storm data: wind in km/h, pressure in hPa, radii in km; None for a field not reported.

    The movement is the course and speed of the position.
    """
    storm_type: str  # TS, HC (hurricane) or TD (depression)
    wind_kmh: float | None = None  # sustained wind
    gust_kmh: float | None = None
    pressure_hpa: int | None = None  # central pressure
    hurricane_radius_km: float | None = None  # radius of hurricane winds
    storm_radius_km: float | None = None  # radius of tropical storm winds
    gale_radius_km: float | None = None  # whole gale (50 knot) winds


def _scaled(raw: str | None, unit: float) -> float | None:
    return None if raw is None else round(int(raw) * unit, 1)


def split_storm(text: str) -> tuple[str, Storm | None]:
    """Split storm data off the start of `text` (a `@` comment after the extension); else None."""
    found = _STORM.match(text)
    if not found:
        return text, None
    storm_type, wind, gust, pressure, hurricane, tropical, gale = found.groups()
    storm = Storm(storm_type, _scaled(wind, KNOT_KMH), _scaled(gust, KNOT_KMH), None if pressure is None else int(pressure), _scaled(hurricane, NAUTICAL_MILE_KM), _scaled(tropical, NAUTICAL_MILE_KM),
                  _scaled(gale, NAUTICAL_MILE_KM))
    return text[found.end():].strip(), storm


_NAMES = {"TS": "tropical storm", "HC": "hurricane", "TD": "tropical depression"}


def storm_text(storm: Storm) -> str:
    """Return one line, e.g. "hurricane, wind 278 km/h, gusts 370 km/h, 980 hPa"."""
    parts = [_NAMES[storm.storm_type]]
    for label, value, unit in (("wind", storm.wind_kmh, "km/h"), ("gusts", storm.gust_kmh, "km/h"), ("", storm.pressure_hpa, "hPa"), ("hurricane winds to", storm.hurricane_radius_km, "km"),
                               ("storm winds to", storm.storm_radius_km, "km"), ("gale winds to", storm.gale_radius_km, "km")):
        if value is not None:
            parts.append(f"{label + ' ' if label else ''}{value:.0f} {unit}")
    return ", ".join(parts)
