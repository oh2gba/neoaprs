"""What NeoAPRS knows of Direwolf, WB2OSZ's sound-card modem, as pure values and functions: the one Direwolf it ships (the pins), the configuration the daemon writes for a radio and the command line it starts the
program with, the keying it proposes for an FM interface, the level of a packet heard on Direwolf's own scale, and what the program prints. No I/O: the program is started and watched by direwolfprogram.py and
direwolfmodem.py, and the Tnc reaches its KISS port as it reaches any KISS server over TCP.

Direwolf is AFSK 1200 on FM (MODEM 1200), keying the radio itself (a CM108 pin, RTS or DTR of a serial port, or nothing: VOX), with its own carrier sense and its defaults for TXDELAY, TXTAIL, SLOTTIME and
PERSIST. It is given no call (it digipeats and gates nothing: NeoAPRS's own digipeater and beacon go over KISS as for any TNC), so a change of the station's call restarts no radio. Every listener of the Direwolf
NeoAPRS builds binds 127.0.0.1 (packaging/direwolf/loopback.patch), it ends cleanly when its standard input closes (`-Q`, quit.patch), its transmit level is a percentage (`-G`, txlevel.patch), it says the receive level ten times a second (`-R`, rxlevel.patch)
and it takes a configuration path of any length (confpath.patch).
docs/direwolf.md says where each number comes from."""
import re
from collections.abc import Sequence
from dataclasses import dataclass

from .mercury import _RADIO_CARD, _RADIO_SERIAL_VID, Keying, SerialPort, SoundCard, choose_sound_card
from .tncprofile import Profile

# The one Direwolf NeoAPRS ships: every release carries this version, built from this source on every system it is offered on (scripts/build-direwolf: natively on Linux, cross-compiled with MinGW-w64 for
# Windows), so that what the suite ran against is what the operator has. A new Direwolf is a change of these constants (docs/MAINTAINING.md, "Moving the Direwolf pin").
VERSION = "1.8.1"
SOURCE_COMMIT = "a231971a652bfb574a4bae9a5d875fbce53d2267"           # the commit the tag 1.8.1 points at
SOURCE_URL = f"https://github.com/wb2osz/direwolf/archive/{SOURCE_COMMIT}.tar.gz"
SOURCE_SHA256 = "9d9a31d13d87571dee77c91fb95a7b9bfdcb39f3d796e87bbbcd20f09f676581"                                                  # the digest of the archive at SOURCE_URL; scripts/build-direwolf builds nothing while it is empty
BANNER = "Dire Wolf Release %d.%d.%d, November 2025"                # the banner's format string in the program (direwolf.c:310): the version check of a program that cannot be run here (Windows)

MODE = "AFSK1200"
FIRST_PORT = 8002                      # the first KISS port tried: 8001 is Direwolf's own default, where an operator's own Direwolf may listen
PORT_TRIES = 50                        # how many ports are tried from FIRST_PORT up (below Mercury's 8100)
CONF_FILE = "direwolf.conf"
PID_FILE = "direwolf.pid"
STATS_SEC = 2                          # `-a`: a line every two seconds with the sample rate, the audio errors and the receive level as it is now (the radio's row follows it), to the log at DEBUG
LEVEL_NOW_MS = 100                     # `-R`: the receive level of channel 0 every 100 ms of audio read, "RXLEVEL 0 = N" (rxlevel.patch), for the pages that show it (web/levelfeed.py); never in the log

# The level of a packet heard, on Direwolf's own scale (direwolf.c:1329-1349): about 50 for most stations, "too high" over 110, "too low" under 5, 199 with the input cranked all the way up. The good band is a choice
# round Direwolf's 50, not a measurement, as Mercury's good range is (docs/direwolf.md).
LEVEL_MAX = 200
LEVEL_LOW = 5
LEVEL_HIGH = 110
LEVEL_GOOD = (30, 70)

# The transmit level: Direwolf's amplitude as a percentage of full scale (`-G`, txlevel.patch; 100 is Direwolf's own constant), set in dB as the HF radio's gain is, 0 dB the most.
TX_GAIN_MIN_DB = -20
TX_GAIN_MAX_DB = 0

