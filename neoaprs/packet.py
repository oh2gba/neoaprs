"""What a heard or sent packet is to the rest of the program: the frame as printable strings and bytes, and what the parser made of it.

Every datetime is timezone-aware UTC. Positions are decimal degrees, south and west negative, speeds km/h, altitudes metres."""
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .aprsextension import Extensions, extension_lines
from .aprsfreq import Frequency, frequency_text
from .aprslocator import Locator
from .aprsstorm import Storm, storm_text
from .aprstelemetry import Telemetry
from .aprsweather import Weather, weather_text


def decode_text(data: bytes) -> str:
    """The text of a comment, a status or a message: UTF-8 when it is, else latin-1 (which cannot fail)."""
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
    weather: Weather | None = None                # the observation of a weather station (symbol code `_`), when the comment held one
    extensions: Extensions | None = None          # PHG, RNG, DFS, the bearing of a DF report or an area object, after the symbol of an uncompressed position (removed from the comment)
    timestamp_local: bool = False                 # the timestamp was in the sender's local time (`/`): the time is as it was sent, not UTC
    locator: Locator | None = None                # the Maidenhead locator in the status text of a Mic-E packet (the position is the Mic-E's own)
    telemetry: Telemetry | None = None            # the base-91 telemetry `|ss11|` the comment carried (APRS 1.2; removed from the comment)
    frequency: Frequency | None = None            # the local information: the frequency (with its tone, offset and range) that the comment began with, or the name of a frequency object (`145.775-A`); removed from the comment, the name's fields too
    storm: Storm | None = None                    # the storm data (APRS101, chapter 12) at the start of the comment of a position or object with the symbol `@` (removed from the comment)
    sign: str | None = None                       # the 1 to 3 characters of a signpost (symbol `\m`), `55` for a comment that began `{55}` (removed from the comment)


@dataclass(frozen=True, slots=True)
class Message:
    """A text message; an ack is a Message with `ack_id` set and no text, a reject one with `rej_id`."""
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
    locator: Locator | None = None                # a Maidenhead locator with a symbol at the start of the report (without a timestamp); `text` is what follows it
    frequency: Frequency | None = None            # the frequency a status text began with (`>145.775MHz T100 -060`): the voice frequency of a tracker that cannot put it in its position; `text` is what follows it


@dataclass(frozen=True, slots=True)
class Other:
    """A data type that is recognised but not (fully) decoded; `kind` is a short word ("weather", "nmea", "query", "capabilities", "test", ...) and `text` the whole information field. A positionless weather
    report (`_`) is decoded: `weather` holds its observation and `timestamp` its time. `items` holds what a small data type says in words: the capabilities of a station by token, the bearing and
    quality of an Agrelo DF report."""
    kind: str
    text: str
    weather: Weather | None = None
    items: dict[str, str] | None = None
    timestamp: datetime | None = None


@dataclass(frozen=True, slots=True)
class Undecoded:
    """A field that should have decoded and did not: `error` says why, `text` is the information field as latin-1."""
    error: str
    text: str


Decoded = Position | Message | ObjectReport | ItemReport | Status | Other | Telemetry | Undecoded

_KINDS: dict[type, str] = {Position: "position", Message: "message", ObjectReport: "object", ItemReport: "item", Status: "status", Other: "other", Telemetry: "other", Undecoded: "undecoded"}


def _line(text: str) -> str:
    """Text on one log line: control characters shown as a question mark."""
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
    """The header of a packet that was wrapped in a third-party frame (`}SRC>DST,PATH:info`), as an iGate sends one it took from the internet: who really sent it, to whom, and the path it went by (text,
    "TCPIP,OH7JHF-1*"). The packet's own `source` and `path` are those of the frame that was heard, the iGate's."""
    source: str
    destination: str
    path: tuple[str, ...] = ()


Via = Literal["rf", "rf-gated", "is", "dummy"]
VIAS: tuple[Via, ...] = ("rf", "rf-gated", "is", "dummy")
RF: Via = "rf"                         # heard on the radio, direct or by digipeaters (and every packet of ours that went out)
RF_GATED: Via = "rf-gated"             # heard on the radio as a third-party packet: an iGate took it from the internet and put it on the air
IS: Via = "is"                         # received from APRS-IS directly over the internet; it was never on the air
DUMMY: Via = "dummy"                   # made up by the Dummy radio, which lets a person try the program with no radio: it goes everywhere a packet of the radio goes, and nowhere beyond this computer

