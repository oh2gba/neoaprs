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

# The one Mercury NeoAPRS ships: every release carries this version, built from this source (scripts/build-mercury, Linux) or taken from this signed release file (packaging/windows/bundle_mercury.py), so that what
# the suite and the simulators ran against is what the operator has. A new Mercury is a change of these four lines, tried by the suite, never something that happens on the operator's computer.
VERSION = "1.9.21"
SOURCE_COMMIT = "edca701ba2e432aecd7d4e217ec8fa717ed23aa3"           # the commit the tag v1.9.21 points at
SOURCE_URL = f"https://github.com/Rhizomatica/mercury/archive/{SOURCE_COMMIT}.tar.gz"
SOURCE_SHA256 = "d991640df2672fa6df29ab973ebf3cd57b65ce2bb12417033e5aa2354cac0191"
WINDOWS_URL = f"https://github.com/Rhizomatica/mercury/releases/download/v{VERSION}/mercury-{VERSION}-w64-{SOURCE_COMMIT[:8]}.zip"
WINDOWS_SHA256 = "85163f2c2db65e03cbbeaac0b32c6a0cacf930616923c1a18d4d17730b74b806"
WINDOWS_SIZE = 16_065_263

# Every number here is justified in docs/mercury.md (where it comes from, and what was measured with scripts/mercury-measure on 2 November 2026 against Mercury 1.9.21 on the simulated channel).
MODE = "DATAC3"                        # the one mode, for every station (Mercury's `-m 1`, its default): the narrowest of its modes that carries a whole APRS packet (docs/MODES.md of Mercury: 9 carriers, 562 Hz)
MODE_INDEX = 1
FRAME_BYTES = 126                      # what a DATAC3 modem frame carries (Mercury's bcast_modes.h: 128 bytes with the CRC)
HEADER_BYTES = 3                       # Mercury's header and length in front of a KISS payload (modem/framer.h HEADER_SIZE 1, plus a two-byte length; its log says "Padding broadcast frame from 109 to 126 bytes" for a 106-byte payload)
MAX_PAYLOAD = FRAME_BYTES - HEADER_BYTES       # the longest AX.25 frame that goes whole: 123 bytes (a 140-byte frame came out of the far Mercury as 123, scripts/mercury-bench)
FRAME_SEC = 3.8                        # a frame on the air, PTT ON to PTT OFF, whatever the payload's length: measured 3.80 s over six frames (the audio is 3.41 s, 27280 samples; Mercury's modem.c adds 10 ms of TX delay, 100 ms of silence, 110 ms of preamble and postamble, 200 ms of tail and 100 ms more: 3.82 s by the code)
DELIVERY_SEC = 3.8                     # from the frame handed to Mercury to the packet at the far station: measured 3.68 s on average and 3.78 s at the slowest (0.14 s to PTT ON, and the far side decodes 0.26 s before PTT OFF: the postamble and the tail are still on the air)
BROADCAST_PORT = 8100                  # Mercury's defaults (its docs/TNC.md): the KISS port, and the control port 200 below it
CONTROL_PORT = 8300
CONTROL_OFFSET = CONTROL_PORT - BROADCAST_PORT         # the control port is this far from the broadcast port, where the daemon chooses the ports; of a Mercury something else runs it is an assumption of ours (Mercury's -b and -p are independent), true of one started with its defaults
BUSY_HOLD_MAX_SEC = 60.0               # a BUSY that lasts longer than this holds nothing any more: the detector's noise floor rises slowly (Mercury's channel_busy.c says a wideband signal reads BUSY for 60 to 95 s and a step in the noise for 100 to 145 s), and traffic must not be stranded by it; in the simulation a step of 30 dB held the radio 56 s

# Where the stations meet: dial frequencies, upper sideband, inside the IARU Region 1 digimode segments and in a gap between the known neighbours (the frequencies are proposals until confirmed on the air).
# Mercury is centred on 1500 Hz of audio, so the signal sits 1.2 to 1.8 kHz above the dial. 10.1476 MHz, the 300 baud HF APRS dial, is not one of these.
FREQUENCIES: tuple[tuple[int, str], ...] = ((30, "10.1462"), (40, "7.0541"), (20, "14.1070"))      # (band in metres, dial in MHz)

