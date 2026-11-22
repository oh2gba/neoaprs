"""What a heard or sent packet is to the program: the frame and what the parser made of it.

Datetimes are UTC-aware; positions decimal degrees, speeds km/h, altitudes metres.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .aprsextension import Extensions, extension_lines
from .aprsfreq import Frequency, frequency_text
from .aprslocator import Locator
from .aprsstorm import Storm, storm_text
from .aprstelemetry import Telemetry
from .aprsweather import Weather, weather_text
from .radiotype import RadioId


DuplicateKey = tuple[str, str, bytes]


def duplicate_key(source: str, destination: str, information: bytes) -> DuplicateKey:
    """Return what makes two copies of a packet the same: source, destination without SSID, info."""
    return source, destination.partition("-")[0], information


def decode_text(data: bytes) -> str:
    """Return the text as UTF-8 if valid, else latin-1."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


@dataclass(frozen=True, slots=True)
class Position:
    lat: float
    lon: float
    symbol_table: str
    symbol_code: str
    comment: str = ""
    course_deg: int | None = None
    speed_kmh: float | None = None
    altitude_m: float | None = None
    timestamp: datetime | None = None
    messaging: bool = False
    compressed: bool = False
    ambiguity: int = 0
    weather: Weather | None = None
    # PHG, RNG, DFS, DF bearing or area object (removed from the comment)
    extensions: Extensions | None = None
    # the timestamp was in the sender's local time (`/`)
    timestamp_local: bool = False
    locator: Locator | None = None
    # base-91 telemetry `|ss11|` (APRS 1.2; removed from the comment)
    telemetry: Telemetry | None = None
    # the frequency the comment began with, or a frequency object's name (removed)
    frequency: Frequency | None = None
    # storm data (APRS101 ch. 12) at the start of the comment (removed)
    storm: Storm | None = None
    # signpost text (symbol `\m`): `55` for a comment beginning `{55}` (removed)
    sign: str | None = None


@dataclass(frozen=True, slots=True)
class Message:
    """A text message; an ack has `ack_id` set and no text, a reject `rej_id`."""
    addressee: str
    text: str
    msg_id: str | None = None
    ack_id: str | None = None
    rej_id: str | None = None


@dataclass(frozen=True, slots=True)
class ObjectReport:
    name: str
    alive: bool
    position: Position
    timestamp: datetime | None = None


@dataclass(frozen=True, slots=True)
class ItemReport:
    name: str
    alive: bool
    position: Position


@dataclass(frozen=True, slots=True)
class Status:
    text: str
    timestamp: datetime | None = None
    locator: Locator | None = None
    # the frequency a status text began with (`>145.775MHz T100 -060`)
    frequency: Frequency | None = None


@dataclass(frozen=True, slots=True)
class Other:
    """A data type recognised but not fully decoded: `kind` is a word, `text` the info field."""
    kind: str
    text: str
    weather: Weather | None = None
    items: dict[str, str] | None = None
    timestamp: datetime | None = None


@dataclass(frozen=True, slots=True)
class Undecoded:
    """A field that should have decoded and did not: `error` for the log, `code` what failed."""
    error: str
    text: str
    code: str = "damaged"


UNDECODED_CODES = ("empty", "position", "mice", "message", "nmea", "damaged")
Decoded = Position | Message | ObjectReport | ItemReport | Status | Other | Telemetry | Undecoded

_KINDS: dict[type, str] = {Position: "position", Message: "message", ObjectReport: "object", ItemReport: "item", Status: "status", Other: "other", Telemetry: "other", Undecoded: "undecoded"}


def _line(text: str) -> str:
    return "".join(c if c.isprintable() else "?" for c in text)


def _where(p: Position) -> str:
    weather = f" weather: {weather_text(p.weather)}" if p.weather else ""
    comment = f"{' -' if weather else ''} {_line(p.comment)}" if p.comment else ""
    extensions = f" [{', '.join(extension_lines(p.extensions))}]" if p.extensions else ""
    local = f" (time {p.timestamp:%d %H:%M} local)" if p.timestamp and p.timestamp_local else ""
    locator = f" locator {p.locator.grid}" if p.locator else ""
    local_info = "".join(f" [{text}]" for text in (p.frequency and frequency_text(p.frequency), p.storm and storm_text(p.storm), p.sign and f"sign {p.sign}") if text)
    return f"{p.lat:.4f} {p.lon:.4f} {p.symbol_table}{p.symbol_code}{local}{locator}{extensions}{local_info}{weather}{comment}"


def _message_summary(m: Message) -> str:
    if m.ack_id is not None:
        return f"ack {m.ack_id} to {m.addressee}"
    if m.rej_id is not None:
        return f"reject {m.rej_id} to {m.addressee}"
    ident = f" {{{m.msg_id}}}" if m.msg_id is not None else ""
    return f"message to {m.addressee}: {_line(m.text)}{ident}"


