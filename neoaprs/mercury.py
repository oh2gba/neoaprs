"""Mercury, the Rhizomatica HF modem: constants, keying, command line, configuration, output.
Pure values and functions, no I/O; mercuryhelper.py and mercurycontrol.py run the program.
The mode is fixed at DATAC3; a frame carries 126 bytes, 3 of them header (see `overflow`).
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from .coded import CodedError
from .frequencylist import SUGGESTED

# re-exported
from .mercurycards import (
    PAIR as PAIR,
    WASAPI_CAPTURE as WASAPI_CAPTURE,
    WASAPI_PLAYBACK as WASAPI_PLAYBACK,
    SoundCard as SoundCard,
    card_with as card_with,
    endpoints as endpoints,
    pair_directions as pair_directions,
    parse_sound_cards as parse_sound_cards,
    stable_alsa_id as stable_alsa_id,
)

# the pinned Mercury (scripts/build-mercury, docs/MAINTAINING.md)
VERSION = "1.9.25"
SOURCE_COMMIT = "33efac4e3089f64f493fde1232b8e96305d15185"  # v1.9.25
SOURCE_URL = f"https://github.com/Rhizomatica/mercury/archive/{SOURCE_COMMIT}.tar.gz"
SOURCE_SHA256 = "d2d88357bbbc9586ed11b25a7ddfb3362126b8dcd203a72e567d8093e734d266"

MODE = "DATAC3"
MODE_INDEX = 1
# Numbers below are justified in docs/mercury.md.
FRAME_BYTES = 126
HEADER_BYTES = 3
MAX_PAYLOAD = FRAME_BYTES - HEADER_BYTES  # longer is cut off
FRAME_SEC = 3.8  # PTT ON to PTT OFF, measured
DELIVERY_SEC = 3.8
HOST = "127.0.0.1"
BROADCAST_PORT = 8100  # Mercury's default KISS port
CONTROL_PORT = 8300
PORT_TRIES = 50  # pairs of ports tried from the defaults up
# UI port offset from the broadcast port
UI_OFFSET = 2000
OWN_UI_PORT = 10000
CONTROL_OFFSET = CONTROL_PORT - BROADCAST_PORT
# fallback only: while the spectrum is read, channelbusy.py decides
BUSY_THRESHOLD_DB = 14
# a longer BUSY holds nothing, so traffic is not stranded
BUSY_HOLD_MAX_SEC = 20.0
# VOX lead-in tone before the preamble
LEADIN_MS = 150
# Mercury's own level is 4 dB over the one the operator's gain is counted from (a frame peaking at -6 dBFS)
TX_GAIN_TRIM_DB = -4
MODEM_GAIN_LIMIT_DB = 20


def modem_gain(gain_db: float) -> float:
    """Return the gain Mercury is given for the operator's gain, within Mercury's limits."""
    return max(-MODEM_GAIN_LIMIT_DB, min(MODEM_GAIN_LIMIT_DB, gain_db + TX_GAIN_TRIM_DB))


# the suggested dials, in the IARU Region 1 digimode segments, are site/frequencies.json
DIAL_BAND = 40  # the band the page shows
DIAL_TEXT = dict(SUGGESTED)[f"{DIAL_BAND} m"]

PTT_KINDS = ("vox", "cm108", "rts", "dtr")
# these name a port after a colon: `rts:/dev/ttyUSB0`
PTT_WITH_DEVICE = ("rts", "dtr")

# Tune and the keying test use Mercury's TUNE command on the control port.
TUNE_TONE_HZ = 1000
TUNE_LEVEL_DBFS = -15.0
TUNE_SEC = 10.0
KEY_TEST_LEVEL_DBFS = -60.0
KEY_TEST_SEC = 1.0
TUNE_OFF = "TUNE OFF"


def tune_level(gain_db: float) -> float:
    return max(KEY_TEST_LEVEL_DBFS, min(0.0, TUNE_LEVEL_DBFS + gain_db))


def key_test_level(kind: str) -> float:
    return TUNE_LEVEL_DBFS if kind == "vox" else KEY_TEST_LEVEL_DBFS


def tune_command(level_dbfs: float) -> str:
    return f"TUNE {level_dbfs:g}"


# The Dummy HF radio plays through the speakers on Mercury's `fifo` backend.


def speaker_audio(capture_fifo: str, playback_fifo: str) -> list[str]:
    return ["-x", "fifo", "-i", capture_fifo, "-o", playback_fifo]


@dataclass(frozen=True)
class Keying:
    """How the radio is keyed (setting `mercury/keying`)."""

    kind: str
    device: str = ""

    @property
    def text(self) -> str:
        return f"{self.kind}:{self.device}" if self.device else self.kind


def keying_of(text: str) -> Keying:
    """Return the keying named by a setting: `vox`, `cm108`, `rts:PORT` or `dtr:PORT`.

    Raise CodedError (`setting.not_keying`) for anything else, including the empty setting.
    """
    value = text.strip()
    kind, _, device = value.partition(":")
    kind, device = kind.strip().lower(), device.strip()
    # a port is one word, so it cannot add a line to a configuration
    if (
        kind not in PTT_KINDS
        or (kind in PTT_WITH_DEVICE) != bool(device)
        or len(device) > 255
        or not device.isprintable()
        or any(c.isspace() for c in device)
    ):
        raise CodedError(
            f"{text!r} is not a way of keying the radio: vox, cm108, rts:PORT or dtr:PORT",
            "setting.not_keying",
            value=text,
        )
    return Keying(kind, device)


def overflow(raw: bytes, max_payload: int = MAX_PAYLOAD) -> int:
    """Return how many bytes the modem would cut off; 0 if it fits."""
    return max(0, len(raw) - max_payload)


def too_long(raw: bytes, max_payload: int = MAX_PAYLOAD) -> str | None:
    """Return why the frame is not sent, or None if it fits."""
    return None if len(raw) <= max_payload else f"{len(raw)} bytes, the radio carries {max_payload}"


def frame_words(direction: str, size: int, station: str, snr: float | None) -> str:
    if direction == "out":
        return f"Mercury frame sent from {station}: {size} bytes"
    return f"Mercury frame heard from {station}: {size} bytes" + ("" if snr is None else f", SNR {snr:.0f} dB")


def ports_from(broadcast_port: int) -> tuple[int, int]:
    return broadcast_port, broadcast_port + CONTROL_OFFSET


def command(
    program: Sequence[str],
    config_file: str,
    sound_card: str,
    keying: Keying,
    broadcast_port: int = BROADCAST_PORT,
    control_port: int = CONTROL_PORT,
    audio: Sequence[str] = (),
) -> list[str]:
    """Return the command line that starts Mercury; `audio` replaces the sound card."""
    argv = [
        *program,
        "-C",
        config_file,
        "-m",
        str(MODE_INDEX),
        "-b",
        str(broadcast_port),
        "-p",
        str(control_port),
        *audio,
    ]
    capture, playback = endpoints(sound_card) if not audio else ("", "")
    if capture:
        argv += ["-i", capture]
    if playback:
        argv += ["-o", playback]
    if keying.kind == "vox":
        argv += ["-P", "none"]
    elif keying.kind == "cm108":
        argv += ["-P", "cm108"]
    else:
        argv += ["-P", "serial", "-A", keying.device]
    return argv


def ini_text(keying: Keying, tx_gain_db: int = 0, ui_port: int = 0) -> str:
    """Return Mercury's configuration file, written at every start."""
    line = keying.kind if keying.kind in PTT_WITH_DEVICE else "rts"
    leadin = f"tx_leadin_ms = {LEADIN_MS}\n" if keying.kind == "vox" else ""
    ui = f"[main]\nui_enabled = true\nui_port = {ui_port}\nwaterfall_enabled = false\n" if ui_port else ""
    return (
        "; written by NeoAPRS at every start; the command line carries the rest\n"
        "[ptt]\n"
        f"line = {line}\n"
        f"{ui}"
        "[audio]\n"
        f"tx_gain_db = {modem_gain(tx_gain_db):g}\n"
        f"{leadin}"
        "[channel]\n"
        "busy_detect = true\n"
        f"busy_threshold_db = {BUSY_THRESHOLD_DB}\n"
        "[store]\n"
        "enabled = false\n"
        "[tnc]\n"
        "keepalive_s = 10\n"
    )


