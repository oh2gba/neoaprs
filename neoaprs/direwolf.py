"""Direwolf, the AFSK 1200 and 300 sound-card modem: version pin, configuration, command line, output.

Pure values and functions, no I/O. Direwolf keys the radio itself and does not digipeat or gate.
The patched build (packaging/direwolf/) adds `-Q`, `-G` and `-R`; docs/direwolf.md has the sources.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from .mercury import _RADIO_CARD, Keying, SerialPort, SoundCard, choose_sound_card, radio_serial_ports
from .tncprofile import Profile

VERSION = "1.8.1"
SOURCE_COMMIT = "a231971a652bfb574a4bae9a5d875fbce53d2267"  # the commit of tag 1.8.1
SOURCE_URL = f"https://github.com/wb2osz/direwolf/archive/{SOURCE_COMMIT}.tar.gz"
SOURCE_SHA256 = "9d9a31d13d87571dee77c91fb95a7b9bfdcb39f3d796e87bbbcd20f09f676581"
BANNER = "Dire Wolf Release %d.%d.%d, November 2025"

MODE = "AFSK1200"
OWN_PORT = 8001  # Direwolf's default KISS port
OWN_AGW_PORT = 8000  # Direwolf's default AGW port
FIRST_PORT = OWN_PORT + 1
PORT_TRIES = 50  # ports tried from FIRST_PORT up, below Mercury's 8100
CONF_FILE = "direwolf.conf"
PID_FILE = "direwolf.pid"
STATS_SEC = 2  # `-a`
LEVEL_NOW_MS = 100  # `-R`: "RXLEVEL 0 = N"

# Flags after the last frame; on Windows the key drops by Direwolf's clock (audio_win.c).
TXTAIL_MS = 200
# Flags before the first frame when a rig program keys the radio (Direwolf's own is 300 ms): its command
# and the rig's relay come first (docs/direwolf.md)
RIG_TXDELAY_MS = 400
# the largest frame: 8 digipeaters, 256 bytes of information, the FCS, one stuffed bit in five
FRAME_BITS_MAX = (7 * 10 + 2 + 256 + 2) * 8 * 6 // 5
# a key-down through a rig program lasts at most its flags, frames and tail, and this
RIG_MARGIN_SEC = 1.0


def frame_sec(baud: int) -> float:
    """Return the time of the largest frame on the air at `baud`."""
    return FRAME_BITS_MAX / baud


def keyed_limit(baud: int, frames: int) -> float:
    """Return how long a key-down of `frames` frames may last when a rig program keys the radio."""
    return (RIG_TXDELAY_MS + TXTAIL_MS) / 1000 + frames * frame_sec(baud) + RIG_MARGIN_SEC


# Receive level (direwolf.c:1329-1349): about 50 typical, over 110 too high.
LEVEL_MAX = 200
LEVEL_LOW = 5
LEVEL_HIGH = 110
LEVEL_GOOD = (30, 70)

TX_GAIN_MIN_DB = -20
TX_GAIN_MAX_DB = 0

# Calibration runs (`-x`, direwolf.c:1056-1110) key the radio until the input is closed.
TUNE_SEC = 10.0
KEY_TEST_SEC = 1.0
TESTS = {"tune": "a", "key": "p"}

PROFILE = Profile(
    "direwolf",
    "sound card, 1200",
    "modem",
    None,
    (),
    None,
    False,
    False,
    "Direwolf 1.8.1, which NeoAPRS carries, on the radio's sound card: AFSK 1200, keyed by a CM108 pin, RTS or DTR, or VOX.",
)
PROFILE_300 = Profile(
    "direwolf-300",
    "sound card, 300",
    "modem",
    None,
    (),
    None,
    False,
    False,
    "The same Direwolf with its 300 baud modem for HF SSB (tones 1600 and 1800 Hz), seven decoders 30 Hz apart; keyed as the 1200 type.",
)
# the speed of the modem of each profile, and its MODEM line (docs/direwolf.md, "300 baud on HF")
BAUDS = {PROFILE.key: 1200, PROFILE_300.key: 300}
_MODEM_LINES = {1200: "MODEM 1200", 300: "MODEM 300 A- 7@30"}


def modem_baud(profile: str) -> int:
    """Return the modem's speed for a Sound card type's profile key (1200 for any other)."""
    return BAUDS.get(profile, 1200)


def mode_of(baud: int) -> str:
    """Return the mode the status line names ("AFSK1200", "AFSK300")."""
    return f"AFSK{baud}"


def gain_percent(gain_db: int) -> int:
    return max(1, min(100, round(100 * 10 ** (gain_db / 20))))


def ptt_line(keying: Keying) -> str:
    """Return the PTT line ("" for VOX and a rig program); raise ValueError for a device that could inject a line."""
    if keying.kind == "vox" or keying.rig:
        return ""
    if keying.kind == "cm108":
        return "PTT CM108\n"
    if any(c.isspace() for c in keying.device) or not keying.device.isprintable():
        raise ValueError(
            f"Direwolf cannot key by the device {keying.device!r}: it has a space or a character that is not printable"
        )
    return f"PTT {keying.device} {keying.kind.upper()}\n"


def adevice(sound_card: str, numbers: tuple[int, int] | None = None) -> str:
    """Return the ADEVICE value; raise ValueError without a card (the default could be speakers)."""
    if numbers is not None:
        return f"{numbers[0]} {numbers[1]}"
    if not sound_card:
        raise ValueError("Direwolf is given no sound card: the system's default device is never written")
    return sound_card


def conf_text(device: str, keying: Keying, kiss_port: int, baud: int = 1200) -> str:
    """Return the configuration. `KISSPORT 0` clears the default slot; ADEVICE precedes PTT."""
    return (
        "# written by NeoAPRS at every start\n"
        f"ADEVICE {device}\n"
        "ACHANNELS 1\n"
        "CHANNEL 0\n"
        f"{_MODEM_LINES[baud]}\n"
        f"TXTAIL {TXTAIL_MS // 10}\n"
        f"{f'TXDELAY {RIG_TXDELAY_MS // 10}\n' if keying.rig else ''}"
        f"{ptt_line(keying)}"
        "KISSPORT 0\n"
        f"KISSPORT {kiss_port}\n"
        "AGWPORT 0\n"
        "DNSSD 0\n"
    )


def command(program: Sequence[str], conf_file: str, gain_db: int = 0, test: str = "", vox: bool = False) -> list[str]:
    """Return the command line, or that of the calibration `test` ("tune", "key")."""
    argv = [*program, "-c", conf_file, "-t", "0"]
    if not test:
        argv += ["-q", "d", "-a", str(STATS_SEC), "-R", str(LEVEL_NOW_MS)]
    argv += ["-d", "on", "-Q", "-G", str(gain_percent(gain_db))]
    if test:
        argv += ["-x", "m" if test == "key" and vox else TESTS[test]]
    return argv


_AIOC = re.compile(r"all-in-one", re.IGNORECASE)  # the AIOC's USB product string


def own_card(cards: Sequence[SoundCard]) -> str:
    """Return the sound card to use when none is set, never the computer's own sound."""
    return choose_sound_card(cards) or next(
        (c.id for c in cards if c.default and c.playback and c.capture and _RADIO_CARD.search(c.name)), ""
    )


