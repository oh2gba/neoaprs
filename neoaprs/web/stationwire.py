"""The stations on the wire: the topic `stations` (a table of rows by call) and the command to forget one. Models like the rest of the protocol, listed in `neoaprs/web/protocol.py`."""
from typing import Literal

from pydantic import Field

from .wirebase import ExtensionValues, FrequencyValues, Iso, LocatorValues, StormValues, _Command, _Model


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


class ReachValues(_Model):
    """How a station's latest packet from the internet got there, read from the q-construct of its APRS-IS path."""
    kind: Literal["igate", "app"] = Field(description="`igate`: an iGate heard it on the radio and put it on the internet (`qAR`, `qAO`); `app`: it was sent from the internet by an app or a program and never was on the air (`TCPIP*`, `qAC`, `qAS`, `qAX`)")
    igate: str = Field(description="the call of the iGate that heard it; empty for `app`")
    hops: list[str] = Field(description="the digipeaters that repeated it on the radio before the iGate heard it, in order (`?` for one that put no call in); empty for a packet the iGate heard direct, and for `app`")


class RouteMarkValues(_Model):
    """One route a packet of a station came by, which the map draws (a line, or none for `app` and for a packet heard direct)."""
    kind: Literal["rf", "gated", "igate", "app"] = Field(description="`rf`: heard on the radio, direct when `hops` is empty; `gated`: heard on the radio as a third-party packet that the iGate `gate` put on the air, `hops` the digipeaters that repeated the iGate's frame; "
                                                                      "`igate`: heard on the radio by the iGate `gate`, which put it on the internet, `hops` the digipeaters before it; `app`: sent from the internet, never on the air")
    hops: list[str] = Field(description="the digipeaters in order, `?` for one that put no call in")
    gate: str = Field(description="the iGate of `gated` and `igate`; empty for the others")
    at: Iso = Field(description="when the packet was heard")
    lat: float | None = Field(description="where the station was when the packet was heard (the position it reported, else the one it had before); null when that is not known: the map takes its position now")
    lon: float | None


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
    packets: int = Field(description="how many packets of this station were received, whatever the channel (`heard_rf` + `heard_rf_gated` + `heard_is` + `heard_dummy`)")
    heard_rf: int = Field(ge=0, description="how many of them were heard on the radio, direct or by digipeaters (`rf`)")
    heard_rf_gated: int = Field(ge=0, description="how many came on the radio as third-party packets: an iGate put what it heard on the internet on the air (`rf-gated`); counted, but never a route to send by")
    heard_is: int = Field(ge=0, description="how many were received from APRS-IS over the internet (`is`); they were never on the air")
    heard_dummy: int = Field(ge=0, description="how many were made up by the Dummy radio (`dummy`), the radio for trying the program with no radio; they work as the radio's do, and never go to the internet")
    last_rf_at: Iso | None = Field(description="when a packet of the station was last heard on the radio (`rf`); null when none was")
    last_rf_gated_at: Iso | None = Field(description="when a third-party packet of the station was last heard on the radio (`rf-gated`); null when none was")
    last_is_at: Iso | None = Field(description="when a packet of the station was last received from the internet (`is`); null when none was")
    last_dummy_at: Iso | None = Field(description="when a packet of the station was last made up by the Dummy radio (`dummy`); null when none was")
    position_via: Literal["rf", "rf-gated", "is", "dummy"] | None = Field(description="the channel of the packet that gave its position (the latest one wins); null for a station without a position and for our own")
    packets_hour: int = Field(ge=0, description="how many of them were heard in the last hour (counted from the packets of the hour at the start and as they come; the row is told again each minute that it becomes fewer)")
    device: str = Field(description="what the station runs, as the APRS device identification list names it (\"Kenwood TH-D74\", \"APRSdroid\"): by the destination call of its packets, or by the type code of a Mic-E packet; empty when unknown")
    last_path: list[str] = Field(description="the digipeaters of the latest packet heard on the radio, the one that repeated it marked with `*`")
    last_route: str = Field(description="how the latest packet heard on the radio reached us (empty for a station known from the internet only): `direct`, `via OH2RCH-2`, `via OH2RCH-1 → OH2RCH-3` (the digipeaters that repeated it, in order, `?` for one that did not put its call in)")
    heard_direct: int = Field(ge=0, description="how many packets came straight from the station (counted from the packets heard in this run and the latest 2000 the database kept)")
    last_direct_at: Iso | None = Field(description="when a packet of the station was last heard direct (no digipeater repeated it, it was not a third-party packet), from the packets counted in `heard_direct`; null for a station never heard direct")
    heard_via: list[tuple[str, int]] = Field(description="[the station we heard, packets] for each digipeater that repeated its packets, the most first; `?` stands for a hop that was an alias (WIDE1) and gave no call; the 8 most frequent routes are counted")
    gated: int = Field(ge=0, description="how many third-party packets this station put on the air that we heard (an iGate wrapping what it took from the internet in a frame of its own; counted from the packets heard in this run and the latest 2000 the database kept, "
                                         "and for a station that is in the book); not `heard_rf_gated`, which counts the packets of this station that some iGate put on the air")
    igate: bool = Field(description="a capabilities packet of the station said `IGATE`: it says it is an iGate")
    best_route: str = Field(description="the route most of its packets came by, as `last_route` writes it, direct included; empty until a packet was counted")
    suggested_path: str | None = Field(description="the path to send by to reach it, the best route turned round: empty for direct, `OH2RCH-2` for one hop, `OH2RCH-3,OH2RCH-1` for `via OH2RCH-1 → OH2RCH-3`, `WIDE1-1,WIDE2-1` when the best route "
                                                   "has a hop with no call; null when no route is known (an object or item, or a station not heard since the packets were pruned)")
    heard_path: str | None = Field(description="the path that has lately been heard to reach the station, which the first two attempts of a message to it go by when the operator has set no path of its own (the later ones go by `beacon/path`): "
                                               "empty for direct (at least 2 packets heard direct within 60 minutes), else the latest named route that at least 2 packets came by within 60 minutes, turned round, as `suggested_path` writes it "
                                               "(no hop without a call, no iGate, at most 3 digipeaters); null when there is none. Worked out when the row is sent, so a path that goes stale is told with the station's next row")
    internet_reach: ReachValues | None = Field(description="how the latest packet of the station that came from the internet got there; null for a station none came from, and for one whose path does not say")
    route_marks: list[RouteMarkValues] = Field(max_length=2, description="the route of the station's latest packet and the one before it that came another way (any channel, the newest first): what the map draws of its routes, and no others; "
                                                                             "empty for a station nothing is known of (our own, our objects)")
    weather: WeatherValues | None = Field(description="the latest weather the station sent (a position with the weather symbol, or a positionless weather report); null for a station that sent none since the weather log began (or was made from the packets kept)")
    weather_at: Iso | None = Field(description="when `weather` was heard; null as it is")
    telemetry: TelemetryValues | None = Field(description="the latest telemetry report of the station, scaled and named by the definitions it sent (read again from the latest packets at the start); null for a station that sent none")
    telemetry_at: Iso | None = Field(description="when `telemetry` was heard; null as it is")
    locator: LocatorValues | None = Field(description="the Maidenhead locator of the station's latest status report (or Mic-E status text): where it says it is, to the square; null when it sent none")
    extensions: ExtensionValues | None = Field(description="the PHG, RNG, DF or area data of the station's latest position; null when it had none")
    frequency: FrequencyValues | None = Field(description="the voice frequency the station gave last, in the comment of a position (or the name of an object) or in a status text; null when it gave none (not kept over a restart of the daemon for a station that does not send it again)")
    storm: StormValues | None = Field(description="the storm data of the latest position of a storm object; null for anything else")
    sign: str | None = Field(description="what a signpost object says (`55`); null for anything else")
    distance_km: float | None = Field(description="from our position, null for us and for a station without a position")
    bearing_deg: float | None = Field(description="the direction from our position, degrees from north; null as the distance is")
    is_me: bool = Field(description="our own station: the row of the call in the settings, at the position in the settings")
    own: bool = Field(description="an object or an item of ours, which we send (the topic `own_objects` has its values and its schedule): the map marks it as ours and the card has Edit and Kill in place of Forget; false for any other row")
    can_message: bool = Field(description="a message to the station makes sense, and the card has a Message button: false for an object or an item and for our own station; for a station true when it has sent a message or an ack (heard, overheard too) "
                                          "or its latest position began with `=` or `@` or was a Mic-E one, false when that began with `!` or `/` or was a Mic-E one whose comment begins with the type code `'` (no messaging); true for a station of which nothing of that is known; "
                                          "false for a station known only from the internet (`heard_is` > 0 and nothing on the radio): a message goes out by radio only")
    track: list[tuple[Iso, float, float]] = Field(max_length=50, description="the latest 50 positions, oldest first, as [time, lat, lon]; a new one only when the station moved more than 10 m or 5 minutes passed")


class ForgetStation(_Command):
    """Removes a station from the station book (and its cache in the database) until it is heard again. Not our own station. Answered by the `del` of the row, or by an `error`."""
    cmd: Literal["forget_station"]
    call: str = Field(min_length=1, max_length=64)


class ForgetAllStations(_Command):
    """A fresh start for what was heard: removes every station and every packet heard (and the weather of the stations), in the daemon and in its database. The station we are, the objects and bulletins we send, the messages, the
    settings and the maps stay, and so do the packets we sent. Answered by the stations' topic told whole, or by an `error`."""
    cmd: Literal["forget_all_stations"]
