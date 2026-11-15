"""The TNC profiles: what to say to a kind of TNC to put it in KISS mode and take it out, whether it can be asked if it is there, and how it is reached. One record for each kind of device, chosen by the setting
`tnc/profile`; the `Tnc` (tnc.py) does what the record says and nothing else, so a device that needs nothing is sent nothing: not a carriage return, not a probe. No I/O.

The strings and their pauses are the ones the manufacturers and the projects named below publish. `enter` is a list of steps, each the
bytes to write and the seconds to wait after them; the wait after the last step is the settle time, in which what the TNC says is thrown away."""
from dataclasses import dataclass
from typing import Literal

from . import kiss
from .coded import CodedError
from .radiotype import Transport as Transport      # how a line is reached: a type of radio's (radiotype.py), named here as before
from .reading import ReadingKind

KISS_EXIT = b"\xc0\xff\xc0"          # the KISS "return" command (FEND, 0xFF, FEND): the TNC leaves KISS mode

Step = tuple[bytes, float]
TextLines = Literal["", "tnc2", "console"]


@dataclass(frozen=True)
class Profile:
    key: str                                   # the value of tnc/profile
    name: str                                  # what the page calls it
    transport: Transport                       # "tcp": the TNC is a program or a bridge reached by host and port; "serial": a serial port (which may itself be a socket:// URL); "dummy": no line at all, the made-up traffic of the Dummy radio; "modem": a modem program the daemon starts itself and reaches over TCP on this computer (Mercury)
    baud: int | None                           # the speed the serial line is opened at unless serial/baud says otherwise; None: not a serial line
    enter: tuple[Step, ...]                    # what is written to switch the TNC to KISS; empty: nothing is, the device is in KISS already
    exit_kiss: bytes | None                    # what takes the TNC out of KISS (the first thing the keep-alive's check sends); None: nothing
    can_probe: bool                            # whether the TNC may be asked if it is there: the keep-alive's check, a carriage return after silence and the silent state; False: nothing is ever sent but KISS frames
    detect_command_mode: bool                  # whether text from the TNC ("cmd:", heard packets as TNC2 lines) means command mode, which `enter` leaves
    note: str                                  # what is uncertain about the profile, for the manual
    readings: tuple[ReadingKind, ...] = ()     # the signal readings the radio gives of each frame it hears (reading.py): the Mercury modem the SNR, a LoRa board the SNR and the RSSI where its firmware says them; none for a KISS TNC
    text_lines: TextLines = ""                 # what lines of text from the line are (loraboard.py), never command mode: "tnc2" a LoRa board's packets in TNC2 text and its log, "console" the CA2RXU iGate's log; "": no such lines
    nudge: bytes = b""                         # written once on an open when the first packet comes as text: a KISS frame that turns a CA2RXU Tracker on classic Bluetooth to KISS, which the other boards ignore
    drop_internet: bool = False                # a frame whose path says APRS-IS (a LoRa iGate's bridge hands it on) is not heard on the air: it is passed over
    board_readings: bool = False               # the signal of a frame is looked for where a LoRa board says it (lorasignal.py, loralist.py)
    receive_only: bool = False                 # nothing at all is written to the line (a board's log, which takes nothing): no frame, no entry, no probe, no nudge
    search: bool = True                        # a port that is not named is looked for among the ports of serial/pattern; False: it waits for its port (a LoRa board, which an open may restart)
    framing: Literal["kiss", "text"] = "kiss"  # what the line carries: KISS frames both ways, or the text a TNC or a radio prints of what it hears (tnc2text.py), which is only read: nothing is ever written to such a line

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
        if self.framing == "text" and (self.enter or self.exit_kiss is not None or self.can_probe or self.detect_command_mode):
            raise ValueError(f"{self.key}: a profile that reads text writes nothing to its line: no entry, no exit, no probe, no command mode")

    @property
    def board(self) -> bool:
        """Whether the line is a LoRa board's, which its own reader takes (loraboard.py): its text lines, its KISS commands, its readings, the internet's frames."""
        return bool(self.text_lines or self.board_readings or self.drop_internet)

    @property
    def writes_nothing(self) -> bool:
        """Whether nothing at all is ever written to the line: a line that reads text, or a board's log that takes nothing (`receive_only`)."""
        return self.framing == "text" or self.receive_only

    @property
    def settle_sec(self) -> float:
        """How long what the TNC says is thrown away after the entry (the wait after its last step); 0 for a profile with no entry."""
        return self.enter[-1][1] if self.enter else 0.0