def choose_keying(card_name: str, ports: Sequence[SerialPort], tied: Sequence[str] | None = None) -> Keying:
    """Return the likely keying: CM108 for an AIOC, RTS of the card's one serial port, else VOX."""
    if _AIOC.search(card_name or ""):
        return Keying("cm108")
    usb = radio_serial_ports(ports)
    near = (
        [p for p in usb if p.device in tied] if tied is not None else usb if _RADIO_CARD.search(card_name or "") else []
    )
    return Keying("rts", near[0].device) if len(near) == 1 else Keying("vox")


_READY = re.compile(r"^Ready to accept KISS TCP client application \d+ on port (\d+)")
_PORT_TAKEN = re.compile(r"^Some other application is probably already using port (\d+)")
_LEVEL = re.compile(r" audio level = (\d+)\(|receive audio level CH0 (\d+)")
_LEVEL_NOW = re.compile(r"^RXLEVEL 0 = (\d+)$")
_PTT = re.compile(r"^PTT (\d+) = ([01])$")
_DCD = re.compile(r"^DCD (\d+) = ([01])$")
_DEVICE = re.compile(r"^ ([* ])  (\d+): (.*?)(?:   \(channels? [\d &]+\))?$")
_AUDIO_FAILED = ("Could not open audio device", "Pointless to continue without audio device")
# Serial port not openable (ptt.c:945-956), no CM108 chip (config.c:2185), HID not openable or
# writable (cm108.c:1013, 948, 1059).
_KEYING_FAILED = re.compile(
    r"^ERROR can't open device .* for channel \d+ PTT control"
    r"|Could not determine USB Audio GPIO PTT device"
    r"|^Could not open \S+ for write"
    r"|^Write to \S+ failed, n="
)
_WRONG_DEVICE = (
    "doesn't match any of the",
    "Invalid input (receive) audio device",
    "Invalid output (transmit) audio device",
)
SEVERAL_CM108 = "There are multiple USB Audio Devices with GPIO capability."
_ERRORS = (
    *_AUDIO_FAILED,
    "Bind failed with error",
    "Some other application is probably already using port",
    "ERROR",
    *_WRONG_DEVICE,
    SEVERAL_CM108,
    "Could not determine USB Audio GPIO PTT device",
    "for write",
    "failed, n=",
)


