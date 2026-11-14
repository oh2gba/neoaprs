"""What Mercury's UI interface says, and the scope the page draws from it, as pure values and functions: the `status` message (the transmit gain and the peak of the latest transmission), the binary spectrum frame, the two commands
NeoAPRS sends (the waterfall on or off, the transmit gain), and the row meter and the binary frame of the waterfall that turn the stream of spectra into what the page shows (the passband at the modem's own bins, a byte of
dB on the modem's scale, two spectra to a row, and the level of the passband; the floor under it is the page's, lib/waterfallfloor.ts), and the rows of the last two minutes kept for a page that begins to look, with the frame
they are sent in (each row with its age). No I/O: the link is
mercuryui.py, and the part of the modem that owns it mercuryscoping.py.

The spectrum (Mercury 1.9.24, the same as 1.9.21's, `gui_interface/ui_communication.c`, `spectrum_publisher_thread`, and `modem_stats_get_rx_spectrum` in `modem/freedv/modem_stats.c`): a binary frame of the magic 0x4D435259, the number of bins and the sample rate
as two little-endian 16-bit numbers, and that many little-endian 32-bit floats; every 50 ms while the waterfall is on. The bins are the first half of a 1024-point FFT of the last 1024 samples of the audio through a Hann window,
512 bins from 0 Hz to half the sample rate (7.8 Hz each at 8 kHz), in dB, scaled by the modem's own full scale (`FDMDV_SCALE` 825, so that a tone of amplitude 1650 of 32768 reads 0 dB). While the radio transmits, the buffer
holds the audio Mercury plays (`tx_spectrum`), so the spectrum is of the transmission then. The level is worked back to the audio's own level from that scale: the power of a bin, 10^((dB + 112.5) / 10) over the window's 384,
is the variance the audio has in that bin, and a band's share of the whole variance is its bins' sum over the 512 (white noise of RMS s reads the same in every bin, 20 log s - 112.5 + 25.8 dB), checked against the simulated
channel's noise of known RMS in the real-Mercury test."""
import json
import math
import struct
import sys
import time
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

SPECTRUM_MAGIC = 0x4D435259
SPECTRUM_HEADER = struct.Struct("<IHH")
SPECTRUM_MAX_BINS = 4096                 # Mercury sends 512; a frame that claims more than this is no frame of its
FULL_SCALE_DB = 20 * math.log10(512 * 825)       # Mercury's own: NSPEC * FDMDV_SCALE
WINDOW_POWER = 1024 * 0.375              # the sum of the squares of the Hann window over the 1024 points
SAMPLE_FULL_SCALE_DB = 20 * math.log10(32768)    # the audio is 16-bit: a full-scale sample is this many dB over one unit

SCOPE_LO_HZ = 300                        # the passband of the scope: what a receiver's SSB filter lets through (Mercury's own busy detector listens to the same 300 to 2700 Hz)
SCOPE_HI_HZ = 2700
SIGNAL_LO_HZ = 1200                      # the frame's signal band above the dial: DATAC3 is centred on 1500 Hz and 562 Hz wide by Mercury's figure (docs/mercury.md)
SIGNAL_HI_HZ = 1800
ROW_SPECTRA = 2                          # a row of the waterfall is this many of the modem's spectra averaged in power: ten rows a second where the modem makes twenty spectra a second (it makes nearer seventeen on reception, so the rows come every 120 ms then)
ROW_KIND = 1                             # the first byte of a binary frame to the page says what the frame is: a row of the waterfall
ROW_HEADER = struct.Struct("<BBb")       # the kind, the flags (ROW_TX) and the level of the passband in whole dBFS; the bytes of the bins follow
ROW_TX = 1                               # the flag: the radio transmits, the row is of our own signal
HISTORY_KIND = 2                         # a binary frame of this kind is the rows kept, sent to a page when it begins to look: the kind and the daemon's clock (HISTORY_HEADER), then each row oldest first
HISTORY_HEADER = struct.Struct("<Bd")    # the kind, and the daemon's clock when the frame is made, milliseconds since 1970 (the page places the times the daemon writes, a packet's `heard_at`, on its own clock by it)
HISTORY_ROW = struct.Struct("<BbI")      # a kept row in it: the flags, the level, and its age in whole milliseconds at the moment the frame is made; the bytes of the bins follow
HISTORY_SEC = 120                        # the rows are kept this long: what the pictures keep (the monitor card's 400 lines are 80 s, two minutes are kept so that a box drawn again larger is whole)
HISTORY_ROWS = HISTORY_SEC * 10          # and at most this many: the modem's timer makes twenty spectra a second, ten rows
ROW_OFFSET_DB = -110.0                   # a bin of a row is one byte on the modem's own scale: byte b is ROW_OFFSET_DB + b * ROW_STEP_DB dB, from -110 to +17.5 (the noise of a channel reads -58 to -31 dB a bin, a frame -15 at its strongest, our own signal +8): what is lower is the lowest byte, what is higher the highest
ROW_STEP_DB = 0.5
MODEM_BINS = 512                         # Mercury's spectrum: 512 bins of 7.8125 Hz at 8 kHz; a row is made of spectra of this shape only
MODEM_RATE = 8000
ROW_FIRST_BIN = math.ceil(SCOPE_LO_HZ / (MODEM_RATE / 2 / MODEM_BINS))              # the first modem bin of the passband: 39, 304.7 Hz
ROW_BINS = int(SCOPE_HI_HZ / (MODEM_RATE / 2 / MODEM_BINS)) - ROW_FIRST_BIN + 1     # the bins of the passband: 307
LEVEL_MIN_DBFS = -90                     # the level of silence, and of anything quieter
LEVEL_MAX_DBFS = 0
LEVEL_GOOD_DBFS = (-55, -25)             # the passband's RMS level that is good: far enough over the sound card's own noise (-98 dBFS in 16 bits) and with headroom for a crash of static (docs/mercury.md): chosen, not measured
TX_GAIN_MIN_DB = -20                     # Mercury's own limits of `set_tx_gain` (ui_communication.c clamps to them)
TX_GAIN_MAX_DB = 20
PEAK_CLIP_DBFS = 0.0                     # a transmission whose peak is this or higher clips in the sound card


