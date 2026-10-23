"""The TNC profiles: what to say to a kind of TNC to put it in KISS mode and take it out, whether it can be asked if it is there, and how it is reached. One record for each kind of device, chosen by the setting
`tnc/profile`; the `Tnc` (tnc.py) does what the record says and nothing else, so a device that needs nothing is sent nothing: not a carriage return, not a probe. No I/O.

The strings and their pauses are the ones the manufacturers and the projects named below publish. `enter` is a list of steps, each the
bytes to write and the seconds to wait after them; the wait after the last step is the settle time, in which what the TNC says is thrown away."""
from dataclasses import dataclass
from typing import Literal

from .coded import CodedError

KISS_EXIT = b"\xc0\xff\xc0"          # the KISS "return" command (FEND, 0xFF, FEND): the TNC leaves KISS mode

Step = tuple[bytes, float]
Transport = Literal["serial", "tcp"]


@dataclass(frozen=True)
class Profile:
    key: str                                   # the value of tnc/profile
    name: str                                  # what the page calls it
    transport: Transport                       # "tcp": the TNC is a program or a bridge reached by host and port; "serial": a serial port (which may itself be a socket:// URL)
    baud: int | None                           # the speed the serial line is opened at unless serial/baud says otherwise; None: not a serial line
    enter: tuple[Step, ...]                    # what is written to switch the TNC to KISS; empty: nothing is, the device is in KISS already
    exit_kiss: bytes | None                    # what takes the TNC out of KISS (the first thing the keep-alive's check sends); None: nothing
    can_probe: bool                            # whether the TNC may be asked if it is there: the keep-alive's check, a carriage return after silence and the silent state; False: nothing is ever sent but KISS frames
    detect_command_mode: bool                  # whether text from the TNC ("cmd:", heard packets as TNC2 lines) means command mode, which `enter` leaves
    note: str                                  # what is uncertain about the profile, for the manual

    def __post_init__(self) -> None:
        if self.can_probe and (not self.enter or self.exit_kiss is None):
            raise ValueError(f"{self.key}: a profile that can be probed has to say how to enter and leave KISS")
        if self.detect_command_mode and not self.enter:
            raise ValueError(f"{self.key}: command mode cannot be left without an entry")
        if self.transport == "tcp" and (self.enter or self.can_probe):
            raise ValueError(f"{self.key}: a TCP profile sends nothing but KISS frames")

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

PROFILES: tuple[Profile, ...] = (KENWOOD_TNC2, KENWOOD_D710, KANTRONICS, KISS, KISS_TCP)
BY_KEY = {p.key: p for p in PROFILES}
DEFAULT = KISS                              # a fresh install: no text is ever sent to a device that was not named


def profile_of(key: str) -> Profile:
    """The profile with this key; ValueError naming the keys there are."""
    try:
        return BY_KEY[key.strip()]
    except KeyError:
        raise CodedError(f"{key!r} is not a TNC profile (the profiles are {', '.join(BY_KEY)})", "setting.not_profile", value=key) from None


def names_tcp(path: str) -> bool:
    """Whether a port setting is a TCP address (`socket://host:port`, or `tcp://host:port`, which means the same) rather than a serial device."""
    return path.strip().lower().startswith(("socket://", "tcp://"))


def tcp_url(host: str, port: int) -> str:
    """The `socket://` address the serial layer opens for a TCP KISS server (an IPv6 address in brackets)."""
    return f"socket://{f'[{host}]' if ':' in host and not host.startswith('[') else host}:{port}"