@dataclass(frozen=True)
class SerialPort:
    device: str
    vid: int | None = None
    pid: int | None = None


_RADIO_CARD = re.compile(r"usb|codec|pnp|digirig|radio|c-media|cm108|texas|pcm290|all-in-one", re.IGNORECASE)
# Silicon Labs, FTDI, Prolific, WCH
_RADIO_SERIAL_VID = {0x10C4, 0x0403, 0x067B, 0x1A86}
# C-Media CM108 and CM119
_USB_CHIP_VID = {0x0D8C}


_RADIO_CODEC = re.compile(r"codec|pcm290|texas|digirig|radio", re.IGNORECASE)


def choose_sound_card(cards: Sequence[SoundCard]) -> str:
    """Return the id of the likely radio sound card, or "" for the default device."""
    both = [c for c in cards if c.playback and c.capture]
    radios = [c for c in both if _RADIO_CARD.search(c.name) and not c.default]
    if len(radios) > 1:
        codecs = [c for c in radios if _RADIO_CODEC.search(c.name)]
        radios = codecs if len(codecs) == 1 else radios
    if len(radios) == 1:
        return radios[0].id
    others = [c for c in both if not c.default]
    return others[0].id if len(others) == 1 and not radios else ""


def card_reason(card: str, setting: str, cards: Sequence[SoundCard]) -> str:
    listed = ", ".join(f"{c.name!r} ({c.id})" for c in cards) or "none listed"
    if setting:
        return f"{setting!r}, from the settings"
    if card:
        name = next((c.name for c in cards if c.id == card), card)
        return f"{name!r} ({card}), chosen by NeoAPRS among the cards listed: {listed}"
    return f"the system's default device; no card stood out among those listed: {listed}"