@dataclass(frozen=True)
class Spectrum:
    """One spectrum frame: the sample rate of the audio and the bins in dB."""
    sample_rate: int
    db: tuple[float, ...]

    def hz_per_bin(self) -> float:
        return self.sample_rate / 2 / len(self.db)


def parse_spectrum(frame: bytes) -> Spectrum | None:
    """The spectrum in a binary frame of the UI websocket, or None for one that is not a spectrum frame (the magic, the size and the sample rate are checked) and for one with a bin that is not a number or is infinitely high: no
    power can be made of it, and one such bin would make every row after it fail. A bin of minus infinity is silence and stays."""
    if len(frame) < SPECTRUM_HEADER.size:
        return None
    magic, bins, rate = SPECTRUM_HEADER.unpack_from(frame)
    if magic != SPECTRUM_MAGIC or not 0 < bins <= SPECTRUM_MAX_BINS or rate <= 0 or len(frame) != SPECTRUM_HEADER.size + 4 * bins:
        return None
    db = struct.unpack_from(f"<{bins}f", frame, SPECTRUM_HEADER.size)
    return None if any(math.isnan(v) or v == math.inf for v in db) else Spectrum(rate, db)


def spectrum_frame(db: list[float], sample_rate: int = 8000) -> bytes:
    """A spectrum frame as Mercury writes it (for the fake Mercury of the tests and the benches)."""
    return SPECTRUM_HEADER.pack(SPECTRUM_MAGIC, len(db), sample_rate) + struct.pack(f"<{len(db)}f", *db)


@dataclass(frozen=True)
class UiStatus:
    """The few things of Mercury's `status` message that NeoAPRS reads."""
    tx_gain_db: float
    tx_peak_dbfs: float
    audio_ok: bool


def parse_status(text: str) -> UiStatus | None:
    """The status in a text message of the UI websocket, or None for any other message (the device lists, the history) and for a status that lacks what is read."""
    try:
        message = json.loads(text)
    except ValueError:
        return None
    if not isinstance(message, dict) or message.get("type") != "status":
        return None
    gain, peak, ok = message.get("tx_gain_db"), message.get("tx_peak_dbfs"), message.get("audio_ok")
    if not isinstance(gain, int | float) or not isinstance(peak, int | float) or not isinstance(ok, bool):
        return None
    return UiStatus(float(gain), float(peak), ok)


def waterfall_command(on: bool) -> str:
    """The command that turns the spectrum feed on or off (`set_waterfall`: any value but "off" is on)."""
    return json.dumps({"command": "set_waterfall", "value": "on" if on else "off"})


def tx_gain_command(db: float) -> str:
    """The command that sets the transmit gain (`set_tx_gain`, in dB; Mercury keeps it between -20 and 20)."""
    return json.dumps({"command": "set_tx_gain", "value": f"{db:g}"})


def clamp_gain(db: float) -> int:
    """A transmit gain as a whole number of dB between Mercury's limits."""
    return max(TX_GAIN_MIN_DB, min(TX_GAIN_MAX_DB, round(db)))


def _bin_of(hz: float, spectrum: Spectrum) -> int:
    return max(0, min(len(spectrum.db) - 1, int(hz / spectrum.hz_per_bin())))