GATEABLE: frozenset[str] = frozenset({RF, RF_GATED})
"""The channels whose packets a consumer that sends to the internet may take. An iGate (or anything else that puts a packet on APRS-IS) MUST check `packet.via in GATEABLE` before it sends: a packet from the internet (`is`)
would go round in a circle, and the made-up traffic of the Dummy radio (`dummy`) must never reach the real network. A new channel is not gateable until it is put here on purpose."""


def via_of(text: str) -> Via:
    """The channel a text names (as the database and the wire write it); raises ValueError for any other."""
    for one in VIAS:
        if one == text:
            return one
    raise ValueError(f"via {text!r} is no channel")


def channel_of(third_party: "ThirdParty | None", internet: bool = False, dummy: bool = False) -> Via:
    """The channel of a packet: `is` for one from APRS-IS, `dummy` for one the Dummy radio made up, else `rf-gated` when it came on the radio as a third-party packet, else `rf`."""
    return IS if internet else DUMMY if dummy else (RF if third_party is None else RF_GATED)


@dataclass(frozen=True, slots=True)
class Packet:
    """A packet that reached us, and how: `via` is the channel and is set once, where the packet is made (the Tnc's frame reader makes `rf`, `rf-gated` and, for the Dummy radio, `dummy`; `aprsisline.parse_is_line` makes `is`) and never
    changes. An `is` packet has no AX.25 frame: its `raw` is the line of APRS-IS as it came (TNC2 text), `path` holds everything between the destination and the colon (the q-construct and the server too)."""
    heard_at: datetime
    direction: Literal["in", "out"]
    raw: bytes
    source: str
    destination: str
    path: tuple[str, ...]
    info: bytes
    decoded: Decoded                  # what the information field says; for a third-party packet, what the wrapped packet says
    third_party: ThirdParty | None = None
    via: Via = RF

    def __post_init__(self) -> None:
        if self.heard_at.tzinfo is None:
            raise ValueError("heard_at must be timezone-aware UTC")
        if self.via not in VIAS:
            raise ValueError(f"via {self.via!r} is no channel")
        if self.via == IS and self.direction != "in":
            raise ValueError("a packet sent by us never goes by the internet")
        if (self.via == RF_GATED) != (self.third_party is not None and self.via not in (IS, DUMMY)):
            raise ValueError("a packet is rf-gated exactly when it came on the radio as a third-party packet")

    @property
    def kind(self) -> str:
        """"position", "message", "object", "item", "status", "other" or "undecoded"."""
        return _KINDS[type(self.decoded)]

    @property
    def sender(self) -> str:
        """The station the packet is from: its source, or for a third-party packet the source of the packet inside."""
        return self.source if self.third_party is None else self.third_party.source

    @property
    def inner_info(self) -> bytes:
        """The information field `decoded` was read from: the packet's own, or for a third-party packet the one inside its header (`}SRC>DST,PATH:`, which ends at the first colon)."""
        return self.info if self.third_party is None else self.info.partition(b":")[2]

    @property
    def gate(self) -> str:
        """The iGate that put a third-party packet on the air (the call of the frame we heard); empty for any other packet, an `is` packet too: it was never on the air."""
        return self.source if self.via == RF_GATED else ""

    @property
    def on_air(self) -> bool:
        """Whether the packet was on the radio channel (heard, or sent by us; the Dummy radio's too). The services that answer, acknowledge, repeat or send take only these."""
        return self.via != IS

    @property
    def weather_report(self) -> tuple[str, Weather] | None:
        """The weather this packet reports and whose it is: the sender's for a position or a positionless report, the object's or item's own name for a live object or item; None for any other packet."""
        d = self.decoded
        if isinstance(d, (Position, Other)):
            return None if d.weather is None else (self.sender, d.weather)
        if isinstance(d, (ObjectReport, ItemReport)) and d.alive and d.position.weather is not None:
            return d.name, d.position.weather
        return None

    @property
    def summary(self) -> str:
        """One line for a log; a third-party packet ends with who put it on the air, one from the internet with where it came from."""
        text = _summary_of(self.decoded)
        if self.via == IS:
            return f"{text} (APRS-IS)"
        return text if self.third_party is None else f"{text} via {self.source} (third-party)"