# Tune and the keying test are Direwolf's own calibration runs (`-x`, direwolf.c:1056-1110), which key the radio and send before any port is open, for up to 60 s: the daemon ends them by closing the program's input.
TUNE_SEC = 10.0                        # the alternating mark and space tones (`-x a`), long enough to read the deviation off a meter
KEY_TEST_SEC = 1.0                     # the PTT alone (`-x p`); the mark tone (`-x m`) for a radio on VOX, which silence does not key
TESTS = {"tune": "a", "key": "p"}

# Direwolf as the Tnc reaches it: a modem program the daemon starts, KISS over TCP on this computer, with the rules a Profile has unless told others (an FM radio's).
PROFILE = Profile("direwolf", "Sound card", "modem", None, (), None, False, False,
                  "Direwolf 1.8.1, which NeoAPRS carries, on the radio's sound card: AFSK 1200, keyed by a CM108 pin, RTS or DTR, or VOX.")


def gain_percent(gain_db: int) -> int:
    """The transmit level of a gain in dB as Direwolf's percentage (`-G`): 100·10^(dB/20), within 1 and 100."""
    return max(1, min(100, round(100 * 10 ** (gain_db / 20))))


def ptt_line(keying: Keying) -> str:
    """The configuration's PTT line for the keying: none for VOX, `PTT CM108`, `PTT /dev/ttyUSB0 RTS`, `PTT COM3 DTR`. ValueError for a device with a space or a character that is not printable (a line break
    would be a line of Direwolf's configuration of its own: the setting refuses one already, mercury.keying_of)."""
    if keying.kind == "vox":
        return ""
    if keying.kind == "cm108":
        return "PTT CM108\n"
    if any(c.isspace() for c in keying.device) or not keying.device.isprintable():
        raise ValueError(f"Direwolf cannot key by the device {keying.device!r}: it has a space or a character that is not printable")
    return f"PTT {keying.device} {keying.kind.upper()}\n"


def adevice(sound_card: str, numbers: tuple[int, int] | None = None) -> str:
    """The configuration's audio device: the WinMM numbers of the input and the output on Windows (winmm.py), else the sound card's id as ALSA takes it. Never the system's default device, which may be the
    computer's speakers or another radio's card: ValueError without a card."""
    if numbers is not None:
        return f"{numbers[0]} {numbers[1]}"
    if not sound_card:
        raise ValueError("Direwolf is given no sound card: the system's default device is never written")
    return sound_card


def conf_text(device: str, keying: Keying, kiss_port: int) -> str:
    """Direwolf's configuration as the daemon writes it at every start: the sound card, one channel of AFSK 1200, the keying, the KISS port (slot 0 cleared first: it holds 8001 until it is, and a new port takes
    the first empty slot), the AGW server and the announcement on the LAN off. The audio device comes before the PTT line, because `PTT CM108` looks up the HID of the output device set before it."""
    return ("# written by NeoAPRS at every start\n"
            f"ADEVICE {device}\n"
            "ACHANNELS 1\n"
            "CHANNEL 0\n"
            "MODEM 1200\n"
            f"{ptt_line(keying)}"
            "KISSPORT 0\n"
            f"KISSPORT {kiss_port}\n"
            "AGWPORT 0\n"
            "DNSSD 0\n")


def command(program: Sequence[str], conf_file: str, gain_db: int = 0, test: str = "", vox: bool = False) -> list[str]:
    """The command line that starts Direwolf for NeoAPRS: the program (its path; or an interpreter and a module that stands in for it), the configuration the daemon wrote, no colours, no description of each
    packet (NeoAPRS decodes), the audio statistics every STATS_SEC, the receive level every LEVEL_NOW_MS, the keying and the carrier said as they change (`-d o`), each frame the line hands it said (`-d n`: a test waits for those to go), the end
    at the end of its input (`-Q`) and the transmit level (`-G`). With `test`
    (`tune` or `key`) the calibration run of that test: the mark tone for the keying test of a radio on VOX."""
    argv = [*program, "-c", conf_file, "-t", "0"]
    if not test:
        argv += ["-q", "d", "-a", str(STATS_SEC), "-R", str(LEVEL_NOW_MS)]
    argv += ["-d", "on", "-Q", "-G", str(gain_percent(gain_db))]
    if test:
        argv += ["-x", "m" if test == "key" and vox else TESTS[test]]
    return argv