def level_dbfs(spectrum: Spectrum, lo_hz: float = SCOPE_LO_HZ, hi_hz: float = SCOPE_HI_HZ) -> float:
    """The RMS level of the audio in the band in dB below a full-scale sample (a full-scale sine reads -3), from the variance each bin of the spectrum stands for (the module's note says how)."""
    lo, hi = _bin_of(lo_hz, spectrum), _bin_of(hi_hz, spectrum)
    variance = sum(10 ** ((spectrum.db[i] + FULL_SCALE_DB) / 10) / WINDOW_POWER for i in range(lo, hi + 1)) / len(spectrum.db)
    return 10 * math.log10(variance + 1e-30) - SAMPLE_FULL_SCALE_DB


@dataclass(frozen=True)
class ScopeRow:
    """One row of the waterfall: the passband's ROW_BINS bins of the modem's spectra as bytes on the modem's own scale (ROW_OFFSET_DB, ROW_STEP_DB), the level of the passband in whole dBFS, and whether the radio transmits."""
    bins: bytes
    level: int
    tx: bool


def byte_of_db(db: float) -> int:
    """A bin's dB on the modem's scale as the byte that is sent."""
    return max(0, min(255, round((db - ROW_OFFSET_DB) / ROW_STEP_DB)))


LEVEL_FIRST_BIN = int(SCOPE_LO_HZ / (MODEM_RATE / 2 / MODEM_BINS))                 # the first bin `level_dbfs` reads of a spectrum of Mercury's: 38; its last is the passband's last
LEVEL_OF_POWER = 10 ** ((FULL_SCALE_DB - SAMPLE_FULL_SCALE_DB) / 10) / WINDOW_POWER / MODEM_BINS     # a sum of those bins' powers is this much of a full-scale sample's power: `level_dbfs` without the log


class RowMeter:
    """Spectra in, a row every ROW_SPECTRA of them out: the power of each bin of the passband averaged over the spectra of the row. It keeps no floor: what a bin is over the noise is found by the page, from the rows
    (ui/src/lib/waterfallfloor.ts), which is the one place of that rule. A row is wholly of reception or wholly of our transmission: when the radio keys or lets go between the two spectra of a pair, the pair starts again."""

    def __init__(self) -> None:
        self._power = [0.0] * ROW_BINS
        self._level = 0.0
        self._count = 0
        self._tx = False

    def feed(self, spectrum: Spectrum, tx: bool) -> ScopeRow | None:
        """One spectrum of the stream; the row it completes, if it does. A spectrum of another shape than Mercury's is ignored."""
        if len(spectrum.db) != MODEM_BINS or spectrum.sample_rate != MODEM_RATE:
            return None
        if tx != self._tx:
            self.reset()
            self._tx = tx
        powers = [10 ** (v / 10) for v in spectrum.db[LEVEL_FIRST_BIN:ROW_FIRST_BIN + ROW_BINS]]           # (each bin's power once: the level's band is the passband and the bin under its first)
        self._power = [total + power for total, power in zip(self._power, powers[ROW_FIRST_BIN - LEVEL_FIRST_BIN:])]
        self._level += sum(powers) * LEVEL_OF_POWER
        self._count += 1
        if self._count < ROW_SPECTRA:
            return None
        count = self._count
        bins = bytes(max(0, min(255, round((10 * math.log10(p / count + 1e-30) - ROW_OFFSET_DB) / ROW_STEP_DB))) for p in self._power)     # (byte_of_db, written out: it is the hot loop of the scope)
        level = 10 * math.log10(self._level / count + 1e-30)
        self.reset()
        return ScopeRow(bins, max(LEVEL_MIN_DBFS, min(LEVEL_MAX_DBFS, round(level))), tx)

    def reset(self) -> None:
        self._power, self._level, self._count = [0.0] * ROW_BINS, 0.0, 0


def scope_clock() -> float:
    """The clock the rows are kept by, in seconds: it only goes forward, and it counts the time the machine was asleep (Linux's boot clock; Windows' monotonic clock counts it already), so that a row of before a
    suspended hour is an hour old after it, as the page's clock says."""
    if sys.platform == "linux":
        return time.clock_gettime(time.CLOCK_BOOTTIME)
    else:
        return time.monotonic()


@dataclass(frozen=True)
class KeptRow:
    """A row as the modem part keeps it: its number (they count up for the life of the modem part, across every emptying), when it was made (`scope_clock`, seconds), and the row."""
    seq: int
    at: float
    row: ScopeRow


