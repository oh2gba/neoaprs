"""TNC profiles: how to enter and leave KISS mode, whether a TNC can be probed, how it is reached.

One record per kind of device; the `Tnc` does what the record says and nothing else. `enter` is
a list of (bytes, seconds to wait) steps; the last wait is the settle time. No I/O here.
"""

from dataclasses import dataclass
from typing import Literal

from . import kiss
from .coded import CodedError
from .radiotype import Transport as Transport
from .reading import ReadingKind

# the KISS "return" command (FEND, 0xFF, FEND): the TNC leaves KISS mode
KISS_EXIT = b"\xc0\xff\xc0"

Step = tuple[bytes, float]
TextLines = Literal["", "tnc2", "console"]


@dataclass(frozen=True)
class Profile:
    key: str  # the value of tnc/profile
    name: str  # the English name of its radio type, under its kind (radiotype.type_label)
    transport: Transport
    baud: int | None  # default speed; None for no serial line
    enter: tuple[Step, ...]  # written to switch to KISS; empty if already in KISS
    exit_kiss: bytes | None  # first thing the keep-alive's check sends
    # whether the TNC may be asked if it is there; if False only KISS frames are ever sent
    can_probe: bool
    detect_command_mode: bool
    note: str  # what is uncertain about the profile, for the manual
    readings: tuple[ReadingKind, ...] = ()
    text_lines: TextLines = ""
    # written once on an open when the first packet comes as text
    nudge: bytes = b""
    # frames whose path says APRS-IS (a LoRa iGate's bridge) are not heard on the air
    drop_internet: bool = False
    board_readings: bool = False
    receive_only: bool = False  # nothing at all is written to the line
    # an unnamed port is searched among serial/pattern; False waits (an open may restart a board)
    search: bool = True
    framing: Literal["kiss", "text"] = "kiss"

    def __post_init__(self) -> None:
        if self.can_probe and (not self.enter or self.exit_kiss is None):
            raise ValueError(f"{self.key}: a profile that can be probed has to say how to enter and leave KISS")
        if self.detect_command_mode and not self.enter:
            raise ValueError(f"{self.key}: command mode cannot be left without an entry")
        if self.transport in ("tcp", "dummy", "modem") and (self.enter or self.can_probe):
            raise ValueError(f"{self.key}: a {self.transport} profile sends nothing but KISS frames")
        if self.receive_only and (self.enter or self.can_probe or self.nudge or self.exit_kiss is not None):
            raise ValueError(f"{self.key}: a profile that only receives writes nothing to its line")
        if self.nudge and self.text_lines != "tnc2":
            raise ValueError(f"{self.key}: the nudge is written when packets come as text")
        if self.framing == "text" and (
            self.enter or self.exit_kiss is not None or self.can_probe or self.detect_command_mode
        ):
            raise ValueError(
                f"{self.key}: a profile that reads text writes nothing to its line: no entry, no exit, no probe, no command mode"
            )

    @property
    def board(self) -> bool:
        return bool(self.text_lines or self.board_readings or self.drop_internet)

    @property
    def writes_nothing(self) -> bool:
        return self.framing == "text" or self.receive_only

    @property
    def settle_sec(self) -> float:
        return self.enter[-1][1] if self.enter else 0.0


KISS_TCP = Profile(
    "kiss-tcp",
    "Direwolf",
    "tcp",
    None,
    (),
    None,
    False,
    False,
    "Direwolf listens on 8001, UZ7HO SoundModem and QtSoundModem on 8100 (the KISS server port of the program).",
)

KISS = Profile(
    "kiss",
    "KISS TNC",
    "serial",
    9600,
    (),
    None,
    False,
    False,
    "The NinoTNC is opened at 57600; the TH-D74 and TH-D75 have to be put in KISS at the radio (they cannot be asked).",
)

# Kenwood TH-D7, TNC-2 and clones: silent after RESTART until a packet is heard, so it is probed
KENWOOD_TNC2 = Profile(
    "kenwood-tnc2",
    "Kenwood TH-D7, TM-D700, TNC-2",
    "serial",
    9600,
    ((b"\rKISS ON\rRESTART\r", 3.0),),
    KISS_EXIT,
    True,
    True,
    "Also the TAPR TNC-2 and MFJ-1270B/1274/1278 clones; the TS-2000 is reported to work, not read in its manual.",
)

# Kenwood TM-D710 and TH-D72: the tmd710_tncsetup sequence (TN 2,0 is band A, 3-4 s to settle)
KENWOOD_D710 = Profile(
    "kenwood-d710",
    "Kenwood TM-D710 / TH-D72",
    "serial",
    9600,
    ((b"TC 1\r", 1.0), (b"TN 2,0\r", 3.0), (b"HBAUD 1200\r", 1.0), (b"KISS ON\r", 1.0), (b"RESTART\r", 1.0)),
    KISS_EXIT,
    True,
    True,
    "What TC 0 and TC 1 mean is not documented by Kenwood; the sequence is the one the tmd710_tncsetup project uses and is copied as it is.",
)

KANTRONICS = Profile(
    "kantronics",
    "Kantronics KPC-3+",
    "serial",
    9600,
    ((b"\rINTFACE KISS\rRESET\r", 3.0),),
    KISS_EXIT,
    True,
    True,
    "The host speed has been reported to change after RESET on some units.",
)

# Mercury carries 123 bytes in a frame and silently cuts a longer one: the daemon shortens first.
MERCURY = Profile(
    "mercury",
    "sound card",
    "modem",
    None,
    (),
    None,
    False,
    False,
    "Mercury 1.9.26 has to be installed; nobody has run APRS over it before NeoAPRS, so the frequencies are proposals until confirmed on the air.",
    readings=("snr",),
)

