"""Mercury's UI interface and the scope drawn from it: messages, spectrum frames, rows, history.

Pure values and functions, no I/O. The spectrum frame format is described in the developer notes.
"""

import json
import math
import struct
import sys
import time
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

from .mercury import modem_gain

SPECTRUM_MAGIC = 0x4D435259
SPECTRUM_HEADER = struct.Struct("<IHH")
SPECTRUM_MAX_BINS = 4096
FULL_SCALE_DB = 20 * math.log10(512 * 825)
WINDOW_POWER = 1024 * 0.375
SAMPLE_FULL_SCALE_DB = 20 * math.log10(32768)

# Passband of the scope, as in Mercury's busy detector.
SCOPE_LO_HZ = 300
SCOPE_HI_HZ = 2700
# DATAC3 is centred on 1500 Hz, 562 Hz wide.
SIGNAL_LO_HZ = 1200
SIGNAL_HI_HZ = 1800
ROW_SPECTRA = 2
ROW_KIND = 1
# kind, flags, level in dBFS; the bins follow
ROW_HEADER = struct.Struct("<BBb")
ROW_TX = 1
HISTORY_KIND = 2
HISTORY_HEADER = struct.Struct("<Bd")
# per row: flags, level, age in ms; the bins follow
HISTORY_ROW = struct.Struct("<BbI")
HISTORY_SEC = 600
HISTORY_ROWS = HISTORY_SEC * 10
# What a full history of a radio takes in memory at most (measured: 3.1 MB)
HISTORY_BYTES = 3_500_000
# A bin of a row is one byte: ROW_OFFSET_DB + b * ROW_STEP_DB dB, -110 to +17.5; values clip.
ROW_OFFSET_DB = -110.0
ROW_STEP_DB = 0.5
MODEM_BINS = 512
MODEM_RATE = 8000
ROW_FIRST_BIN = math.ceil(SCOPE_LO_HZ / (MODEM_RATE / 2 / MODEM_BINS))
ROW_BINS = int(SCOPE_HI_HZ / (MODEM_RATE / 2 / MODEM_BINS)) - ROW_FIRST_BIN + 1
LEVEL_MIN_DBFS = -90
LEVEL_MAX_DBFS = 0
# Good passband RMS level: over the sound card's noise with headroom for static crashes (chosen).
LEVEL_GOOD_DBFS = (-55, -25)
TX_GAIN_MIN_DB = -20
TX_GAIN_MAX_DB = 20
PEAK_CLIP_DBFS = 0.0


@dataclass(frozen=True)
class Spectrum:
    sample_rate: int
    db: tuple[float, ...]

    def hz_per_bin(self) -> float:
        return self.sample_rate / 2 / len(self.db)


def parse_spectrum(frame: bytes) -> Spectrum | None:
    """Return the spectrum in a binary UI frame, or None if it is not one.

    A NaN or +inf bin rejects the frame; -inf is silence and stays.
    """
    if len(frame) < SPECTRUM_HEADER.size:
        return None
    magic, bins, rate = SPECTRUM_HEADER.unpack_from(frame)
    if (
        magic != SPECTRUM_MAGIC
        or not 0 < bins <= SPECTRUM_MAX_BINS
        or rate <= 0
        or len(frame) != SPECTRUM_HEADER.size + 4 * bins
    ):
        return None
    db = struct.unpack_from(f"<{bins}f", frame, SPECTRUM_HEADER.size)
    return None if any(math.isnan(v) or v == math.inf for v in db) else Spectrum(rate, db)


def spectrum_frame(db: list[float], sample_rate: int = 8000) -> bytes:
    return SPECTRUM_HEADER.pack(SPECTRUM_MAGIC, len(db), sample_rate) + struct.pack(f"<{len(db)}f", *db)


@dataclass(frozen=True)
class UiStatus:
    tx_gain_db: float
    tx_peak_dbfs: float
    audio_ok: bool


