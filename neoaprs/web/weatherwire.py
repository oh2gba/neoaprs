"""The weather on the wire: the command that asks for the observations of one weather station and the message that answers it. The current observation is a field of the station's row (`neoaprs/web/stationwire.py`).
Models like the rest of the protocol, listed in `neoaprs/web/protocol.py`."""
from typing import Literal

from pydantic import Field

from .wirebase import Iso, _Command, _Message

Value = float | None
Point = tuple[Iso, Value, Value, Value, Value, Value, Value]


class WeatherSeries(_Command):
    """Asks for the observations a weather station made in the last `hours` hours. Answered with a `weather_series` message to the page that asked, or an `error` for a call that is empty or hours out of range; a call with no
    observations is answered with no points."""
    cmd: Literal["weather_series"]
    call: str = Field(min_length=1, max_length=64, description="the station, as the `stations` topic has it (an object's name for a weather object)")
    hours: int = Field(ge=1, le=168, description="how far back to go: 24 for a day, 168 for a week")


class WeatherSeriesMsg(_Message):
    """The observations of one weather station, the answer to `weather_series`: one point for each weather packet heard, the oldest first (a packet that came by two digipeaters is two points)."""
    type: Literal["weather_series"]
    call: str = Field(description="the station asked about")
    hours: int = Field(ge=1, le=168, description="the hours asked for: a page that asked twice (a day, then a week) tells the answers apart by it")
    points: list[Point] = Field(description="[time, temp_c, pressure_hpa, wind_kmh, gust_kmh, rain_1h_mm, humidity] for each observation; a value the report did not have is null")
