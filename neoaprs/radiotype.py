"""What a type of radio is, as plain values: its kind, `Limits`, `Allowed`, `Can` and `Field`s.

A radio is named by its id (`RadioId`, a never reused integer). No I/O.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final, Literal

from . import kiss
from .coded import CodedError, Reason

Kind = Literal["fm", "hf", "lora"]
KINDS: tuple[Kind, ...] = ("fm", "hf", "lora")
LOCAL_KINDS: frozenset[Kind] = frozenset({"fm", "lora"})

# the numbers of the kinds (see the developer notes)
FM_BEACON_MIN_MIN = 20
FM_BEACON_JITTER_SEC = 30
HF_BEACON_MIN_MIN = 30
HF_BEACON_JITTER_SEC = 300
HF_MAX_FRAME = 123
HF_RETRY_JITTER_SEC = 20
LORA_BEACON_MIN_MIN = 30
LORA_BEACON_JITTER_SEC = 300
LORA_RETRY_JITTER_SEC = 20
# 250 leaves room for three KISS escapes in 255
LORA_MAX_FRAME = 250
LORA_MAX_KISS = 256

RadioId = int
FM_ID: Final = 1
HF_ID: Final = 2

ResourceKind = Literal["serial", "sound_card", "keying", "modem_ports", "gps"]
ONLY_RECEIVES = Reason("the radio only receives", "transmit.off")
FieldKind = Literal["text", "int", "bool", "choice", "port", "path"]
Transport = Literal["serial", "tcp", "dummy", "modem"]


@dataclass(frozen=True)
class Limits:
    """What the device cannot do."""

    max_frame: int | None
    beacon_min_min: int
    beacon_jitter_sec: int  # the most of the random pause before every send by the clock
    retry_jitter_sec: int
    max_text: int | None = None
    max_kiss: int | None = None

    def too_long(self, raw: bytes, text: bytes) -> str | None:
        """Return why a frame is longer than the radio carries, as a clause, or None."""
        if self.max_frame is not None and len(raw) > self.max_frame:
            return f"{len(raw)} bytes, the radio carries {self.max_frame}"
        if self.max_text is not None and len(text) > self.max_text:
            return f"{len(text)} bytes of text, the radio carries {self.max_text}"
        if self.max_kiss is not None and (size := len(kiss.encode(raw))) > self.max_kiss:
            return f"{size} bytes in KISS, the radio takes {self.max_kiss}"
        return None


@dataclass(frozen=True)
class Allowed:
    """What was decided for the type: a control exists only where it is True."""

    paths: bool
    digipeat: bool
    smart_beacon: bool
    gateway_heard: bool
    shared_channel: bool


@dataclass(frozen=True)
class Can:
    """What the type can do; the controls of its box follow."""

    find: bool
    terminal: bool
    tune: bool
    key_test: bool
    scope: bool
    tx_gain: bool
    frequencies: bool
    transmit: bool = True
    rx_level: bool = False


@dataclass(frozen=True)
class Field:
    """One setting of a radio, by its own key."""

    key: str
    kind: FieldKind
    parse: Callable[[str], Any]
    default: str
    range: tuple[int, int] | None = None
    choices: tuple[str, ...] = ()
    together: str = ""
    text: str = ""
    claims: ResourceKind | None = None


@dataclass(frozen=True)
class RadioType:
    key: str
    kind: Kind
    name: str
    text: str
    transport: Transport
    # the driver key: "tnc", "mercury" or "direwolf"
    driver: str
    profile: str
    fields: tuple[Field, ...]
    limits: Limits
    allowed: Allowed
    can: Can
    dummy: bool
    recommended_path: str = ""
    systems: frozenset[str] = frozenset()

    def field(self, key: str) -> Field | None:
        return next((f for f in self.fields if f.key == key), None)


class RadioTypeError(CodedError):
    """An unknown radio type (code `radio.unknown_type`)."""


def radio_id_of(slot: str) -> RadioId | None:
    """Return the id a slot word names (`fm` 1, `hf` 2), else None."""
    return FM_ID if slot == "fm" else HF_ID if slot == "hf" else None


def stored_text(value: Any) -> str:
    """Return a value as the settings table keeps it."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return str(value)