_AIOC = re.compile(r"all-in-one", re.IGNORECASE)             # the AIOC's USB product string is "All-In-One-Cable" (its firmware's usb_descriptors.h)


def own_card(cards: Sequence[SoundCard]) -> str:
    """The sound card the daemon chooses for Direwolf when the settings name none: the one that stands out as a radio's (`mercury.choose_sound_card`), else the system's default when it names itself as a
    radio's or an interface's (a computer whose one sound card is the radio's); "" for none, never the computer's own sound, which would put the beacons on its speakers."""
    return choose_sound_card(cards) or next((c.id for c in cards if c.default and c.playback and c.capture and _RADIO_CARD.search(c.name)), "")


def choose_keying(card_name: str, ports: Sequence[SerialPort], tied: Sequence[str] | None = None) -> Keying:
    """How an FM radio on a sound-card interface is likely keyed, the card first: the CM108 pin of an AIOC whatever serial ports there are (its own way: its serial port keys only on DTR with RTS low, which
    `dtr:` does not say); else RTS of the one USB serial port that is part of the card's interface (a Digirig's CP2102): of `tied`, the ports in the card's group on the USB (its own device, or the hub of the radio it is in), where that can be
    told (Linux: usbtie.py), else the one such port of the computer when the card names itself as an interface's or a radio's; else VOX. A port that is not the card's is never keyed: it may be a programming
    cable, or another radio's."""
    if _AIOC.search(card_name or ""):
        return Keying("cm108")
    usb = [p for p in ports if p.vid is not None and p.vid in _RADIO_SERIAL_VID and not p.device.lower().startswith(("bt://", "ble://"))]
    near = [p for p in usb if p.device in tied] if tied is not None else usb if _RADIO_CARD.search(card_name or "") else []
    return Keying("rts", near[0].device) if len(near) == 1 else Keying("vox")


# ---- what the program prints

_READY = re.compile(r"^Ready to accept KISS TCP client application \d+ on port (\d+)")
_PORT_TAKEN = re.compile(r"^Some other application is probably already using port (\d+)")
_LEVEL = re.compile(r" audio level = (\d+)\(|receive audio level CH0 (\d+)")
_LEVEL_NOW = re.compile(r"^RXLEVEL 0 = (\d+)$")
_PTT = re.compile(r"^PTT (\d+) = ([01])$")
_DCD = re.compile(r"^DCD (\d+) = ([01])$")
_DEVICE = re.compile(r"^ ([* ])  (\d+): (.*?)(?:   \(channels? [\d &]+\))?$")
_AUDIO_FAILED = ("Could not open audio device", "Pointless to continue without audio device")
_KEYING_FAILED = re.compile(r"^ERROR can't open device .* for channel \d+ PTT control"                 # a serial port (ptt.c:945-956)
                            r"|Could not determine USB Audio GPIO PTT device"                          # `PTT CM108` with no CM108 chip on the card: Direwolf would run on unkeyed (config.c:2185)
                            r"|^Could not open \S+ for write"                                           # the chip's HID cannot be opened at a key (Linux: /dev/hidrawN without the rights, cm108.c:1013; Windows: cm108.c:948)
                            r"|^Write to \S+ failed, n=")                                                # nor written to (cm108.c:1059)
_WRONG_DEVICE = ("doesn't match any of the", "Invalid input (receive) audio device", "Invalid output (transmit) audio device")
SEVERAL_CM108 = "There are multiple USB Audio Devices with GPIO capability."
_ERRORS = (*_AUDIO_FAILED, "Bind failed with error", "Some other application is probably already using port", "ERROR", *_WRONG_DEVICE, SEVERAL_CM108, "Could not determine USB Audio GPIO PTT device",
           "for write", "failed, n=")


_KISS_FROM_CLIENT = "<<< Data frame from KISS client application"                     # `-d n`: a frame the line handed it, then its bytes (kiss_frame.c:464, 938-972)
_KISS_DUMP = re.compile(r"^(?:<<<|>>>) .* KISS client application|^  [0-9a-f]{3}: ( [0-9a-f]{2}){1,16}")