def parse_status(text: str) -> UiStatus | None:
    """Return the status in a UI text message, or None for any other message."""
    try:
        message = json.loads(text)
    except (ValueError, RecursionError):
        return None
    if not isinstance(message, dict) or message.get("type") != "status":
        return None
    gain, peak, ok = message.get("tx_gain_db"), message.get("tx_peak_dbfs"), message.get("audio_ok")
    if not isinstance(gain, int | float) or not isinstance(peak, int | float) or not isinstance(ok, bool):
        return None
    try:
        status = UiStatus(float(gain), float(peak), ok)
    except OverflowError:
        return None
    return status if math.isfinite(status.tx_gain_db) and math.isfinite(status.tx_peak_dbfs) else None


def waterfall_command(on: bool) -> str:
    return json.dumps({"command": "set_waterfall", "value": "on" if on else "off"})


def tx_gain_command(db: float) -> str:
    return json.dumps({"command": "set_tx_gain", "value": f"{modem_gain(db):g}"})


def clamp_gain(db: float) -> int:
    return max(TX_GAIN_MIN_DB, min(TX_GAIN_MAX_DB, round(db)))


def _bin_of(hz: float, spectrum: Spectrum) -> int:
    return max(0, min(len(spectrum.db) - 1, int(hz / spectrum.hz_per_bin())))


def level_dbfs(spectrum: Spectrum, lo_hz: float = SCOPE_LO_HZ, hi_hz: float = SCOPE_HI_HZ) -> float:
    """Return the RMS level of the audio in the band in dBFS (a full-scale sine reads -3)."""
    lo, hi = _bin_of(lo_hz, spectrum), _bin_of(hi_hz, spectrum)
    variance = sum(10 ** ((spectrum.db[i] + FULL_SCALE_DB) / 10) / WINDOW_POWER for i in range(lo, hi + 1)) / len(
        spectrum.db
    )
    return 10 * math.log10(variance + 1e-30) - SAMPLE_FULL_SCALE_DB


@dataclass(frozen=True, slots=True)
class ScopeRow:
    bins: bytes
    level: int
    tx: bool


def byte_of_db(db: float) -> int:
    return max(0, min(255, round((db - ROW_OFFSET_DB) / ROW_STEP_DB)))


LEVEL_FIRST_BIN = int(SCOPE_LO_HZ / (MODEM_RATE / 2 / MODEM_BINS))
LEVEL_OF_POWER = 10 ** ((FULL_SCALE_DB - SAMPLE_FULL_SCALE_DB) / 10) / WINDOW_POWER / MODEM_BINS


class RowMeter:
    """Spectra in, a row out every ROW_SPECTRA: the mean power of each passband bin.

    A row is wholly reception or wholly transmission; a change of keying restarts the pair.
    """

    def __init__(self) -> None:
        self._power = [0.0] * ROW_BINS
        self._level = 0.0
        self._count = 0
        self._tx = False

    def feed(self, spectrum: Spectrum, tx: bool) -> ScopeRow | None:
        """Take one spectrum; return the row it completes, if any."""
        if len(spectrum.db) != MODEM_BINS or spectrum.sample_rate != MODEM_RATE:
            return None
        if tx != self._tx:
            self.reset()
            self._tx = tx
        powers = [10 ** (v / 10) for v in spectrum.db[LEVEL_FIRST_BIN : ROW_FIRST_BIN + ROW_BINS]]
        self._power = [total + power for total, power in zip(self._power, powers[ROW_FIRST_BIN - LEVEL_FIRST_BIN :])]
        self._level += sum(powers) * LEVEL_OF_POWER
        self._count += 1
        if self._count < ROW_SPECTRA:
            return None
        count = self._count
        bins = bytes(
            max(0, min(255, round((10 * math.log10(p / count + 1e-30) - ROW_OFFSET_DB) / ROW_STEP_DB)))
            for p in self._power
        )
        level = 10 * math.log10(self._level / count + 1e-30)
        self.reset()
        return ScopeRow(bins, max(LEVEL_MIN_DBFS, min(LEVEL_MAX_DBFS, round(level))), tx)

    def reset(self) -> None:
        self._power, self._level, self._count = [0.0] * ROW_BINS, 0.0, 0