# Direwolf: KISS over TCP on port 8001 (Direwolf User Guide 1.3, section 9.4.2); UZ7HO SoundModem and QtSoundModem: KISS over TCP on 8100 (Digirig forum, wiki.oarc.uk/packet:qtsoundmodem).
# A program has no command mode and no keep-alive: the connection is all there is to know.
KISS_TCP = Profile("kiss-tcp", "KISS over TCP (Direwolf, soundmodem)", "tcp", None, (), None, False, False,
                   "Direwolf listens on 8001, UZ7HO SoundModem and QtSoundModem on 8100 (the KISS server port of the program).")

# Mobilinkd TNC3 and TNC4 (USB or Bluetooth serial; user guides Rev C and Rev B), NinoTNC (USB serial at 57600, wiki.oarc.uk/packet:ninotnc), TNC-Pi and TNC-X (no setup), Kenwood TH-D74 and TH-D75
# with KISS switched on at the radio ([F] then [LIST] on the D75; user manual B5A-4505, chapter 15: no command mode), any TNC that is in KISS when it is switched on.
KISS = Profile("kiss", "KISS TNC (Mobilinkd, NinoTNC, TNC-Pi, TH-D74/D75…)", "serial", 9600, (), None, False, False,
               "The NinoTNC is opened at 57600; the TH-D74 and TH-D75 have to be put in KISS at the radio (they cannot be asked).")

# Kenwood TH-D7, TM-D700 (APRS/packet manual: "KISS ON", then "RESTART"; leave with 0xC0 0xFF 0xC0), TS-2000 (forum reports), TAPR TNC-2 and its clones, MFJ-1270B/1274/1278, PacComm Tiny-2
# (TAPR TNC-2 1.1.6 notes: KISS ON, RESTART; G7JJF TNC set-up page). The TNC is silent after RESTART until it hears a packet, so it is asked: a carriage return answers "cmd:" in command mode.
KENWOOD_TNC2 = Profile("kenwood-tnc2", "Kenwood TH-D7 / TM-D700 / TS-2000, TNC-2", "serial", 9600, ((b"\rKISS ON\rRESTART\r", 3.0),), KISS_EXIT, True, True,
                       "Also the TAPR TNC-2 and MFJ-1270B/1274/1278 clones; the TS-2000 is reported to work, not read in its manual.")

# Kenwood TM-D710A/E/G/GA/GE and TH-D72A/E: the console sequence of the tmd710_tncsetup project (github.com/fmarier/tmd710_tncsetup, man page tmd710_tncsetup(1)): TC 1 (1 s), TN 2,0 (3 s: "D710 version
# 1.01,3179 needs 3-4 seconds to settle down"), HBAUD 1200 (1 s), KISS ON (1 s), RESTART (1 s). TN 2,1 would be band B.
KENWOOD_D710 = Profile("kenwood-d710", "Kenwood TM-D710 / TH-D72", "serial", 9600,
                       ((b"TC 1\r", 1.0), (b"TN 2,0\r", 3.0), (b"HBAUD 1200\r", 1.0), (b"KISS ON\r", 1.0), (b"RESTART\r", 1.0)), KISS_EXIT, True, True,
                       "What TC 0 and TC 1 mean is not documented by Kenwood; the sequence is the one the tmd710_tncsetup project uses and is copied as it is.")

# Kantronics KPC-3+, KPC-3, KAM (KPC-3+ user manual, KISS mode: INTFACE KISS, then RESET; G7JJF "^MINT KISS^MRESET^M"); leave with 0xC0 0xFF 0xC0 or a hard reset. Its prompt is "cmd:" too.
KANTRONICS = Profile("kantronics", "Kantronics KPC-3+", "serial", 9600, ((b"\rINTFACE KISS\rRESET\r", 3.0),), KISS_EXIT, True, True,
                     "The host speed has been reported to change after RESET on some units.")