PTT_KINDS = ("vox", "cm108", "rts", "dtr")           # how the radio is keyed: by itself (VOX, or the radio's own data mode), a CM108 sound chip's GPIO pin (an AIOC, some dongles), or the RTS or DTR line of a serial port (a DigiRig, a home-made interface)
PTT_WITH_DEVICE = ("rts", "dtr")                     # the kinds that name a serial port after a colon: `rts:/dev/ttyUSB0`, `dtr:COM3`

# Tune and the keying test go through Mercury's own TUNE command on its control port (Mercury 1.9.21, mercury(1): `TUNE -dB` keys the transmitter through the keying it was started with and holds a steady tone at
# that level in dBFS, `TUNE OFF` unkeys; Mercury unkeys by itself after 60 s whatever the host does), so that the same keying and the same sound card as the frames use are what is tried, and nothing of ours touches
# the serial port or the sound card that Mercury holds. The tone is Mercury's: 1000 Hz, the frequency VARA's TUNE sends too (the control port takes no other), inside the 1200 to 1800 Hz the modes occupy, so an
# antenna tuner matches where the signal will be. Its level is Mercury's own default for TUNE, the example the manual gives, and is set at the sound card as the frames' level is, so the radio's ALC at the tone is
# what it will be on a frame. Ten seconds is long enough for an automatic tuner to find its match (most settle in a few seconds) and for the audio level to be read off a meter, and well under Mercury's deadline.
# The keying test is the same command for one second (what Mercury's own `-Q` keys for) at the quietest level TUNE takes, 60 dB under full scale: TUNE wants a level, "none" is not one of its choices, and a tone
# 45 dB under the tune tone moves no meter and is not heard on a monitor, so the operator sees the radio go to transmit and come back with nothing on the air to speak of.
TUNE_TONE_HZ = 1000
TUNE_LEVEL_DBFS = -15.0
TUNE_SEC = 10.0
KEY_TEST_LEVEL_DBFS = -60.0
KEY_TEST_SEC = 1.0
TUNE_OFF = "TUNE OFF"


def tune_command(level_dbfs: float) -> str:
    """The control port's line that keys the radio with the tone at this level (dBFS, -60 to 0): `TUNE -15`."""
    return f"TUNE {level_dbfs:g}"


# The Dummy HF radio (neoaprs/dummyhfscene.py) makes up what is heard and sends nothing on the air; what we send is played through the computer's own speakers as Mercury's real audio, so that the operator hears
# what the modem sounds like: the bundled Mercury is started keying nothing (`-P none`) on its `fifo` audio backend, two named pipes the daemon paces and plays (neoaprs/mercuryspeaker.py says how and why), and
# the frames the Tnc writes to the dummy line are handed to its broadcast port as they would be to the modem's. Where there are no named pipes (Windows) it runs on WASAPI's default recording and playback
# devices instead (`command(..., audio=())`): the recording device paces it and is heard by nobody, the playback device is the speakers.


def speaker_audio(capture_fifo: str, playback_fifo: str) -> list[str]:
    """Mercury's flags for the fifo backend: it hears `capture_fifo` and transmits into `playback_fifo`."""
    return ["-x", "fifo", "-i", capture_fifo, "-o", playback_fifo]


@dataclass(frozen=True)
class Keying:
    """How the radio is keyed, as the setting `mercury/keying` keeps it: the kind, and for a serial line the port."""
    kind: str
    device: str = ""

    @property
    def text(self) -> str:
        return f"{self.kind}:{self.device}" if self.device else self.kind


def keying_of(text: str) -> Keying:
    """The keying the setting names: `vox`, `cm108`, `rts:PORT` or `dtr:PORT`. CodedError for anything else (the code `setting.not_keying`); the empty setting, which means the daemon's own choice, is not one."""
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