def kiss_from_client(line: str) -> bool:
    """Whether the line says a frame came from the line on the KISS port (`-d n`), which Direwolf queues until the channel is clear."""
    return line.startswith(_KISS_FROM_CLIENT)


def kiss_dump(line: str) -> bool:
    """Whether the line is one of the frames `-d n` prints, each way, with its bytes: counted by the daemon, not logged (the packets are in the log already)."""
    return _KISS_DUMP.match(line) is not None


def ready_port(line: str) -> int | None:
    """The KISS port Direwolf says it listens on ("Ready to accept KISS TCP client application 0 on port 8002 ..."); None for any other line."""
    m = _READY.match(line)
    return int(m.group(1)) if m else None


def bind_failed(line: str) -> bool:
    """Whether the line says the KISS port is taken (Direwolf runs on without KISS then: kissnet.c:458-466, 567-574)."""
    return line.startswith("Bind failed with error") or _PORT_TAKEN.match(line) is not None


def audio_open_error(line: str) -> bool:
    """Whether the line says the sound card could not be opened (Direwolf ends 5 s later: direwolf.c:1005-1011)."""
    return line.startswith(_AUDIO_FAILED)


def keying_open_error(line: str) -> bool:
    """Whether the line says the radio cannot be keyed: a serial port that cannot be opened (Direwolf ends: ptt.c:945-956), or a CM108 pin it found no chip for or cannot write to (it runs on, and keys
    nothing: the daemon ends it)."""
    return _KEYING_FAILED.search(line) is not None


def wrong_device(line: str) -> bool:
    """Windows: whether the line says the device numbers named no device or a wrong one, after which Direwolf runs on the system's default device (audio_win.c:336-338, 386-390): the daemon ends it."""
    return any(words in line for words in _WRONG_DEVICE)


def several_cm108(line: str) -> bool:
    """Whether the line says there are several CM108-class chips and Direwolf keys the last (cm108.c:785-817): on Windows the daemon ends it, it could key another radio."""
    return line.strip() == SEVERAL_CM108


def level_of(line: str) -> int | None:
    """The receive level a line tells, on Direwolf's scale: the level as it is now, said every STATS_SEC ("ADEVICE0: Sample rate approx. 44.1 k, 0 errors, receive audio level CH0 43", audio_stats.c), or that of a
    packet just heard ("OH2XYZ audio level = 48(12/9)   [NONE]   ___|||___"); None for any other line."""
    m = _LEVEL.search(line)
    return int(m.group(1) or m.group(2)) if m else None


def level_now_of(line: str) -> int | None:
    """The receive level of channel 0 as it is now, which `-R` says every LEVEL_NOW_MS ("RXLEVEL 0 = 43", rxlevel.patch); None for any other line."""
    m = _LEVEL_NOW.match(line)
    return int(m.group(1)) if m else None


def ptt_of(line: str) -> bool | None:
    """Whether the line keys (`PTT 0 = 1`) or unkeys (`PTT 0 = 0`) the radio, which `-d o` prints at each change, VOX too; None for any other line."""
    m = _PTT.match(line.strip())
    return m.group(2) == "1" if m else None


def dcd_of(line: str) -> bool | None:
    """Whether the line says a carrier came (`DCD 0 = 1`) or went (`DCD 0 = 0`); None for any other line."""
    m = _DCD.match(line.strip())
    return m.group(2) == "1" if m else None


def is_error(line: str) -> bool:
    """Whether the line is one of the errors Direwolf prints, which the log says counted (Direwolf's lines carry no severity of their own)."""
    return any(words in line for words in _ERRORS)


@dataclass
class DeviceLists:
    """What Direwolf says of the WinMM devices it chose (Windows: audio_win.c:379-410, 456-490): the device starred in each list, by its number and its name."""
    section: str = ""
    selected: dict[str, tuple[int, str]] | None = None

    def feed(self, line: str) -> None:
        """One line of the program: a list's heading, or a device of the list under way."""
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
        """Whether a list said another device than the one meant is selected (both lists said: whether the input and the output are the ones meant)."""
        chosen = self.selected or {}
        return any(chosen[way][0] != number for way, number in zip(("input", "output"), meant, strict=True) if way in chosen)