# `-d n` prints a frame from the client, then its bytes (kiss_frame.c:464, 938-972).
_KISS_FROM_CLIENT = "<<< Data frame from KISS client application"
_KISS_DUMP = re.compile(r"^(?:<<<|>>>) .* KISS client application|^  [0-9a-f]{3}: ( [0-9a-f]{2}){1,16}")


def kiss_from_client(line: str) -> bool:
    return line.startswith(_KISS_FROM_CLIENT)


def kiss_dump(line: str) -> bool:
    return _KISS_DUMP.match(line) is not None


def ready_port(line: str) -> int | None:
    m = _READY.match(line)
    return int(m.group(1)) if m else None


def bind_failed(line: str) -> bool:
    """Return whether the KISS port is taken (kissnet.c:458-574)."""
    return line.startswith("Bind failed with error") or _PORT_TAKEN.match(line) is not None


def audio_open_error(line: str) -> bool:
    return line.startswith(_AUDIO_FAILED)


def keying_open_error(line: str) -> bool:
    return _KEYING_FAILED.search(line) is not None


def wrong_device(line: str) -> bool:
    """Windows: return whether the numbers matched no device (audio_win.c:336-390)."""
    return any(words in line for words in _WRONG_DEVICE)


def several_cm108(line: str) -> bool:
    """Return whether several CM108 chips exist (cm108.c:785-817)."""
    return line.strip() == SEVERAL_CM108


def level_of(line: str) -> int | None:
    m = _LEVEL.search(line)
    return int(m.group(1) or m.group(2)) if m else None


def level_now_of(line: str) -> int | None:
    m = _LEVEL_NOW.match(line)
    return int(m.group(1)) if m else None


def ptt_of(line: str) -> bool | None:
    m = _PTT.match(line.strip())
    return m.group(2) == "1" if m else None


def dcd_of(line: str) -> bool | None:
    m = _DCD.match(line.strip())
    return m.group(2) == "1" if m else None


def is_error(line: str) -> bool:
    return any(words in line for words in _ERRORS)


@dataclass
class DeviceLists:
    """The starred device of each WinMM list (audio_win.c:379-490)."""

    section: str = ""
    selected: dict[str, tuple[int, str]] | None = None

    def feed(self, line: str) -> None:
        if line.startswith("Available audio input devices"):
            self.section = "input"
        elif line.startswith("Available audio output devices"):
            self.section = "output"
        elif self.section and (m := _DEVICE.match(line)) is not None:
            if m.group(1) == "*":
                self.selected = {**(self.selected or {}), self.section: (int(m.group(2)), m.group(3))}
        else:
            self.section = ""

    def wrong(self, meant: tuple[int, int]) -> bool:
        chosen = self.selected or {}
        return any(
            chosen[way][0] != number for way, number in zip(("input", "output"), meant, strict=True) if way in chosen
        )
