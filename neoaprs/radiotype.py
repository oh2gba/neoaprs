"""What a type of radio is, as plain values: its kind (fm, hf, lora), what the device cannot do (`Limits`), what we decided it may do (`Allowed`), what the page's box of it offers (`Can`) and its own settings
(`Field`). One `RadioType` for each entry of the list the operator chooses from; the registry of them is the package neoaprs/radiotypes/, one module for each family of types and one line each.

A radio is named by its id (`RadioId`, an integer of the `radio` table, never used again); FM_ID and HF_ID are the ids of today's two radios, the ones the migration gives them and the ones the code uses
before it exists. `radio_id_of` reads the kind of a slot as it is stored today (`fm`, `hf`, "" for none) as the id of its radio. No I/O."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final, Literal

from .coded import CodedError

Kind = Literal["fm", "hf", "lora"]
KINDS: tuple[Kind, ...] = ("fm", "hf", "lora")              # the order of the page's lists and of the numbering within a kind ("FM", "HF 2")
LOCAL_KINDS: frozenset[Kind] = frozenset({"fm", "lora"})     # rule 3.2: heard on a local kind wins over hf within the recent time (policy.MESSAGE_RADIO_RECENT_HOURS)

RadioId = int
FM_ID: Final = 1                     # the ids the migration gives today's radios: the FM radio (tnc/profile) ...
HF_ID: Final = 2                     # ... and the HF radio (hf/profile); the same ids are used before the migration exists

ResourceKind = Literal["serial", "sound_card", "keying", "modem_ports", "gps"]
FieldKind = Literal["text", "int", "bool", "choice", "port", "path"]
Transport = Literal["serial", "tcp", "dummy", "modem"]        # "tcp": a program or a bridge reached by host and port; "serial": a serial port (which may be a socket:// URL); "dummy": no line, made-up traffic; "modem": a modem program the daemon starts itself


@dataclass(frozen=True)
class Limits:
    """What the device cannot do: constants of the type (neoaprs/radiorules.py says why each number is what it is)."""
    max_frame: int | None             # the longest AX.25 frame carried whole (Mercury 123); None: AX.25's own
    beacon_min_min: int               # the floor of the beacon interval on this radio (FM 20, HF 30)
    beacon_jitter_sec: int            # the longest random pause after a timed beacon (HF 300); 0: none
    retry_jitter_sec: int             # the longest pause before a retry of a message (HF 20); 0: none
    max_text: int | None = None       # the longest TNC2 text of a frame carried whole, where the air carries text (LoRa 252: its packet is a header of 3 bytes and the text); None: the air carries AX.25
    max_kiss: int | None = None       # the longest KISS frame of ours its line takes, both FENDs, the command byte and the escapes counted (LoRa 256: a board's input of 255 bytes); None: no limit of its own


@dataclass(frozen=True)
class Allowed:
    """What we decided for the type and is not the operator's: a control exists only where it is True."""
    paths: bool                       # our frames may carry digipeaters
    digipeat: bool                    # it may repeat what it hears
    smart_beacon: bool                # SmartBeaconing applies
    gateway_heard: bool               # internet gateways hear this kind (the email radio, rule 3.5)
    shared_channel: bool              # a 1200-baud shared channel: the ALOHA circle is worked out for it (rule 3.8)


@dataclass(frozen=True)
class Can:
    """What the type can do: the controls of its box on the page follow it."""
    find: bool                        # Find my radio (a serial line)
    terminal: bool
    tune: bool
    key_test: bool
    scope: bool
    tx_gain: bool
    frequencies: bool                 # the suggested dials are shown in its box
    transmit: bool = True             # it can send: False for a radio that only listens (the receive-only types: a TNC's text, a LoRa iGate's log), which no rule picks to send on and whose line is never written to


@dataclass(frozen=True)
class Field:
    """One setting of a radio, by its own key (`radio/<id>/<key>` on the wire from wave 4 on)."""
    key: str                          # "port", "baud", "tcp_host", "tcp_port", "sound_card", "keying", "tx_gain_db", "beacon", "path", "digipeat"
    kind: FieldKind
    parse: Callable[[str], Any]       # text -> value; ValueError (a CodedError) with the reason: the parsers of the flat settings of today (configvalues.py, configtypes.py)
    default: str                      # as text, as the settings table keeps it
    range: tuple[int, int] | None = None
    choices: tuple[str, ...] = ()
    together: str = ""                # fields with the same word are sent in one set_config ("tcp": tcp_host and tcp_port)
    text: str = ""                    # the catalogue id of its label (the words are the page's): "radio.field.port"
    claims: ResourceKind | None = None    # the value is a resource the claims table holds (neoaprs/claims.py)


@dataclass(frozen=True)
class RadioType:
    key: str                          # the stored type: kiss, kenwood-tnc2, kenwood-d710, kantronics, kiss-tcp, dummy, mercury, dummy-hf
    kind: Kind
    name: str                         # English, for the log and the support bundle (the page has its own words by `text`)
    text: str                         # the catalogue id of its name: "radio.type.kiss"
    transport: Transport
    driver: str                       # the adapters' driver by key: "tnc" (serial, tcp and dummy lines) or "mercury"
    profile: str                      # the tncprofile key its line speaks (the KISS entry, the probe); "" for none
    fields: tuple[Field, ...]         # its own fields, then the common ones it is allowed (radiotypes/common.py: beacon always, path and digipeat where allowed)
    limits: Limits
    allowed: Allowed
    can: Can
    dummy: bool                       # made-up traffic: the dashed tag
    recommended_path: str = ""        # the path of our frames on it when its own "path" is empty (LoRa WIDE1-1, as its networks repeat); "": the recommended path of the station's symbol (FM's)

    def field(self, key: str) -> Field | None:
        """Its field of this key; None when it has none."""
        return next((f for f in self.fields if f.key == key), None)


class RadioTypeError(CodedError):
    """A type that is not one: the code `radio.unknown_type` with the `type` named (radiotypes.type_of)."""


def radio_id_of(slot: str) -> RadioId | None:
    """The id of the radio that today's word for a slot names: `fm` radio 1, `hf` radio 2, "" (the internet, or no radio) None."""
    return FM_ID if slot == "fm" else HF_ID if slot == "hf" else None


def stored_text(value: Any) -> str:
    """A value as the settings table keeps it: "" for None, true/false, a float without trailing zeros, anything else as str()."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return str(value)
