"""What a heard or sent packet is to the rest of the program: the frame as printable strings and bytes, and what the parser made of it.

Every datetime is timezone-aware UTC. Positions are decimal degrees, south and west negative, speeds km/h, altitudes metres."""
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from .aprsextension import Extensions, extension_lines
from .aprsfreq import Frequency, frequency_text
from .aprslocator import Locator
from .aprsstorm import Storm, storm_text
from .aprstelemetry import Telemetry
from .aprsweather import Weather, weather_text
from .radiotype import FM_ID, HF_ID, RadioId, radio_id_of


def old_keywords[T](**old: str) -> Callable[[type[T]], type[T]]:
    """For a dataclass one of whose fields took a new name and form (the radio as an id: `radio` became `radio_id`): its constructor still takes the old keyword, `old="field"`, as the value of the field it
    became; the class's own `__post_init__` turns a value of the old form (a word) in the field into the new, so the old value is taken by name and in its old place alike. `dataclasses.replace` goes through
    the constructor, so it takes both names too; it hands over the field as it was beside the old keyword, so the old keyword wins where both are given. The old name is read through a view of the class's
    own. Until W3 takes the old names away."""
    def wrap(cls: type[T]) -> type[T]:
        made = cls.__init__

        def init(self: T, *args: Any, **values: Any) -> None:
            for name, new in old.items():
                if name in values:
                    values[new] = values.pop(name)
            made(self, *args, **values)

        init.__wrapped__ = made                             # type: ignore[attr-defined]
        cls.__init__ = init                                 # type: ignore[method-assign, assignment]
        return cls
    return wrap


def radio_word(radio: RadioId | None) -> str:
    """Today's word for the slot of a radio, as the old views say it (the inverse of radiotype.radio_id_of): `fm` for radio 1, `hf` for radio 2, "" for none and for any other radio, which had no word."""
    return "fm" if radio == FM_ID else "hf" if radio == HF_ID else ""


def id_of_word(word: str) -> RadioId | None:
    """The id an old word names (`fm` 1, `hf` 2, "" none); ValueError for a word that was none of RADIOS."""
    if word not in RADIOS:
        raise ValueError(f"radio {word!r} is no radio: {RADIOS}")
    return radio_id_of(word)


DuplicateKey = tuple[str, str, bytes]


def duplicate_key(source: str, destination: str, information: bytes) -> DuplicateKey:
    """What makes two copies of a packet the same one, for a digipeater and an iGate: the source, the destination without its SSID and the information field; the path is not part of it (the server's own test, and
    WB2OSZ's digipeater algorithm). A copy is a duplicate within policy.DIGI_DUPLICATE_SEC."""
    return source, destination.partition("-")[0], information


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
RADIOS: tuple[str, ...] = ("", "fm", "hf")      # what the old view Packet.radio says: the word of the slot of radio 1 (`fm`) or radio 2 (`hf`), or none (the internet, no radio, and any other radio)

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


@old_keywords(radio="radio_id")
@dataclass(frozen=True, slots=True)
class Packet:
    """A packet that reached us, and how: `via` is the channel and is set once, where the packet is made (the Tnc's frame reader makes `rf`, `rf-gated` and, for the Dummy radio, `dummy`; `aprsisline.parse_is_line` makes `is`) and never
    changes. An `is` packet has no AX.25 frame: its `raw` is the line of APRS-IS as it came (TNC2 text), `path` holds everything between the destination and the colon (the q-construct and the server too).

    The radio is kept as its id (`radio_id`). The old word `radio` (`fm`, `hf`, "") is a view of it and is still taken by the constructor, by name (`Packet(..., radio="hf")`, `replace(packet, radio="fm")`)
    and in its old place (the eleventh value), until W3."""
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
    if TYPE_CHECKING:                 # (what a type checker is told: the old word `radio` is taken in its old place and read, the id by its name; in the running program `radio` is the view below, no field)
        radio: str = ""
        radio_id: RadioId | None = field(default=None, kw_only=True)
    else:
        radio_id: RadioId | None = None   # the radio it came on or went out on, by its id (neoaprs/radiospec.py), set where the Tnc makes the packet; None for a packet from the internet, and for one made without a radio (a test's), which counts as radio 1's
    snr: float | None = None          # the signal-to-noise ratio the radio measured of the frame, dB, and the received strength, dBm (neoaprs/reading.py): set where the Tnc makes the packet, of the radio types that give
    rssi: float | None = None         # them; None for a packet of ours, one from the internet, and one of a radio that gives none

    def __post_init__(self) -> None:
        if self.heard_at.tzinfo is None:
            raise ValueError("heard_at must be timezone-aware UTC")
        if self.via not in VIAS:
            raise ValueError(f"via {self.via!r} is no channel")
        given: object = self.radio_id
        if isinstance(given, str):                                              # (the old word, by name or in its old place)
            object.__setattr__(self, "radio_id", id_of_word(given))
        if self.radio_id is not None and (type(self.radio_id) is not int or self.radio_id < 1):
            raise ValueError(f"radio {self.radio_id!r} is no radio: an id from 1, or None")
        if self.via == IS and self.direction != "in":
            raise ValueError("a packet sent by us never goes by the internet")
        if (self.via == RF_GATED) != (self.third_party is not None and self.via not in (IS, DUMMY)):
            raise ValueError("a packet is rf-gated exactly when it came on the radio as a third-party packet")

    if not TYPE_CHECKING:
        @property
        def radio(self) -> str:
            """The old word for the radio (`radio_id` as the word of its slot: 1 `fm`, 2 `hf`); "" for none and for any other radio."""
            return radio_word(self.radio_id)

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
