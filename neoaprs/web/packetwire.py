"""The packets on the wire: the topic `packets` (the latest 200, a table of rows by id), and the command that reads one station's packets from the log with the message that answers it. Models like the rest of the protocol, listed in `neoaprs/web/protocol.py`.

`decoded` is what the parser made of the information field, as one of the models `Decoded...` below, tagged by `type` (the same word as `kind` of the row, except for a telemetry report: its kind is `other` and its type `telemetry`). A time inside it is `YYYY-MM-DDTHH:MM:SS.ffffffZ`."""
from typing import Annotated, Literal, Union

from pydantic import Field

from .wirebase import ExtensionValues, FrequencyValues, Iso, LocatorValues, StormValues, _Command, _Message, _Model

Stamp = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$", description="UTC, ISO 8601 with a Z, with fractions of a second")]


class DecodedWeather(_Model):
    """The weather fields of a weather station's position or of a positionless weather report, in metric units; null where the report did not have the field."""
    wind_dir: int | None = Field(description="degrees the wind blows from")
    wind_kmh: float | None
    gust_kmh: float | None
    temp_c: float | None
    humidity: int | None = Field(description="per cent, 1 to 100")
    pressure_hpa: float | None
    rain_1h_mm: float | None
    rain_24h_mm: float | None
    rain_today_mm: float | None = Field(description="since midnight")
    luminosity: int | None = Field(description="W/m2")
    snow_mm: float | None = Field(description="in the last 24 hours")
    rain_counter: int | None = Field(description="the raw rain counter, as the station counts it")
    raw: str = Field(description="the weather fields as they were sent")


class TelemetryFields(_Model):
    """A telemetry report as the parser made it."""
    sequence: int | None = Field(description="the sequence number; null for the `MIC` of a Mic-E unit")
    analog: list[float] = Field(description="the analog values as sent, 1 to 5 (APRS 1.2: any width, signed, with a decimal point)")
    bits: str = Field(description="the digital values as a text of 0 and 1, B1 first: up to eight, empty when there were none")
    comment: str


class PositionFields(_Model):
    """A position as the parser made it: decimal degrees, south and west negative, speed in km/h, altitude in metres."""
    lat: float
    lon: float
    symbol_table: str
    symbol_code: str
    comment: str
    course_deg: int | None
    speed_kmh: float | None
    altitude_m: float | None
    timestamp: Stamp | None = Field(description="the time the packet itself carries, when it has one")
    messaging: bool = Field(description="the station can receive messages")
    compressed: bool
    ambiguity: int = Field(description="how many digits of the position were blanked out, 0 to 4")
    weather: DecodedWeather | None = Field(description="the weather a station with the weather symbol (`_`) sent after its position; the rest of the text is the `comment`")
    extensions: ExtensionValues | None = Field(description="the PHG, RNG, DFS, DF bearing or area data after the symbol of an uncompressed position; null when there was none")
    timestamp_local: bool = Field(description="the `timestamp` was sent in the sender's local time (`/`): it is the time as it was sent, not UTC")
    locator: LocatorValues | None = Field(description="the Maidenhead locator in the status text of a Mic-E packet; null for any other position")
    telemetry: TelemetryFields | None = Field(default=None, description="the base-91 telemetry `|ss11|` the comment carried (APRS 1.2), taken out of the `comment`; null when there was none")
    frequency: FrequencyValues | None = Field(description="the local information the comment began with (`145.775MHz T100 -060 R40k`), or the name of a frequency object with the fields of its comment, taken out of the `comment`; null when there was none")
    storm: StormValues | None = Field(description="the storm data the comment of a position with the symbol `@` began with (`/HC/150^200/0980>090&030%040`), taken out of the `comment`; null when there was none")
    sign: str | None = Field(description="the characters of a signpost (symbol `\\m`): `55` for a comment that began `{55}`, taken out of the `comment`; null for any other position")


class DecodedPosition(PositionFields):
    """A position report."""
    type: Literal["position"]


class DecodedMessage(_Model):
    """A text message; an ack has `ack_id` and no text, a reject `rej_id`."""
    type: Literal["message"]
    addressee: str
    text: str
    msg_id: str | None
    ack_id: str | None
    rej_id: str | None


class DecodedObject(_Model):
    """An object report: a thing (a storm, an event) that a station puts on the map."""
    type: Literal["object"]
    name: str
    alive: bool = Field(description="false when the report kills the object")
    position: PositionFields
    timestamp: Stamp | None


class DecodedItem(_Model):
    """An item report: like an object, without a time."""
    type: Literal["item"]
    name: str
    alive: bool
    position: PositionFields


class DecodedStatus(_Model):
    """A status report."""
    type: Literal["status"]
    text: str = Field(description="the status text; after the locator when there is one")
    timestamp: Stamp | None
    locator: LocatorValues | None = Field(description="a Maidenhead locator with a symbol at the start of the report (a report that has one has no timestamp)")
    frequency: FrequencyValues | None = Field(description="the frequency the text began with (`>145.775MHz T100`), taken out of the `text`; null when there was none")