def scope_clock() -> float:
    """Return the clock rows are timed by: monotonic and counting time asleep."""
    if sys.platform == "linux":
        return time.clock_gettime(time.CLOCK_BOOTTIME)
    else:
        return time.monotonic()


@dataclass(frozen=True, slots=True)
class KeptRow:
    seq: int
    at: float
    row: ScopeRow


class ScopeHistory:
    """The rows of the last HISTORY_SEC, oldest first, at most HISTORY_ROWS.

    Numbers keep counting across `clear`, so a page's newest row says which rows are newer.
    """

    def __init__(self, keep_sec: float = HISTORY_SEC, most: int = HISTORY_ROWS) -> None:
        self._keep = keep_sec
        self._rows: deque[KeptRow] = deque(maxlen=most)
        self.last = 0

    def add(self, row: ScopeRow, now: float) -> KeptRow:
        self.last += 1
        kept = KeptRow(self.last, now, row)
        self._rows.append(kept)
        while self._rows and now - self._rows[0].at > self._keep:
            self._rows.popleft()
        return kept

    def after(self, seq: int, now: float, within: float | None = None) -> list[KeptRow]:
        """Return the rows newer than number `seq` and of the last `within` seconds of the kept time, oldest first."""
        keep = self._keep if within is None else min(within, self._keep)
        newer: list[KeptRow] = []
        for kept in reversed(self._rows):
            if kept.seq <= seq or now - kept.at > keep:
                break
            newer.append(kept)
        return newer[::-1]

    def clear(self) -> bool:
        had = bool(self._rows)
        self._rows.clear()
        return had

    def __len__(self) -> int:
        return len(self._rows)


def history_frame(rows: Sequence[KeptRow], now: float, wall_ms: float) -> bytes:
    """Return the binary frame of the kept rows: HISTORY_HEADER with `wall_ms`, then each row.

    With no rows it is the header alone, which makes the page forget its rows.
    """
    return HISTORY_HEADER.pack(HISTORY_KIND, wall_ms) + b"".join(
        HISTORY_ROW.pack(ROW_TX if k.row.tx else 0, k.row.level, max(0, round((now - k.at) * 1000))) + k.row.bins
        for k in rows
    )


def parse_history(frame: bytes) -> list[tuple[ScopeRow, int]] | None:
    """Return the rows and ages in ms in a history frame, or None (for tests)."""
    size = HISTORY_ROW.size + ROW_BINS
    if len(frame) < HISTORY_HEADER.size or frame[0] != HISTORY_KIND or (len(frame) - HISTORY_HEADER.size) % size:
        return None
    rows = []
    for start in range(HISTORY_HEADER.size, len(frame), size):
        flags, level, age = HISTORY_ROW.unpack_from(frame, start)
        rows.append((ScopeRow(frame[start + HISTORY_ROW.size : start + size], level, bool(flags & ROW_TX)), age))
    return rows


def history_clock(frame: bytes) -> float:
    return float(HISTORY_HEADER.unpack_from(frame)[1])


def row_frame(row: ScopeRow) -> bytes:
    return ROW_HEADER.pack(ROW_KIND, ROW_TX if row.tx else 0, row.level) + row.bins


def parse_row(frame: bytes) -> ScopeRow | None:
    if len(frame) != ROW_HEADER.size + ROW_BINS:
        return None
    kind, flags, level = ROW_HEADER.unpack_from(frame)
    return ScopeRow(frame[ROW_HEADER.size :], level, bool(flags & ROW_TX)) if kind == ROW_KIND else None


BAND_HZ = 150.0


def bands_db(spectrum: Spectrum) -> list[float]:
    """Return the mean power in dB of each 150 Hz band, cut as Mercury's busy detector does."""
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