def propose_sound_card(cards: Sequence[SoundCard]) -> str:
    """Return the sound card id the page proposes when the setting is empty."""
    return (
        choose_sound_card(cards)
        or next((c.id for c in cards if c.default), "")
        or next((c.id for c in cards if c.playback and c.capture), "")
        or (cards[0].id if cards else "")
    )


def radio_serial_ports(ports: Sequence[SerialPort]) -> list[SerialPort]:
    return [
        p
        for p in ports
        if p.vid is not None and p.vid in _RADIO_SERIAL_VID and not p.device.lower().startswith(("bt://", "ble://"))
    ]


def choose_keying(card_name: str, ports: Sequence[SerialPort]) -> Keying:
    """Return RTS of the only USB serial port if the card is a USB one, else VOX."""
    usb = radio_serial_ports(ports)
    if _RADIO_CARD.search(card_name or "") and len(usb) == 1:
        return Keying("rts", usb[0].device)
    return Keying("vox")


def propose_keying(cards: Sequence[SoundCard], card: str, ports: Sequence[SerialPort]) -> str:
    if not cards:
        return ""
    return choose_keying(next((c.name for c in cards if c.id == card), ""), ports).text


_AUDIO_OPEN_ERROR = re.compile(r"\[ERR\] \[audio-(?:play|playback|cap|capture)\] .*audio->(?:open|init)\(\)")


def audio_open_error(line: str) -> bool:
    """Return whether the line says the sound card could not be opened."""
    return _AUDIO_OPEN_ERROR.search(line) is not None


# Mercury's audioio.c writes this while the audio it records is not taken by its demodulator.
CAPTURE_FULL = "[WRN] [audio-cap] Buffer full in capture buffer!"


def capture_full(line: str) -> bool:
    return CAPTURE_FULL in line


_STAMP = re.compile(r"^(?:\d{4}-\d{2}-\d{2} )?\d{2}:\d{2}:\d{2}\.\d{3}Z? \[\+\d+\.\d{3}s\] ")


def unstamped(line: str) -> str:
    return _STAMP.sub("", line, count=1)


# a station message (Mercury 1.9.23+) comes under KISS command 0x03; it is no packet
STATION_MESSAGE_COMMAND = 0x03
STATION_MESSAGE_TYPE = 0x07


def station_message(command: int, payload: bytes) -> bool:
    return command == STATION_MESSAGE_COMMAND and bool(payload) and payload[0] >> 5 == STATION_MESSAGE_TYPE


@dataclass(frozen=True)
class ControlEvent:
    kind: str  # "ptt", "busy", "snr", "alive", "buffer", "other"
    on: bool = False
    value: float | None = None  # dB, or bytes
    text: str = ""


def parse_control_line(line: str) -> ControlEvent:
    """Parse a control-port line, such as `PTT ON` or `SN -2.5`; else `other`."""
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
    """Remove and return the complete lines in `buffer`; a partial line stays."""
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
        del buffer[: cut + 1]
        if line:
            lines.append(line)