# Rhizomatica's Mercury HF modem (neoaprs/mercury.py): a program the daemon starts and stops itself, with the radio's sound card and the way the radio is keyed as its two settings, reached on its broadcast port, which is
# KISS over TCP (Mercury 1.9.24, docs/TNC.md). Its frame carries 123 bytes of a packet and a longer one is cut off by Mercury without a word, so the daemon refuses or shortens it first. Only stations with the same
# modem on the same frequency hear each other; the mode is fixed in the program so that every NeoAPRS station is on it.
MERCURY = Profile("mercury", "Mercury HF modem (sound card, SSB radio)", "modem", None, (), None, False, False,
                  "Mercury 1.9.24 has to be installed; nobody has run APRS over it before NeoAPRS, so the frequencies are proposals until confirmed on the air.", readings=("snr",))

# The Dummy radio (neoaprs/dummyline.py): no radio, no port, no speed; the daemon makes the traffic itself and swallows what it sends. It is last in the list: it is for trying NeoAPRS out, and a person looking
# for their radio should find the real ones first.
DUMMY = Profile("dummy", "Dummy (no radio, made-up traffic)", "dummy", None, (), None, False, False,
                "Nothing goes on the air and nothing is opened: the traffic is made up by the program, around the station's position.")

# The Dummy HF radio (neoaprs/dummyhfscene.py): the HF radio's Dummy, with the rules of HF. A handful of distant fixed stations beacon every half hour to an hour, one answers a message; nothing goes on the air
# and nothing is keyed, and what we send is played through the computer's speakers as Mercury's real audio (mercurymodem.py), so that the HF side can be tried with no radio and no other station on the air.
DUMMY_HF = Profile("dummy-hf", "Dummy HF radio (no radio, made-up distant stations)", "dummy", None, (), None, False, False,
                   "Nothing goes on the air and nothing is keyed: the stations are made up, hundreds of kilometres away, and your own frames are heard from the speakers.", readings=("snr",))

# The Dummy LoRa radio (neoaprs/dummylorascene.py): a LoRa APRS board of made-up stations round the station; its type has the limits of LoRa (radiotypes/dummylora.py). The board speaks TNC2 text, as the
# boards in use do on the air and on their line, and each packet comes with the signal-to-noise ratio and the strength a board measures; nothing goes on the air and nothing is opened.
DUMMY_LORA = Profile("dummy-lora", "Dummy LoRa radio (no radio, made-up stations)", "dummy", None, (), None, False, False,
                     "Nothing goes on the air and nothing is opened: the stations are made up, round the station's position, as a LoRa APRS board would hear them.", readings=("snr", "rssi"))

# A LoRa APRS board (aprs-reference/lora-plan.md): the firmware takes the LoRa packet of text apart and gives the computer KISS (AX.25 frames it made from the text) or the text itself, and says the signal in
# its own way. The CA2RXU iGate on the network (its TNC server on port 8001, KISS or TNC2 lines; its list of heard packets says the signal), a board on USB or Bluetooth (the CA2RXU Tracker's `_TNC`
# images, the CA2RXU iGate's TNC on USB, DL9SAU's tracker, esp32_loraprs), and the CA2RXU iGate's log on USB, which says every packet with its signal and takes nothing. The frequency and the modem's
# settings are the board's own: no firmware takes them from a program safely, so none is sent. Text lines are read and never written (the firmwares end and take them differently); the nudge turns a
# Tracker on classic Bluetooth to KISS, and a board that keeps sending text receives and sends nothing (loraboard.TEXT_LINES). What the kind may carry and do is its types' (radiotypes/lora.py).
LORA_NUDGE = kiss.encode(b"\x00", command=5)       # C0 05 00 C0: KISS "full duplex off", which no board acts on; any KISS frame turns the Tracker's answers to KISS
LORA_TCP = Profile("lora-tcp", "LoRa APRS board on the network (KISS over TCP)", "tcp", None, (), None, False, False,
                   "The CA2RXU iGate's TNC server on port 8001, in KISS; its list of heard packets on port 80 says each packet's signal.",
                   readings=("snr", "rssi"), text_lines="tnc2", nudge=LORA_NUDGE, drop_internet=True, board_readings=True, search=False)
