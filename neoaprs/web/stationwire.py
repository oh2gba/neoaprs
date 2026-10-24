"""The stations on the wire: the topic `stations` (a table of rows by call) and the command to forget one. Models like the rest of the protocol, listed in `neoaprs/web/protocol.py`."""
from typing import Literal

from pydantic import Field

from .wirebase import ExtensionValues, Iso, LocatorValues, _Command, _Model


class WeatherValues(_Model):
    """One weather observation in metric units; each field is null where the report did not have it."""
    wind_dir: int | None = Field(description="the direction the wind blows from, degrees from north (0 to 360)")
    wind_kmh: float | None = Field(description="the sustained wind, km/h")
    gust_kmh: float | None = Field(description="the gust, km/h")
    temp_c: float | None = Field(description="degrees Celsius")
    humidity: int | None = Field(description="per cent (1 to 100)")
    pressure_hpa: float | None = Field(description="barometric pressure, hPa")
    rain_1h_mm: float | None = Field(description="rain in the last hour, mm")
    rain_24h_mm: float | None = Field(description="rain in the last 24 hours, mm")
    rain_today_mm: float | None = Field(description="rain since midnight, mm")
    luminosity: int | None = Field(description="W/m2")
    snow_mm: float | None = Field(description="snow in the last 24 hours, mm")


class TelemetryChannel(_Model):
    """One analog channel of a station's latest telemetry report."""
    name: str = Field(description="from the station's `PARM.` message, else `A1` to `A5`")
    unit: str = Field(description="from its `UNIT.` message; empty when it sent none")
    raw: float = Field(description="the value as it was sent (0 to 255)")
    value: float = Field(description="`a*raw^2 + b*raw + c` with the coefficients of its `EQNS.` message; the raw value when it sent none")


class TelemetryBit(_Model):
    """One digital channel of a station's latest telemetry report."""
    name: str = Field(description="from the station's `PARM.` message, else `B1` to `B8`")
    on: bool = Field(description="the bit has the sense that its `BITS.` message gives (1 when there is none)")


class TelemetryValues(_Model):
    """A station's latest telemetry report with the definitions the station sent as messages (`PARM.`, `UNIT.`, `EQNS.`, `BITS.`) applied."""
    sequence: int | None = Field(description="the sequence number; null for the `MIC` of a Mic-E unit")
    channels: list[TelemetryChannel] = Field(description="the analog channels, as many as the report had (1 to 5)")
    bits: list[TelemetryBit] = Field(description="the digital channels, as many as the report had (up to 8)")
    project: str = Field(description="the project title of the `BITS.` message; empty when there is none")
    comment: str