# A Mercury the operator runs himself: reached on its KISS port, listened to on its control port 200 above.
MERCURY_OWN = Profile(
    "mercury-own",
    "your own program",
    "modem",
    None,
    (),
    None,
    False,
    False,
    "NeoAPRS starts no modem: both ends of a contact must run Mercury on the same mode, DATAC3.",
    readings=("snr",),
)

DUMMY = Profile(
    "dummy",
    "Dummy packet radio",
    "dummy",
    None,
    (),
    None,
    False,
    False,
    "Nothing goes on the air and nothing is opened: the traffic is made up by the program, around the station's position.",
)

DUMMY_HF = Profile(
    "dummy-hf",
    "Dummy Mercury radio",
    "dummy",
    None,
    (),
    None,
    False,
    False,
    "Nothing goes on the air and nothing is keyed: the stations are made up, hundreds of kilometres away, and your own frames are heard from the speakers.",
    readings=("snr",),
)

DUMMY_LORA = Profile(
    "dummy-lora",
    "Dummy LoRa radio",
    "dummy",
    None,
    (),
    None,
    False,
    False,
    "Nothing goes on the air and nothing is opened: the stations are made up, round the station's position, as a LoRa APRS board would hear them.",
    readings=("snr", "rssi"),
)

# LoRa boards: their frequency and modem settings are never sent, nor text lines.
# C0 05 00 C0 is KISS "full duplex off", which no board acts on but switches the Tracker to KISS.
LORA_NUDGE = kiss.encode(b"\x00", command=5)
LORA_TCP = Profile(
    "lora-tcp",
    "tracker or iGate on Wi-Fi",
    "tcp",
    None,
    (),
    None,
    False,
    False,
    "The CA2RXU iGate's TNC server on port 8001, in KISS; its list of heard packets on port 80 says each packet's signal.",
    readings=("snr", "rssi"),
    text_lines="tnc2",
    nudge=LORA_NUDGE,
    drop_internet=True,
    board_readings=True,
    search=False,
)
LORA_SERIAL = Profile(
    "lora-serial",
    "tracker or iGate, USB or Bluetooth",
    "serial",
    115200,
    (),
    None,
    False,
    False,
    "A CA2RXU Tracker's TNC image over Bluetooth, the CA2RXU iGate's TNC on USB, DL9SAU's tracker, esp32_loraprs; whether an open restarts a board is not known.",
    readings=("snr", "rssi"),
    text_lines="tnc2",
    nudge=LORA_NUDGE,
    drop_internet=True,
    board_readings=True,
    search=False,
)
LORA_CONSOLE = Profile(
    "lora-console",
    "iGate on USB (RX only)",
    "serial",
    115200,
    (),
    None,
    False,
    False,
    "The CA2RXU iGate with its TNC off on USB writes a line for each packet it hears, with its signal; it takes nothing, so nothing is sent.",
    readings=("snr", "rssi"),
    text_lines="console",
    receive_only=True,
    search=False,
)

# Text monitor: nothing is written, not even a carriage return; typing into a TNC whose prompt was
# not seen can put the lines on the air (Converse Mode).
TNC_TEXT = Profile(
    "tnc-text",
    "Yaesu FTM, receive only",
    "serial",
    9600,
    (),
    None,
    False,
    False,
    "Receive only. What real devices print rests on their manuals and on ygate's one Yaesu sample: no capture of one has been read yet.",
    framing="text",
)

PROFILES: tuple[Profile, ...] = (KENWOOD_TNC2, KENWOOD_D710, KANTRONICS, KISS, KISS_TCP, TNC_TEXT, DUMMY)
HF_PROFILES: tuple[Profile, ...] = (MERCURY, MERCURY_OWN, DUMMY_HF)
# the types whose radio is a Mercury on the air (not the Dummy)
MERCURY_TYPES = frozenset({MERCURY.key, MERCURY_OWN.key})
BY_KEY = {p.key: p for p in PROFILES}
HF_BY_KEY = {p.key: p for p in HF_PROFILES}
LORA_PROFILES: tuple[Profile, ...] = (LORA_TCP, LORA_SERIAL, LORA_CONSOLE, DUMMY_LORA)
EVERY_BY_KEY = {p.key: p for p in (*PROFILES, *HF_PROFILES, *LORA_PROFILES)}
DEFAULT = KISS
HF_DEFAULT = MERCURY


def profile_of(key: str) -> Profile:
    try:
        return BY_KEY[key.strip()]
    except KeyError:
        raise CodedError(
            f"{key!r} is not a type of radio (the types are {', '.join(BY_KEY)})", "setting.not_profile", value=key
        ) from None


def hf_profile_of(key: str) -> Profile:
    try:
        return HF_BY_KEY[key.strip()]
    except KeyError:
        raise CodedError(
            f"{key!r} is not a type of a Mercury radio (the types are {', '.join(HF_BY_KEY)})",
            "setting.not_hf_profile",
            value=key,
        ) from None


def names_tcp(path: str) -> bool:
    return path.strip().lower().startswith(("socket://", "tcp://"))


LINE_SPEED = 9600


def bracketed(host: str) -> str:
    return f"[{host}]" if ":" in host and not host.startswith("[") else host


def tcp_url(host: str, port: int) -> str:
    return f"socket://{bracketed(host)}:{port}"


def tcp_host(path: str) -> str:
    """Return the host of a TCP port setting without IPv6 brackets, or "" if it is not TCP."""
    if not names_tcp(path):
        return ""
    rest = path.split("://", 1)[1].rsplit(":", 1)[0]
    return rest[1:-1] if rest.startswith("[") and rest.endswith("]") else rest
