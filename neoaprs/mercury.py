"""What NeoAPRS knows of Rhizomatica's Mercury HF modem, as pure values and functions: the one mode every station is on and what its frame carries, the frequencies the stations meet on, the keying of the radio as the
setting keeps it, the command line the daemon starts the program with and the configuration it writes for it, and what the program prints (its sound cards, the lines of its control port). No I/O: the program itself is
started and watched by mercuryhelper.py and mercurycontrol.py, and the Tnc reaches its broadcast port as it reaches any KISS server over TCP.

Mercury's broadcast port is KISS over TCP: unconnected datagrams, one modem frame each, no ack, heard by every station that runs the same mode on the same frequency (Mercury 1.9.21, `docs/TNC.md`). The mode
is fixed in the program and is not a setting, because a station on another mode hears nothing and nothing on the air says which mode a station is on: DATAC3, the narrowest of Mercury's modes that carries a whole
APRS packet. A frame is always its full size on the air, 3.9 s with the preamble, and carries 126 bytes, of which Mercury takes 3 for a header and a length; a KISS payload longer than the 123 that are left is
cut off by Mercury without a word to the client, so the daemon refuses or shortens such a packet before it goes (`overflow`). Nothing listens before it transmits (there is no carrier sense on the broadcast
plane), so two stations that key at the same moment lose both frames: Mercury's channel-busy detector is switched on in the configuration the daemon writes, and its `BUSY ON` holds our frames (mercurymodem.py)."""
import re
from collections.abc import Sequence
from dataclasses import dataclass

from .coded import CodedError

MODE = "DATAC3"                        # the one mode, for every station (Mercury's `-m 1`)
MODE_INDEX = 1
FRAME_BYTES = 126                      # what a DATAC3 modem frame carries
HEADER_BYTES = 3                       # Mercury's header and length in front of a KISS payload
MAX_PAYLOAD = FRAME_BYTES - HEADER_BYTES       # the longest AX.25 frame that goes whole: 123 bytes
FRAME_SEC = 3.9                        # a frame on the air, preamble included, whatever the payload's length
DELIVERY_SEC = 4.5                     # from the frame handed to Mercury to the packet at the far station: the frame, the decode and the 100 ms polls of its threads
BROADCAST_PORT = 8100                  # Mercury's defaults: the KISS port, and the control port 200 below it
CONTROL_PORT = 8300
CONTROL_OFFSET = CONTROL_PORT - BROADCAST_PORT         # the control port is this far from the broadcast port, where the daemon chooses the ports
BEACON_FLOOR_SEC = 300                 # a moving station beacons no oftener than this over HF (SmartBeaconing's fast rate and turn time are raised to it): on HF the custom is 10 to 30 minutes between reports
BUSY_HOLD_MAX_SEC = 60.0               # a BUSY that lasts longer than this holds nothing any more: the detector reads a step in the noise as a signal for a minute or two, and traffic must not be stranded by it

# Where the stations meet: dial frequencies, upper sideband, inside the IARU Region 1 digimode segments and in a gap between the known neighbours (the frequencies are proposals until confirmed on the air).
# Mercury is centred on 1500 Hz of audio, so the signal sits 1.2 to 1.8 kHz above the dial. 10.1476 MHz, the 300 baud HF APRS dial, is not one of these.
FREQUENCIES: tuple[tuple[int, str], ...] = ((30, "10.1462"), (40, "7.0541"), (20, "14.1070"))      # (band in metres, dial in MHz)

PTT_KINDS = ("vox", "cm108", "rts", "dtr")           # how the radio is keyed: by itself (VOX, or the radio's own data mode), a CM108 sound chip's GPIO pin (an AIOC, some dongles), or the RTS or DTR line of a serial port (a DigiRig, a home-made interface)
PTT_WITH_DEVICE = ("rts", "dtr")                     # the kinds that name a serial port after a colon: `rts:/dev/ttyUSB0`, `dtr:COM3`


@dataclass(frozen=True)
class Keying:
    """How the radio is keyed, as the setting `mercury/keying` keeps it: the kind, and for a serial line the port."""
    kind: str
    device: str = ""

    @property
    def text(self) -> str:
        return f"{self.kind}:{self.device}" if self.device else self.kind


def keying_of(text: str) -> Keying:
    """The keying the setting names: `vox`, `cm108`, `rts:PORT` or `dtr:PORT`. CodedError for anything else (the code `setting.not_keying`)."""
    value = text.strip()
    kind, _, device = value.partition(":")
    kind, device = kind.strip().lower(), device.strip()
    if kind not in PTT_KINDS or (kind in PTT_WITH_DEVICE) != bool(device):
        raise CodedError(f"{text!r} is not a way of keying the radio: vox, cm108, rts:PORT or dtr:PORT", "setting.not_keying", value=text)
    return Keying(kind, device)


def overflow(raw: bytes, max_payload: int = MAX_PAYLOAD) -> int:
    """How many bytes of this AX.25 frame the modem would cut off: 0 when it goes whole."""
    return max(0, len(raw) - max_payload)


def too_long(raw: bytes, max_payload: int = MAX_PAYLOAD) -> str | None:
    """Why the frame is not sent, as a clause, or None when it fits: "131 bytes, the radio carries 123"."""
    return None if len(raw) <= max_payload else f"{len(raw)} bytes, the radio carries {max_payload}"


