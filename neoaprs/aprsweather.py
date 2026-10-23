"""APRS weather: the fields that follow the position of a weather station (symbol code `_`) or the timestamp of a positionless weather report (data type `_`), decoded and converted to metric.

The fields are a letter and a fixed number of digits (APRS101, chapter 12): `c` wind direction (degrees) and `s` its speed (mph), or the same as the leading `DIR/SPD` of a position; `g` gust (mph), `t` temperature (degrees F, three
characters, `-05` below zero), `r` rain in the last hour, `p` in the last 24 hours and `P` since midnight (hundredths of an inch), `h` humidity (per cent, `00` is 100), `b` pressure (tenths of a hPa), `L` luminosity (W/m2, 0 to 999)
and `l` (1000 and more, as `l` plus 1000), `s` snow in the last 24 hours (inches) once the wind speed is there already, `#` the raw rain counter. A field that is all dots or all spaces is missing. The fields end at the first
character that is not a field of this list with the right digits; what follows (a software id such as `wRSW`, "RX Igate & WX station", a comment glued to the data) is the comment.

Pure code, like the rest of the foundation."""
import re
from dataclasses import dataclass

MPH_KMH = 1.609344
INCH_MM = 25.4

_WIND = re.compile(r"(\d{2,3}|\.{2,3}| {2,3})/(\d{3}|\.{3}| {3})")           # the wind of a position: direction (2 or 3 digits, some stations send two) and speed
_FIELDS = {letter: re.compile(rf"(\d{{{width}}}|\.{{{width}}}| {{{width}}})") for letter, width in
           (("c", 3), ("s", 3), ("g", 3), ("r", 3), ("p", 3), ("P", 3), ("h", 2), ("b", 5), ("L", 3), ("l", 3), ("#", 3))}
_FIELDS["t"] = re.compile(r"(-\d{2}|\d{3}|\.{3}| {3})")
_MAX_DIRECTION = 360
_VALUES = ("wind_dir", "wind_kmh", "gust_kmh", "temp_c", "humidity", "pressure_hpa", "rain_1h_mm", "rain_24h_mm", "rain_today_mm", "luminosity", "snow_mm", "rain_counter")


@dataclass(frozen=True, slots=True)
class Weather:
    """One weather observation in metric units; every field is None when the report did not have it. `raw` is the text of the fields as they were sent."""
    wind_dir: int | None = None                    # degrees the wind blows from
    wind_kmh: float | None = None                  # sustained, km/h
    gust_kmh: float | None = None
    temp_c: float | None = None
    humidity: int | None = None                    # per cent, 1 to 100
    pressure_hpa: float | None = None
    rain_1h_mm: float | None = None
    rain_24h_mm: float | None = None
    rain_today_mm: float | None = None             # since midnight
    luminosity: int | None = None                  # W/m2
    snow_mm: float | None = None                   # in the last 24 hours
    rain_counter: int | None = None                # the raw rain counter, as the station counts it
    raw: str = ""


def _number(text: str) -> int | None:
    return int(text) if text.lstrip("-").isdigit() else None


def _scan(text: str) -> tuple[dict[str, int | None], int]:
    """The fields at the start of `text`, by their letter (`snow` for an `s` that follows the wind speed), with the raw numbers (None for a missing one), and how many characters they took."""
    fields: dict[str, int | None] = {}
    pos = 0
    wind = _WIND.match(text)
    if wind:
        fields["c"], fields["s"] = _number(wind.group(1)), _number(wind.group(2))
        pos = wind.end()
    while pos < len(text):
        letter = text[pos]
        found = _FIELDS[letter].match(text, pos + 1) if letter in _FIELDS else None
        key = "snow" if letter == "s" and "s" in fields else letter
        if found is None or key in fields:
            break
        fields[key] = _number(found.group(1))
        pos = found.end()
    return fields, pos


def _scaled(value: int | None, factor: float) -> float | None:
    return None if value is None else round(value * factor, 1)


def _humidity(value: int | None) -> int | None:
    if value is None:
        return None
    return 100 if value == 0 else value


def _luminosity(fields: dict[str, int | None]) -> int | None:
    low, high = fields.get("L"), fields.get("l")
    return low if low is not None else (None if high is None else 1000 + high)


def _weather(fields: dict[str, int | None], raw: str) -> Weather | None:
    direction = fields.get("c")
    fahrenheit = fields.get("t")
    pressure = fields.get("b")
    weather = Weather(
        wind_dir=direction if direction is not None and direction <= _MAX_DIRECTION else None, wind_kmh=_scaled(fields.get("s"), MPH_KMH), gust_kmh=_scaled(fields.get("g"), MPH_KMH),
        temp_c=None if fahrenheit is None else round((fahrenheit - 32) * 5 / 9, 1), humidity=_humidity(fields.get("h")), pressure_hpa=None if pressure is None else pressure / 10,
        rain_1h_mm=_scaled(fields.get("r"), 0.254), rain_24h_mm=_scaled(fields.get("p"), 0.254), rain_today_mm=_scaled(fields.get("P"), 0.254),
        luminosity=_luminosity(fields), snow_mm=_scaled(fields.get("snow"), INCH_MM), rain_counter=fields.get("#"), raw=raw)
    return weather if any(getattr(weather, name) is not None for name in _VALUES) else None



def parse_weather(text: str) -> tuple[Weather | None, str]:
    """The weather fields at the start of `text` (the part of a position after the symbol, or of a positionless report after its time) and the rest, which is the comment. None when the text has no field, or when every field it has is missing."""
    fields, taken = _scan(text)
    if not taken:
        return None, text
    return _weather(fields, text[:taken]), text[taken:]


def parse_report(info: bytes) -> Weather | None:
    """The weather of a positionless report, the information field `_MMDDhhmm` and the fields (the time is not used: the packet's own is); None for anything else."""
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
    for value, form in ((w.rain_1h_mm, "{:.1f} mm/h"), (w.rain_24h_mm, "24 h {:.1f} mm"), (w.rain_today_mm, "today {:.1f} mm")):
        if value is not None:
            bits.append(form.format(value))
    return "rain " + ", ".join(bits) if bits else None


def weather_text(w: Weather) -> str:
    """The observation in a line, only the fields that are there: `wind 107° 2 km/h gusts 2, 10.0 °C, 85 %, 1028.4 hPa, rain 0.3 mm/h, 24 h 4.1 mm`."""
    parts = [
        _wind_text(w), None if w.temp_c is None else f"{w.temp_c:.1f} °C", None if w.humidity is None else f"{w.humidity} %", None if w.pressure_hpa is None else f"{w.pressure_hpa:.1f} hPa",
        _rain_text(w), None if w.luminosity is None else f"{w.luminosity} W/m²", None if w.snow_mm is None else f"snow {w.snow_mm:.0f} mm",
    ]
    return ", ".join(part for part in parts if part)