class DecodedTelemetry(TelemetryFields):
    """A telemetry report (`T#005,199,000,255,073,123,01101001`). The definitions of the channels are messages of the station, applied by the daemon: see `telemetry` of the station."""
    type: Literal["telemetry"]


class DecodedOther(_Model):
    """A data type that is recognised but not (fully) decoded: a positionless weather report is decoded (`weather`, `timestamp`), the station capabilities and an Agrelo DF report are read into `items`."""
    type: Literal["other"]
    kind: str = Field(description="a short word: weather, nmea, query, test, capabilities, agrelo-df, shelter, space-weather, third-party, user-defined, telemetry (one that is not a report), ...")
    text: str = Field(description="the whole information field")
    weather: DecodedWeather | None = Field(description="the observation of a positionless weather report (`_`); null for anything else")
    items: dict[str, str] | None = Field(description="`capabilities`: the items of the list by token (`IGATE`, `MSG_CNT`...), the value empty for a token alone; `agrelo-df`: `bearing` and `quality`; null for anything else")
    timestamp: Stamp | None = Field(description="the time of a positionless weather report (its MMDDhhmm, resolved to the latest such time that is not in the future)")


class DecodedUndecoded(_Model):
    """A field that should have decoded and did not."""
    type: Literal["undecoded"]
    error: str = Field(description="why it did not")
    text: str = Field(description="the information field as latin-1")


Decoded = Annotated[Union[DecodedPosition, DecodedMessage, DecodedObject, DecodedItem, DecodedStatus, DecodedTelemetry, DecodedOther, DecodedUndecoded], Field(discriminator="type")]


class PacketRow(_Model):
    """One packet heard or sent. The rows are the values of the topic `packets`, keyed by `id` as text: the daemon holds the latest 200, a packet that comes is a `set` and the one that falls out of the
    200 a `del`. The page shows them newest first (the highest id)."""
    id: int = Field(ge=0, description="counts up in the order the packets came in this run of the daemon; not kept in the database")
    heard_at: Iso
    direction: Literal["in", "out"] = Field(description="heard on the air, or sent by us")
    source: str = Field(description="who sent the frame we heard; for a third-party packet the iGate (see `gate`); for a packet from the internet the station that sent it")
    sender: str = Field(description="the station the packet is from: `source`, or for a third-party packet the source of the packet inside it")
    destination: str
    path: list[str] = Field(description="the digipeaters, the one that repeated it marked with `*`; for a packet from the internet everything between the destination and the colon of the line (`TCPIP*`, the q-construct `qAC`, the server `T2FINLAND`)")
    kind: Literal["position", "message", "object", "item", "status", "other", "undecoded"] = Field(description="a telemetry report is `other`; its `decoded.type` is `telemetry`")
    route: str = Field(description="how a packet that was heard on the radio reached us: `direct`, `via OH2RCH-2`, `via ? → OH2RCH-2`, `via OH7JHF-1 (internet)` for a third-party packet; empty for a packet of ours and for one from the internet")
    via: Literal["rf", "rf-gated", "is", "dummy"] = Field(description="the channel the packet came by, set once where it was made: `rf` heard on the radio (direct or by digipeaters; every packet of ours too), `rf-gated` heard on the radio as a third-party packet that an iGate put on "
                                                             "the air, `is` received from APRS-IS over the internet (never on the air), `dummy` made up by the Dummy radio (it works as `rf` does and never goes to the internet)")
    gate: str = Field(description="the iGate, for a third-party packet (`via` is `rf-gated`): `source` and `path` are those of the frame we heard (the iGate's), `decoded` is the packet inside it; empty for any other packet")
    summary: str = Field(description="one line, as the log has it")
    tnc2: str = Field(description="the packet as a line of TNC2 monitor text")
    decoded: Decoded


TRAFFIC_KEPT = 50                       # the packets of one station that `station_traffic` reads, the latest


class StationTraffic(_Command):
    """Asks for the latest packets of one station, for the station panel of the Stations tab: those it sent (its own source, or inside a third-party packet an iGate put on the air) and the messages we sent
    to it (a message, an ack, a directed query). Read from the packet log, so that they reach back past the 200 of the topic `packets`; the page adds the packets that come after. While `igate/enabled` is off no packet
    that came from APRS-IS is read, as the topic shows none. Answered with a `station_traffic` message to the page that asked."""
    cmd: Literal["station_traffic"]
    call: str = Field(min_length=1, max_length=64, description="the station, as the `stations` topic has it")


class StationTrafficMsg(_Message):
    """The latest packets of one station (at most 50), the answer to `station_traffic`, the newest first. A third-party packet is looked for among the latest 20000 packets of the log, where an iGate's are."""
    type: Literal["station_traffic"]
    call: str = Field(description="the station asked about")
    packets: list[PacketRow] = Field(description="the packets, as the rows of the topic `packets` but for `id`, which is the packet's number in the log here (the same packet in the topic has its own); the newest first")