LORA_SERIAL = Profile("lora-serial", "LoRa APRS board on USB or Bluetooth (KISS)", "serial", 115200, (), None, False, False,
                      "A CA2RXU Tracker's TNC image over Bluetooth, the CA2RXU iGate's TNC on USB, DL9SAU's tracker, esp32_loraprs; whether an open restarts a board is not known.",
                      readings=("snr", "rssi"), text_lines="tnc2", nudge=LORA_NUDGE, drop_internet=True, board_readings=True, search=False)
LORA_CONSOLE = Profile("lora-console", "LoRa APRS iGate's log on USB (receive only)", "serial", 115200, (), None, False, False,
                       "The CA2RXU iGate with its TNC off on USB writes a line for each packet it hears, with its signal; it takes nothing, so nothing is sent.",
                       readings=("snr", "rssi"), text_lines="console", receive_only=True, search=False)

# A radio or a TNC that gives no KISS and prints what it hears as text: the Yaesu FTM-100, -400 and -500 on their data port with Output PACKET (FTM-400DR/DE manual, "Setting the COM port": 9600 bps by default;
# ygate's README ticks these three), a TAPR TNC-2, a Kantronics KPC-3 or an AEA PK-232 in its own monitor mode (aprs-reference/text-monitor-plan.md, section 2). Nothing is written to it, not even a carriage return:
# typing into a TNC whose prompt was not seen can put the lines on the air (Converse Mode), so the settings that matter are the ones a user types once (docs/RADIOS.md). The TNC-2 and the PK-232 send 7 bits with
# a parity bit at their factory setting; the reader finds that by itself (tnc2text.py).
TNC_TEXT = Profile("tnc-text", "RX only: Yaesu FTM, TNC text (no KISS)", "serial", 9600, (), None, False, False,
                   "Receive only. What real devices print rests on their manuals and on ygate's one Yaesu sample: no capture of one has been read yet.",
                   framing="text")      # (nothing of ours on it, no path, no digipeater, no beacon: its type's, radiotypes/tnctext.py)

PROFILES: tuple[Profile, ...] = (KENWOOD_TNC2, KENWOOD_D710, KANTRONICS, KISS, KISS_TCP, TNC_TEXT, DUMMY)       # the FM radio's types (tnc/profile); the HF radio's are HF_PROFILES (hf/profile)
HF_PROFILES: tuple[Profile, ...] = (MERCURY, DUMMY_HF)                                                 # the HF radio's types: the Mercury modem, and its Dummy last, as the FM radio's is
BY_KEY = {p.key: p for p in PROFILES}
HF_BY_KEY = {p.key: p for p in HF_PROFILES}
LORA_PROFILES: tuple[Profile, ...] = (LORA_TCP, LORA_SERIAL, LORA_CONSOLE, DUMMY_LORA)                  # the types of a LoRa radio
EVERY_BY_KEY = {p.key: p for p in (*PROFILES, *HF_PROFILES, *LORA_PROFILES)}                           # every profile a radio's type may name (RadioType.profile)
DEFAULT = KISS                              # a fresh install: no text is ever sent to a device that was not named
HF_DEFAULT = MERCURY


def profile_of(key: str) -> Profile:
    """The profile with this key; ValueError naming the keys there are."""
    try:
        return BY_KEY[key.strip()]
    except KeyError:
        raise CodedError(f"{key!r} is not a TNC profile (the profiles are {', '.join(BY_KEY)})", "setting.not_profile", value=key) from None


def hf_profile_of(key: str) -> Profile:
    """The HF radio's profile with this key (hf/profile): the Mercury modem or the Dummy HF radio."""
    try:
        return HF_BY_KEY[key.strip()]
    except KeyError:
        raise CodedError(f"{key!r} is not a type of the HF radio (the types are {', '.join(HF_BY_KEY)})", "setting.not_hf_profile", value=key) from None


def names_tcp(path: str) -> bool:
    """Whether a port setting is a TCP address (`socket://host:port`, or `tcp://host:port`, which means the same) rather than a serial device."""
    return path.strip().lower().startswith(("socket://", "tcp://"))


def tcp_url(host: str, port: int) -> str:
    """The `socket://` address the serial layer opens for a TCP KISS server (an IPv6 address in brackets)."""
    return f"socket://{f'[{host}]' if ':' in host and not host.startswith('[') else host}:{port}"
