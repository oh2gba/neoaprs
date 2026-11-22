"""APRS weather fields after a weather station's position or a positionless report's time.

Fields are converted to metric. A field of dots or spaces is missing; the fields end at the first
character that is no field, and the rest is the comment.
"""

import re
from dataclasses import dataclass

from neoaprs.units import INCH_MM, MILE_KM, fahrenheit_to_celsius

# wind direction (some stations send two digits) and speed
_WIND = re.compile(r"(\d{2,3}|\.{2,3}| {2,3})/(\d{3}|\.{3}| {3})")
_FIELDS = {
    letter: re.compile(rf"(\d{{{width}}}|\.{{{width}}}| {{{width}}})")
    for letter, width in (
        ("c", 3),
        ("s", 3),
        ("g", 3),
        ("r", 3),
        ("p", 3),
        ("P", 3),
        ("h", 2),
        ("b", 5),
        ("L", 3),
        ("l", 3),
        ("#", 3),
    )
}
_FIELDS["t"] = re.compile(r"(-\d{2}|\d{3}|\.{3}| {3})")
# snow of the last 24 hours, inches: three characters, a decimal point allowed (`s1.5`)
_SNOW = re.compile(r"(\d{3}|\d\.\d|\d{2}\.|\.\d{2}|\.{3}| {3})")
_MAX_DIRECTION = 360
_VALUES = (
    "wind_dir",
    "wind_kmh",
    "gust_kmh",
    "temp_c",
    "humidity",
    "pressure_hpa",
    "rain_1h_mm",
    "rain_24h_mm",
    "rain_today_mm",
    "luminosity",
    "snow_mm",
    "rain_counter",
)


@dataclass(frozen=True, slots=True)
class Weather:
    """One weather observation in metric units; a field is None if the report lacked it.

    `raw` is the text of the fields as sent.
    """

    wind_dir: int | None = None  # degrees the wind blows from
    wind_kmh: float | None = None  # sustained, km/h
    gust_kmh: float | None = None
    temp_c: float | None = None
    humidity: int | None = None  # per cent, 1 to 100
    pressure_hpa: float | None = None
    rain_1h_mm: float | None = None
    rain_24h_mm: float | None = None
    rain_today_mm: float | None = None  # since midnight
    luminosity: int | None = None  # W/m2
    snow_mm: float | None = None  # in the last 24 hours
    rain_counter: int | None = None  # the raw rain counter, as the station counts it
    raw: str = ""


def _number(text: str) -> int | None:
    return int(text) if text.lstrip("-").isdigit() else None


def _decimal(text: str) -> float | None:
    return float(text) if any(c.isdigit() for c in text) else None


def _scan(text: str) -> tuple[dict[str, int | None], float | None, int]:
    """Return the fields at the start of `text` by letter, raw numbers, snow and length taken.

    Snow is an `s` after the wind speed, in inches; the length is in characters.
    """
    fields: dict[str, int | None] = {}
    snow: float | None = None
    snowed = False
    pos = 0
    wind = _WIND.match(text)
    if wind:
        fields["c"], fields["s"] = _number(wind.group(1)), _number(wind.group(2))
        pos = wind.end()
    while pos < len(text):
        letter = text[pos]
        if letter == "s" and "s" in fields:
            found = None if snowed else _SNOW.match(text, pos + 1)
            if found is None:
                break
            snow, snowed, pos = _decimal(found.group(1)), True, found.end()
            continue
        found = _FIELDS[letter].match(text, pos + 1) if letter in _FIELDS else None
        if found is None or letter in fields:
            break
        fields[letter] = _number(found.group(1))
        pos = found.end()
    return fields, snow, pos


def _scaled(value: float | None, factor: float) -> float | None:
    return None if value is None else round(value * factor, 1)


def _humidity(value: int | None) -> int | None:
    if value is None:
        return None
    return 100 if value == 0 else value


def _luminosity(fields: dict[str, int | None]) -> int | None:
    low, high = fields.get("L"), fields.get("l")
    return low if low is not None else (None if high is None else 1000 + high)


def _weather(fields: dict[str, int | None], snow: float | None, raw: str) -> Weather | None:
    direction = fields.get("c")
    fahrenheit = fields.get("t")
    pressure = fields.get("b")
    weather = Weather(
        wind_dir=direction if direction is not None and direction <= _MAX_DIRECTION else None,
        wind_kmh=_scaled(fields.get("s"), MILE_KM),
        gust_kmh=_scaled(fields.get("g"), MILE_KM),
        temp_c=None if fahrenheit is None else round(fahrenheit_to_celsius(fahrenheit), 1),
        humidity=_humidity(fields.get("h")),
        pressure_hpa=None if pressure is None else pressure / 10,
        rain_1h_mm=_scaled(fields.get("r"), 0.254),
        rain_24h_mm=_scaled(fields.get("p"), 0.254),
        rain_today_mm=_scaled(fields.get("P"), 0.254),
        luminosity=_luminosity(fields),
        snow_mm=_scaled(snow, INCH_MM),
        rain_counter=fields.get("#"),
        raw=raw,
    )
    return weather if any(getattr(weather, name) is not None for name in _VALUES) else None


def parse_weather(text: str) -> tuple[Weather | None, str]:
    """Split the weather fields off the start of `text`; the rest is the comment.

    The weather is None if there is no field or every field is missing.
    """
    fields, snow, taken = _scan(text)
    if not taken:
        return None, text
    return _weather(fields, snow, text[:taken]), text[taken:]


def parse_report(info: bytes) -> Weather | None:
    """Return the weather of a positionless report `_MMDDhhmm` + fields (time unused); else None."""
    text = info.decode("latin-1")
    if text[:1] != "_" or not text[1:9].isdigit():
        return None
    return parse_weather(text[9:])[0]


def _wind_text(w: Weather) -> str | None:
    bits = [] if w.wind_dir is None else [f"{w.wind_dir}°"]
    if w.wind_kmh is not None:
        bits.append(f"{w.wind_kmh:.0f} km/h")
    if w.gust_kmh is not None:
        bits.append(f"gusts {w.gust_kmh:.0f}" + ("" if w.wind_kmh is not None else " km/h"))
    return "wind " + " ".join(bits) if bits else None


def _rain_text(w: Weather) -> str | None:
    bits = []
    for value, form in (
        (w.rain_1h_mm, "{:.1f} mm/h"),
        (w.rain_24h_mm, "24 h {:.1f} mm"),
        (w.rain_today_mm, "today {:.1f} mm"),
    ):
        if value is not None:
            bits.append(form.format(value))
    return "rain " + ", ".join(bits) if bits else None


def weather_text(w: Weather) -> str:
    """Return the present fields in one line: `wind 107° 2 km/h, 10.0 °C, 85 %, 1028.4 hPa`."""
    parts = [
        _wind_text(w),
        None if w.temp_c is None else f"{w.temp_c:.1f} °C",
        None if w.humidity is None else f"{w.humidity} %",
        None if w.pressure_hpa is None else f"{w.pressure_hpa:.1f} hPa",
        _rain_text(w),
        None if w.luminosity is None else f"{w.luminosity} W/m²",
        None if w.snow_mm is None else f"snow {w.snow_mm:.0f} mm",
    ]
    return ", ".join(part for part in parts if part)
