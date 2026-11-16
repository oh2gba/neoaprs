"""What a type of radio is, as plain values: its kind (fm, hf, lora), what the device cannot do (`Limits`), what we decided it may do (`Allowed`), what the page's box of it offers (`Can`) and its own settings
(`Field`). One `RadioType` for each entry of the list the operator chooses from; the registry of them is the package neoaprs/radiotypes/, one module for each family of types and one line each.

A radio is named by its id (`RadioId`, an integer of the `radio` table, never used again); FM_ID and HF_ID are the ids of today's two radios, the ones the migration gives them and the ones the code uses
before it exists. `radio_id_of` reads the kind of a slot as it is stored today (`fm`, `hf`, "" for none) as the id of its radio. No I/O."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final, Literal

from . import kiss
from .coded import CodedError, Reason

Kind = Literal["fm", "hf", "lora"]
KINDS: tuple[Kind, ...] = ("fm", "hf", "lora")              # the order of the page's lists and of the numbering within a kind ("FM", "HF 2")
LOCAL_KINDS: frozenset[Kind] = frozenset({"fm", "lora"})     # rule 3.2: heard on a local kind wins over hf within the recent time (policy.MESSAGE_RADIO_RECENT_HOURS)

# The numbers of the kinds (radiotypes/common.py makes their `Limits` and `Allowed` of them), and why each is what it is:
# - FM: the paths and the fill-in digipeater of the VHF network, SmartBeaconing for a moving station, the beacon from 20 minutes (the net cycle of a 2-hop path), AX.25's own frame limit.
# - HF (Mercury): no path ever (every station on the mode hears every frame direct, there are no digipeaters, and a path costs bytes of a frame that carries 123); no digipeater (a repeat would only fill a channel
#   every station already hears); no SmartBeaconing (a moving station sends its timed beacon with the current fix: on HF a report every few tens of seconds in a turn would take the channel for everyone); the one
#   beacon interval of the station (`beacon/interval_min`) with a floor of 30 minutes on this radio (John's rule: not very often, a frame of 3.8 s on a shared channel); a random pause of up to HF_BEACON_JITTER_SEC after
#   each interval, because fixed stations have stable clocks and those that started their hour at the same moment would key up together on one channel every hour from then on (the start of the daemon is a random
#   phase already; the pause keeps two stations on the same interval apart afterwards). The size was measured by `scripts/mercury-measure beacons` (docs/mercury.md): on the 30-minute interval with a frame of 3.8 s,
#   stations that started within one minute of each other lose 14 percent of their beacons without the pause when there are two of them and 43 percent when there are five; with the pause of 300 s they lose 0.8 and
#   2.7 percent, within a point of what stations with random phases lose by chance (0.4 and 1.6 percent: the floor), while a pause of 120 s leaves them at 1.3 and 5.0 percent. A beacon lost by chance is made up by
#   the next one; tests/test_mercury.py samples the pause. Frames up to the 123 bytes the mode carries.
# - LoRa (a LoRa APRS board; the Dummy LoRa radio is the first type of the kind, aprs-reference/lora-plan.md section 3.2): paths, as the LoRa networks use WIDE1-1 and their iGates repeat it, and
#   no digipeating by us (a second repeat of each frame would hold the one shared channel twice as long); SmartBeaconing, whose fastest rate (60 s) is the trackers' own; a frame of ours takes 2 to 4 s
#   on the air at SF12, close to Mercury's 3.8 s, on one channel that every station shares, so the beacon's floor, its random pause and the pause before a retry are HF's (the floor of 30 minutes
#   is John's to confirm: the firmwares beacon every 15); frames up to 250 bytes, which the boards in use take over KISS whole (their buffer of 255 bytes counts the KISS bytes around the frame, so a frame whose escapes would not fit is
#   shortened or refused too: LORA_MAX_KISS),
#   and 252 bytes of text on the air, where a packet is the text after a header of 3 bytes in a buffer of 255 (tnc2line.MAX_TEXT).
FM_BEACON_MIN_MIN = 20
HF_BEACON_MIN_MIN = 30                 # the floor of beacon/interval_min on an HF radio (an FM radio's: FM_BEACON_MIN_MIN)
HF_BEACON_JITTER_SEC = 300             # measured: the smallest pause that puts stations started together within a point of the random-phase floor (above; docs/mercury.md)
HF_MAX_FRAME = 123
HF_RETRY_JITTER_SEC = 20               # the longest pause added before each retry of a message on HF: two stations that sent at the same moment collided, and their retries, 32 s and 64 s later to the second,
                                       # collided again (John and OH2GAX, 4 Nov 2026); a frame keys the radio for about 4 s and the channel-busy check needs about a second to see another station start
LORA_BEACON_MIN_MIN = 30               # a LoRa frame of ours is as long on the air as an HF one, on one shared channel: HF's floor (above)
LORA_BEACON_JITTER_SEC = 300           # HF's pause, measured for a frame of 3.8 s; not measured on LoRa
LORA_RETRY_JITTER_SEC = 20             # as on HF: the retries of two stations that collided collide again
LORA_MAX_FRAME = 250                   # the boards clear their KISS input past 255 bytes, which count the FENDs, the command byte and the escapes: 250 leaves room for three escapes
LORA_MAX_KISS = 256                    # the whole KISS frame a board takes: the CA2RXU iGate clears its input when it passes 255 bytes before the closing FEND (tnc_utils.cpp handleInputDataKISS)

RadioId = int
FM_ID: Final = 1                     # the ids the migration gives today's radios: the FM radio (tnc/profile) ...
HF_ID: Final = 2                     # ... and the HF radio (hf/profile); the same ids are used before the migration exists

ResourceKind = Literal["serial", "sound_card", "keying", "modem_ports", "gps"]
ONLY_RECEIVES = Reason("the radio only receives", "transmit.off")         # why a radio of a type that sends nothing (Can.transmit false) takes no frame and sends no beacon
FieldKind = Literal["text", "int", "bool", "choice", "port", "path"]
Transport = Literal["serial", "tcp", "dummy", "modem"]        # "tcp": a program or a bridge reached by host and port; "serial": a serial port (which may be a socket:// URL); "dummy": no line, made-up traffic; "modem": a modem program the daemon starts itself


@dataclass(frozen=True)
class Limits:
    """What the device cannot do: constants of the type (the numbers of the kinds above say why each is what it is)."""
    max_frame: int | None             # the longest AX.25 frame carried whole (Mercury 123); None: AX.25's own
    beacon_min_min: int               # the floor of the beacon interval on this radio (FM 20, HF 30)
    beacon_jitter_sec: int            # the longest random pause after a timed beacon (HF 300); 0: none
    retry_jitter_sec: int             # the longest pause before a retry of a message (HF 20); 0: none
    max_text: int | None = None       # the longest TNC2 text of a frame carried whole, where the air carries text (LoRa 252: its packet is a header of 3 bytes and the text); None: the air carries AX.25
    max_kiss: int | None = None       # the longest KISS frame of ours its line takes, both FENDs, the command byte and the escapes counted (LoRa 256: a board's input of 255 bytes); None: no limit of its own

    def too_long(self, raw: bytes, text: bytes) -> str | None:
        """Why a frame (its AX.25 bytes, its TNC2 text) is longer than the radio carries whole, as a clause: "131 bytes, the radio carries 123", "256 bytes of text, the radio carries 252", "257 bytes in KISS,
        the radio takes 256"; None when it fits."""
        if self.max_frame is not None and len(raw) > self.max_frame:
            return f"{len(raw)} bytes, the radio carries {self.max_frame}"
        if self.max_text is not None and len(text) > self.max_text:
            return f"{len(text)} bytes of text, the radio carries {self.max_text}"
        if self.max_kiss is not None and (size := len(kiss.encode(raw))) > self.max_kiss:
            return f"{size} bytes in KISS, the radio takes {self.max_kiss}"
        return None