class ScopeHistory:
    """The rows of the last HISTORY_SEC, oldest first, at most HISTORY_ROWS of them: what a page that begins to look is sent first. Time that passed without rows stays in it as the distance between two rows' times.
    It is emptied when it would lie (`clear`): the numbers go on counting, so that a page's newest row says which rows are newer."""

    def __init__(self, keep_sec: float = HISTORY_SEC, most: int = HISTORY_ROWS) -> None:
        self._keep = keep_sec
        self._rows: deque[KeptRow] = deque(maxlen=most)
        self.last = 0                            # the number of the newest row made; 0 before the first

    def add(self, row: ScopeRow, now: float) -> KeptRow:
        self.last += 1
        kept = KeptRow(self.last, now, row)
        self._rows.append(kept)
        while self._rows and now - self._rows[0].at > self._keep:
            self._rows.popleft()
        return kept

    def after(self, seq: int, now: float) -> list[KeptRow]:
        """The rows newer than number `seq` and not older than the time kept, oldest first."""
        newer: list[KeptRow] = []
        for kept in reversed(self._rows):
            if kept.seq <= seq or now - kept.at > self._keep:
                break
            newer.append(kept)
        return newer[::-1]

    def clear(self) -> bool:
        """Forgets every row; whether there was one."""
        had = bool(self._rows)
        self._rows.clear()
        return had

    def __len__(self) -> int:
        return len(self._rows)


def history_frame(rows: Sequence[KeptRow], now: float, wall_ms: float) -> bytes:
    """The binary frame of the rows kept: HISTORY_HEADER with the daemon's clock `wall_ms`, then each row (HISTORY_ROW and the ROW_BINS bytes), its age counted to `now`. With no row it is the header alone: the page forgets
    what it holds."""
    return HISTORY_HEADER.pack(HISTORY_KIND, wall_ms) + b"".join(HISTORY_ROW.pack(ROW_TX if k.row.tx else 0, k.row.level, max(0, round((now - k.at) * 1000))) + k.row.bins for k in rows)


def parse_history(frame: bytes) -> list[tuple[ScopeRow, int]] | None:
    """The rows and their ages in milliseconds in a frame of the rows kept, or None for a frame that is none (for the tests; the page has its own, ui/src/lib/scoperow.ts)."""
    size = HISTORY_ROW.size + ROW_BINS
    if len(frame) < HISTORY_HEADER.size or frame[0] != HISTORY_KIND or (len(frame) - HISTORY_HEADER.size) % size:
        return None
    rows = []
    for start in range(HISTORY_HEADER.size, len(frame), size):
        flags, level, age = HISTORY_ROW.unpack_from(frame, start)
        rows.append((ScopeRow(frame[start + HISTORY_ROW.size:start + size], level, bool(flags & ROW_TX)), age))
    return rows


def history_clock(frame: bytes) -> float:
    """The daemon's clock (milliseconds since 1970) a frame of the rows kept was made at (for the tests)."""
    return float(HISTORY_HEADER.unpack_from(frame)[1])


def row_frame(row: ScopeRow) -> bytes:
    """The binary frame a page is sent for a row: the header (ROW_HEADER) and the ROW_BINS bytes."""
    return ROW_HEADER.pack(ROW_KIND, ROW_TX if row.tx else 0, row.level) + row.bins


def parse_row(frame: bytes) -> ScopeRow | None:
    """The row in a binary frame to the page, or None for a frame that is no row (for the tests; the page has its own, ui/src/lib/scoperow.ts)."""
    if len(frame) != ROW_HEADER.size + ROW_BINS:
        return None
    kind, flags, level = ROW_HEADER.unpack_from(frame)
    return ScopeRow(frame[ROW_HEADER.size:], level, bool(flags & ROW_TX)) if kind == ROW_KIND else None


BAND_HZ = 150.0                          # the bands of Mercury's own busy detector (modem/channel_busy.h BUSY_BAND_HZ), 300 to 2700 Hz: 17 of them at 8 kHz, the last of four bins


def bands_db(spectrum: Spectrum) -> list[float]:
    """The mean power of each 150 Hz band of the passband in dB, cut as Mercury's busy detector cuts them (`channel_busy_update`: the bins from 300 Hz up in bands of 19, the last one short), so that a detector of ours sees what Mercury's sees."""
    count = len(spectrum.db)
    hz_per_bin = (spectrum.sample_rate // 2) / count
    lo, hi = _clamp_bin(int(SCOPE_LO_HZ / hz_per_bin), count), _clamp_bin(int(SCOPE_HI_HZ / hz_per_bin), count)
    width = max(1, int(BAND_HZ / hz_per_bin + 0.5))
    bands: list[float] = []
    for first in range(lo, hi + 1, width):
        last = min(first + width - 1, hi)
        power = sum(10 ** (spectrum.db[i] / 10) for i in range(first, last + 1)) / (last - first + 1)
        bands.append(10 * math.log10(power + 1e-30))
    return bands


def _clamp_bin(bin_: int, count: int) -> int:
    return max(0, min(count - 1, bin_))