class StationRow(_Model):
    """One station of the station book: who it is, where it was heard and how often. An object or an item is a row of its own, named by the object. The rows are the values of the topic `stations`
    (keyed by `call`): a station heard again is a `set` of its row, a station that is forgotten or pruned (or an object that was killed) a `del`. When our own position changes in the settings every
    row has a new distance and bearing, and the topic is told whole again."""
    call: str = Field(description="the call with its SSID, or the name of the object or item")
    kind: Literal["station", "object", "item"]
    reported_by: str = Field(description="who sent the report, for an object or an item; empty for a station")
    symbol_table: str = Field(description="`/` (primary), `\\` (alternate) or an overlay character 0-9, A-Z; empty until a position is heard")
    symbol_code: str = Field(description="the character of the symbol in its table; empty until a position is heard")
    symbol_name: str = Field(description="the name of the symbol (\"Car\", \"Digipeater\"), `unknown` for none")
    lat: float | None = Field(description="decimal degrees, south negative; null until a position is heard")
    lon: float | None = Field(description="decimal degrees, west negative; null until a position is heard")
    altitude_m: float | None
    course_deg: int | None
    speed_kmh: float | None
    first_heard: Iso
    last_heard: Iso
    last_position_at: Iso | None
    last_status: str = Field(description="the text of the latest status report")
    last_comment: str = Field(description="the comment of the latest position")
    packets: int = Field(description="how many packets of this station were heard")
    last_path: list[str] = Field(description="the digipeaters of the latest packet, the one that repeated it marked with `*`")
    last_route: str = Field(description="how the latest packet reached us: `direct`, `via OH2RCH-2`, `via OH2RCH-1 → OH2RCH-3` (the digipeaters that repeated it, in order, `?` for one that did not put its call in)")
    heard_direct: int = Field(ge=0, description="how many packets came straight from the station (counted from the packets heard in this run and the latest 2000 the database kept)")
    last_direct_at: Iso | None = Field(description="when a packet of the station was last heard direct (no digipeater repeated it, it was not a third-party packet), from the packets counted in `heard_direct`; null for a station never heard direct")
    heard_gated: int = Field(ge=0, description="how many packets came as third-party packets: an iGate put what it heard on the internet on the air; counted, but never a route to send by")
    heard_via: list[tuple[str, int]] = Field(description="[the station we heard, packets] for each digipeater that repeated its packets, the most first; `?` stands for a hop that was an alias (WIDE1) and gave no call; the 8 most frequent routes are counted")
    best_route: str = Field(description="the route most of its packets came by, as `last_route` writes it, direct included; empty until a packet was counted")
    suggested_path: str | None = Field(description="the path to send by to reach it, the best route turned round: empty for direct, `OH2RCH-2` for one hop, `OH2RCH-3,OH2RCH-1` for `via OH2RCH-1 → OH2RCH-3`, `WIDE1-1,WIDE2-1` when the best route "
                                                   "has a hop with no call; null when no route is known (an object or item, or a station not heard since the packets were pruned)")
    heard_path: str | None = Field(description="the path that has lately been heard to reach the station, which the first two attempts of a message to it go by when the operator has set no path of its own (the later ones go by `beacon/path`): "
                                               "empty for direct (at least 2 packets heard direct within 60 minutes), else the latest named route that at least 2 packets came by within 60 minutes, turned round, as `suggested_path` writes it "
                                               "(no hop without a call, no iGate, at most 3 digipeaters); null when there is none. Worked out when the row is sent, so a path that goes stale is told with the station's next row")
    weather: WeatherValues | None = Field(description="the latest weather the station sent (a position with the weather symbol, or a positionless weather report); null for a station that sent none since the weather log began (or was made from the packets kept)")
    weather_at: Iso | None = Field(description="when `weather` was heard; null as it is")
    telemetry: TelemetryValues | None = Field(description="the latest telemetry report of the station, scaled and named by the definitions it sent (read again from the latest packets at the start); null for a station that sent none")
    telemetry_at: Iso | None = Field(description="when `telemetry` was heard; null as it is")
    locator: LocatorValues | None = Field(description="the Maidenhead locator of the station's latest status report (or Mic-E status text): where it says it is, to the square; null when it sent none")
    extensions: ExtensionValues | None = Field(description="the PHG, RNG, DF or area data of the station's latest position; null when it had none")
    distance_km: float | None = Field(description="from our position, null for us and for a station without a position")
    bearing_deg: float | None = Field(description="the direction from our position, degrees from north; null as the distance is")
    is_me: bool = Field(description="our own station: the row of the call in the settings, at the position in the settings")
    own: bool = Field(description="an object or an item of ours, which we send (the topic `own_objects` has its values and its schedule): the map marks it as ours and the card has Edit and Kill in place of Forget; false for any other row")
    can_message: bool = Field(description="a message to the station makes sense, and the card has a Message button: false for an object or an item and for our own station; for a station true when it has sent a message or an ack (heard, overheard too) "
                                          "or its latest position began with `=` or `@` or was a Mic-E one, false when that began with `!` or `/` or was a Mic-E one whose comment begins with the type code `'` (no messaging); true for a station of which nothing of that is known")
    track: list[tuple[Iso, float, float]] = Field(max_length=50, description="the latest 50 positions, oldest first, as [time, lat, lon]; a new one only when the station moved more than 10 m or 5 minutes passed")


class ForgetStation(_Command):
    """Removes a station from the station book (and its cache in the database) until it is heard again. Not our own station. Answered by the `del` of the row, or by an `error`."""
    cmd: Literal["forget_station"]
    call: str = Field(min_length=1, max_length=64)