def command(program: Sequence[str], config_file: str, sound_card: str, keying: Keying, broadcast_port: int = BROADCAST_PORT, control_port: int = CONTROL_PORT, audio: Sequence[str] = ()) -> list[str]:
    """The command line that starts Mercury for NeoAPRS: the program (its path; or an interpreter and a module that stands in for it), the configuration file the daemon wrote, the mode, the sound card for capture and
    playback (empty: the system's default device; `audio` names another backend instead, the Dummy HF radio's speaker's), the keying, and the two ports. The command line wins over the file, so what matters is
    said here."""
    argv = [*program, "-C", config_file, "-m", str(MODE_INDEX), "-b", str(broadcast_port), "-p", str(control_port), *audio]
    if sound_card and not audio:
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


@dataclass(frozen=True)
class SerialPort:
    """A serial port as the daemon lists it, the little the choice of a keying line needs."""
    device: str
    vid: int | None = None
    pid: int | None = None


_RADIO_CARD = re.compile(r"usb|codec|pnp|digirig|radio|c-media|cm108|texas|pcm290", re.IGNORECASE)      # what a radio's sound card calls itself: a USB codec (the IC-7300's PCM2903 "USB Audio CODEC", a DigiRig's or a dongle's C-Media "USB PnP Sound Device"); the computer's own card is "HDA Intel" or the like
_RADIO_SERIAL_VID = {0x10C4, 0x0403, 0x067B, 0x1A86}                 # Silicon Labs CP210x (a DigiRig, an IC-7300, an FT-710), FTDI, Prolific and WCH adapters: what a radio's or an interface's serial port is
_USB_CHIP_VID = {0x0D8C}                                              # C-Media: a CM108 or CM119 sound chip, whose GPIO keys the radio on a DigiRig Lite, an AIOC and the dongles


def choose_sound_card(cards: Sequence[SoundCard]) -> str:
    """The sound card the radio is likely on, as its id, or "" for the system's default device: the one card that is both playback and capture and names itself as a USB codec or a radio's, else the one card besides
    the system's default that is both, else nothing chosen. A computer with one radio has one such card; with none, Mercury's own default is the system's, which is right for a radio that is the only sound device."""
    both = [c for c in cards if c.playback and c.capture]
    radios = [c for c in both if _RADIO_CARD.search(c.name) and not c.default]
    if len(radios) == 1:
        return radios[0].id
    others = [c for c in both if not c.default]
    return others[0].id if len(others) == 1 and not radios else ""


def choose_keying(card_name: str, ports: Sequence[SerialPort]) -> Keying:
    """How the radio is likely keyed: RTS of the one USB serial port of a radio or an interface when the sound card is a USB one (a DigiRig keys on RTS of its CP2102; an IC-7300 or an FT-710 with its USB cable keys on
    RTS when the radio's USB SEND is RTS, which the manuals say to set for digital modes), else VOX, which every radio has and which a SignaLink does by itself. A CM108-class chip could be keyed on its GPIO, but not
    every dongle wires the pin, so the serial line wins where there is one."""
    usb = [p for p in ports if p.vid is not None and p.vid in _RADIO_SERIAL_VID and not p.device.lower().startswith(("bt://", "ble://"))]
    if _RADIO_CARD.search(card_name or "") and len(usb) == 1:
        return Keying("rts", usb[0].device)
    return Keying("vox")


# ---- what the program prints

_AUDIO_OPEN_ERROR = re.compile(r"\[ERR\] \[audio-(?:play|playback|cap|capture)\] .*audio->(?:open|init)\(\)")       # Mercury 1.9.21's audioio.c when the sound card cannot be opened: `[ERR] [audio-play] error in audio->open(): 1: snd_pcm_hw_params_set_access: (-22) Invalid argument`, `Error in audio->init(): ...`


def audio_open_error(line: str) -> bool:
    """Whether a line Mercury printed says its sound card could not be opened for playback or capture (the program runs on all the same, deaf and mute: the daemon ends it and says so)."""
    return _AUDIO_OPEN_ERROR.search(line) is not None


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