def _summary_of(d: Decoded) -> str:
    match d:
        case Position():
            return f"position {_where(d)}"
        case Message():
            return _message_summary(d)
        case ObjectReport():
            return f"object {d.name} {'alive' if d.alive else 'killed'} {_where(d.position)}"
        case ItemReport():
            return f"item {d.name} {'alive' if d.alive else 'killed'} {_where(d.position)}"
        case Status():
            return f"status {'locator ' + d.locator.grid + ' ' if d.locator else ''}{'[' + frequency_text(d.frequency) + '] ' if d.frequency else ''}{_line(d.text)}".rstrip()
        case Telemetry():
            return f"telemetry #{'MIC' if d.sequence is None else d.sequence}: {' '.join(f'{v:g}' for v in d.analog)} {d.bits}{' ' + _line(d.comment) if d.comment else ''}"
        case Other():
            return f"weather: {weather_text(d.weather)}" if d.weather else f"{d.kind}: {_line(d.text)}"
        case Undecoded():
            return f"undecoded ({d.error}): {_line(d.text)}"


@dataclass(frozen=True, slots=True)
class ThirdParty:
    """The header of a packet wrapped in a third-party frame (`}SRC>DST,PATH:info`)."""
    source: str
    destination: str
    path: tuple[str, ...] = ()


Via = Literal["rf", "rf-gated", "is", "dummy"]
VIAS: tuple[Via, ...] = ("rf", "rf-gated", "is", "dummy")
# heard on the radio, or sent by us
RF: Via = "rf"
# heard on the radio as a third-party packet from the internet
RF_GATED: Via = "rf-gated"
IS: Via = "is"  # received from APRS-IS; never on the air
# made up by the Dummy radio: never beyond this computer
DUMMY: Via = "dummy"

GATEABLE: frozenset[str] = frozenset({RF, RF_GATED})
"""The channels whose packets a consumer that sends to the internet may take. An iGate (or anything else that puts a packet on APRS-IS) MUST check `packet.via in GATEABLE` before it sends: a packet from the internet (`is`)
would go round in a circle, and the made-up traffic of the Dummy radio (`dummy`) must never reach the real network. A new channel is not gateable until it is put here on purpose."""


def via_of(text: str) -> Via:
    for one in VIAS:
        if one == text:
            return one
    raise ValueError(f"via {text!r} is no channel")


def channel_of(third_party: "ThirdParty | None", internet: bool = False, dummy: bool = False) -> Via:
    return IS if internet else DUMMY if dummy else (RF if third_party is None else RF_GATED)


@dataclass(frozen=True, slots=True)
class Packet:
    """A packet that reached us; `via` is its channel. An `is` packet has no AX.25 frame."""
    heard_at: datetime
    direction: Literal["in", "out"]
    raw: bytes
    source: str
    destination: str
    path: tuple[str, ...]
    info: bytes
    # what the information field says; for a third-party packet, what the wrapped packet says
    decoded: Decoded
    third_party: ThirdParty | None = None
    via: Via = RF
    # the radio it came on or went out on; None for an internet packet
    radio_id: RadioId | None = None
    # SNR (dB) and RSSI (dBm) the radio measured; None if it gave none
    snr: float | None = None
    rssi: float | None = None

    def __post_init__(self) -> None:
        if self.heard_at.tzinfo is None:
            raise ValueError("heard_at must be timezone-aware UTC")
        if self.via not in VIAS:
            raise ValueError(f"via {self.via!r} is no channel")
        if self.radio_id is not None and (type(self.radio_id) is not int or self.radio_id < 1):
            raise ValueError(f"radio {self.radio_id!r} is no radio: an id from 1, or None")
        if self.via == IS and self.direction != "in":
            raise ValueError("a packet sent by us never goes by the internet")
        if (self.via == RF_GATED) != (self.third_party is not None and self.via not in (IS, DUMMY)):
            raise ValueError("a packet is rf-gated exactly when it came on the radio as a third-party packet")

    @property
    def kind(self) -> str:
        return _KINDS[type(self.decoded)]

    @property
    def sender(self) -> str:
        return self.source if self.third_party is None else self.third_party.source

    @property
    def inner_info(self) -> bytes:
        """Return the information field `decoded` was read from (inside a third-party header)."""
        return self.info if self.third_party is None else self.info.partition(b":")[2]

    @property
    def gate(self) -> str:
        return self.source if self.via == RF_GATED else ""

    @property
    def on_air(self) -> bool:
        """Return whether the packet was on the radio channel, Dummy included."""
        return self.via != IS

    @property
    def weather_report(self) -> tuple[str, Weather] | None:
        """Return (station or object name, weather) this packet reports; None otherwise."""
        d = self.decoded
        if isinstance(d, (Position, Other)):
            return None if d.weather is None else (self.sender, d.weather)
        if isinstance(d, (ObjectReport, ItemReport)) and d.alive and d.position.weather is not None:
            return d.name, d.position.weather
        return None

    @property
    def summary(self) -> str:
        text = _summary_of(self.decoded)
        if self.via == IS:
            return f"{text} (APRS-IS)"
        return text if self.third_party is None else f"{text} via {self.source} (third-party)"