@dataclass(frozen=True)
class Allowed:
    """What we decided for the type and is not the operator's: a control exists only where it is True."""
    paths: bool                       # our frames may carry digipeaters
    digipeat: bool                    # it may repeat what it hears
    smart_beacon: bool                # SmartBeaconing applies
    gateway_heard: bool               # internet gateways hear this kind
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
    rx_level: bool = False            # the level of the packets it hears is shown in its box (a sound-card modem's)


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
    driver: str                       # the adapters' driver by key: "tnc" (serial, tcp and dummy lines), "mercury" or "direwolf"
    profile: str                      # the tncprofile key its line speaks (the KISS entry, the probe); "" for none
    fields: tuple[Field, ...]         # its own fields, then the common ones it is allowed (radiotypes/common.py: beacon always, path and digipeat where allowed)
    limits: Limits
    allowed: Allowed
    can: Can
    dummy: bool                       # it reaches no radio (no port, no radio's sound card) and makes its traffic up: the dashed tag, and Add radio's group of the types for trying the program out (Without a radio)
    recommended_path: str = ""        # the path of our frames on it when its own "path" is empty (LoRa WIDE1-1, as its networks repeat); "": the recommended path of the station's symbol (FM's)
    systems: frozenset[str] = frozenset()     # the systems (sys.platform) whose installations carry the type's program; empty: every system. A type is offered only where its program is

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