def ports_from(broadcast_port: int) -> tuple[int, int]:
    """The broadcast port and the control port that goes with it."""
    return broadcast_port, broadcast_port + CONTROL_OFFSET


# ---- the program

def command(program: Sequence[str], config_file: str, sound_card: str, keying: Keying, broadcast_port: int = BROADCAST_PORT, control_port: int = CONTROL_PORT) -> list[str]:
    """The command line that starts Mercury for NeoAPRS: the program (its path; or an interpreter and a module that stands in for it), the configuration file the daemon wrote, the mode, the sound card for capture and
    playback (empty: the system's default device), the keying, and the two ports. The command line wins over the file, so what matters is said here."""
    argv = [*program, "-C", config_file, "-m", str(MODE_INDEX), "-b", str(broadcast_port), "-p", str(control_port)]
    if sound_card:
        argv += ["-i", sound_card, "-o", sound_card]
    if keying.kind == "vox":
        argv += ["-P", "none"]
    elif keying.kind == "cm108":
        argv += ["-P", "cm108"]
    else:
        argv += ["-P", "serial", "-A", keying.device]
    return argv


def ini_text(keying: Keying) -> str:
    """Mercury's configuration file as the daemon writes it: the channel-busy detector on (its `BUSY ON` / `BUSY OFF` on the control port is the one carrier sense this plane has), the serial line that keys the radio
    (`line` has no command-line flag), no message store (Mercury keeps a chat history by default; NeoAPRS has its own), and a quick heartbeat on the control port."""
    line = keying.kind if keying.kind in PTT_WITH_DEVICE else "rts"
    return ("; written by NeoAPRS at every start; the command line carries the rest\n"
            "[ptt]\n"
            f"line = {line}\n"
            "[channel]\n"
            "busy_detect = true\n"
            "[store]\n"
            "enabled = false\n"
            "[tnc]\n"
            "keepalive_s = 10\n")


@dataclass(frozen=True)
class SoundCard:
    """A sound card as `mercury -z` lists it: the id to give Mercury and the name the system gives it."""
    id: str
    name: str
    playback: bool = False
    capture: bool = False
    default: bool = False


_DEVICE = re.compile(r"^device(?: #\d+)?: (?:name: '(?P<name>.*?)'\s+id: '(?P<id>.*?)'|(?P<name2>.*?)\s+id=(?P<id2>\S+))(?P<default>\s+\(system (?:default|route)\))?\s*$")


def parse_sound_cards(text: str) -> list[SoundCard]:
    """The sound cards of `mercury -z` (Mercury 1.9.21: "playback devices:" and "capture devices:" each followed by `device: name: 'USB Audio CODEC'  id: 'plughw:1,0'  (system default)` lines, or `device #1: Default (system route)
    id=default` where the backend lists none). A card that is in both lists is one card, which is what a radio's sound card is."""
    cards: dict[str, SoundCard] = {}
    section = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.endswith("devices:"):
            section = stripped.split()[0]
            continue
        m = _DEVICE.match(stripped)
        if m is None or not section:
            continue
        ident = m.group("id") or m.group("id2") or ""
        name = (m.group("name") or m.group("name2") or ident).strip()
        before = cards.get(ident, SoundCard(ident, name))
        default = m.group("default") is not None or "(system route)" in name or "(system default)" in name
        cards[ident] = SoundCard(ident, before.name or name, before.playback or section == "playback", before.capture or section == "capture", before.default or default)
    return list(cards.values())


# ---- the control port (CR-terminated lines, as VARA's)

@dataclass(frozen=True)
class ControlEvent:
    """One line Mercury wrote on its control port that the daemon acts on."""
    kind: str                          # "ptt", "busy", "snr", "alive", "buffer", "other"
    on: bool = False                   # for ptt and busy
    value: float | None = None         # for snr (dB) and buffer (bytes)
    text: str = ""                     # the line as it came, for the log


def parse_control_line(line: str) -> ControlEvent:
    """`PTT ON`, `PTT OFF`, `BUSY ON`, `BUSY OFF`, `SN -2.5`, `IAMALIVE`, `BUFFER 126`; anything else is `other` with its text."""
    text = line.strip()
    words = text.split()
    if len(words) == 2 and words[0] in ("PTT", "BUSY") and words[1] in ("ON", "OFF"):
        return ControlEvent(words[0].lower(), on=words[1] == "ON", text=text)
    if len(words) == 2 and words[0] in ("SN", "BUFFER"):
        try:
            return ControlEvent("snr" if words[0] == "SN" else "buffer", value=float(words[1]), text=text)
        except ValueError:
            return ControlEvent("other", text=text)
    if text == "IAMALIVE":
        return ControlEvent("alive", text=text)
    return ControlEvent("other", text=text)


def split_control_lines(buffer: bytearray) -> list[str]:
    """The whole lines in the bytes that came from the control port (CR-terminated; a LF after the CR, or alone, is taken too), taken out of the buffer; a partial line stays in it."""
    lines: list[str] = []
    while True:
        cut = -1
        for i, byte in enumerate(buffer):
            if byte in (0x0D, 0x0A):
                cut = i
                break
        if cut < 0:
            return lines
        line = bytes(buffer[:cut]).decode("ascii", "replace").strip()
        del buffer[:cut + 1]
        if line:
            lines.append(line)
