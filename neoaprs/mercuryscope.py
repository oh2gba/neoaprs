"""What Mercury's UI interface says, and the scope the page draws from it, as pure values and functions: the `status` message (the transmit gain and the peak of the latest transmission), the binary spectrum frame, the two commands
NeoAPRS sends (the waterfall on or off, the transmit gain), and the meter that turns the stream of spectra into what the page shows, a few dozen bins over the passband and the level of the passband. No I/O: the link is
mercuryui.py, and the part of the modem that owns it mercuryscoping.py.

The spectrum (Mercury 1.9.21, `gui_interface/ui_communication.c`, `spectrum_publisher_thread`, and `modem_stats_get_rx_spectrum` in `modem/freedv/modem_stats.c`): a binary frame of the magic 0x4D435259, the number of bins and the sample rate
as two little-endian 16-bit numbers, and that many little-endian 32-bit floats; every 50 ms while the waterfall is on. The bins are the first half of a 1024-point FFT of the last 1024 samples of the audio through a Hann window,
512 bins from 0 Hz to half the sample rate (7.8 Hz each at 8 kHz), in dB, scaled by the modem's own full scale (`FDMDV_SCALE` 825, so that a tone of amplitude 1650 of 32768 reads 0 dB). While the radio transmits, the buffer
holds the audio Mercury plays (`tx_spectrum`), so the spectrum is of the transmission then. The level is worked back to the audio's own level from that scale: the power of a bin, 10^((dB + 112.5) / 10) over the window's 384,
is the variance the audio has in that bin, and a band's share of the whole variance is its bins' sum over the 512 (white noise of RMS s reads the same in every bin, 20 log s - 112.5 + 25.8 dB), checked against the simulated
channel's noise of known RMS in the real-Mercury test."""
import json
import math
import struct
from dataclasses import dataclass

SPECTRUM_MAGIC = 0x4D435259
SPECTRUM_HEADER = struct.Struct("<IHH")
SPECTRUM_MAX_BINS = 4096                 # Mercury sends 512; a frame that claims more than this is no frame of its
FULL_SCALE_DB = 20 * math.log10(512 * 825)       # Mercury's own: NSPEC * FDMDV_SCALE
WINDOW_POWER = 1024 * 0.375              # the sum of the squares of the Hann window over the 1024 points
SAMPLE_FULL_SCALE_DB = 20 * math.log10(32768)    # the audio is 16-bit: a full-scale sample is this many dB over one unit

SCOPE_LO_HZ = 300                        # the passband of the scope: what a receiver's SSB filter lets through (Mercury's own busy detector listens to the same 300 to 2700 Hz)
SCOPE_HI_HZ = 2700
SCOPE_BINS = 48                          # 50 Hz each
SIGNAL_LO_HZ = 1200                      # the frame's signal band above the dial: DATAC3 is centred on 1500 Hz and 562 Hz wide by Mercury's figure (docs/mercury.md)
SIGNAL_HI_HZ = 1800
SCOPE_EVERY_SEC = 0.2                    # the page is sent at most five pictures a second (Mercury makes twenty spectra a second; they are averaged in power over the 0.2 s)
SCOPE_RANGE_DB = 60                      # the most a bin is told over the floor
FLOOR_FALL = 0.3                         # the floor moves toward a lower reading by this part of the way at every picture, toward a higher one by FLOOR_RISE (ten seconds or so): a signal or a step in the noise is not taken for the floor
FLOOR_RISE = 0.02
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
    """The spectrum in a binary frame of the UI websocket, or None for one that is not a spectrum frame (the magic, the size and the sample rate are checked)."""
    if len(frame) < SPECTRUM_HEADER.size:
        return None
    magic, bins, rate = SPECTRUM_HEADER.unpack_from(frame)
    if magic != SPECTRUM_MAGIC or not 0 < bins <= SPECTRUM_MAX_BINS or rate <= 0 or len(frame) != SPECTRUM_HEADER.size + 4 * bins:
        return None
    return Spectrum(rate, struct.unpack_from(f"<{bins}f", frame, SPECTRUM_HEADER.size))


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


def band_db(spectrum: Spectrum, lo_hz: float, hi_hz: float) -> float:
    """The mean power per bin of the band, in dB (the bins' dB are powers: they are averaged as powers)."""
    lo, hi = _bin_of(lo_hz, spectrum), _bin_of(hi_hz, spectrum)
    power = sum(10 ** (spectrum.db[i] / 10) for i in range(lo, hi + 1)) / (hi - lo + 1)
    return 10 * math.log10(power + 1e-30)


def level_dbfs(spectrum: Spectrum, lo_hz: float = SCOPE_LO_HZ, hi_hz: float = SCOPE_HI_HZ) -> float:
    """The RMS level of the audio in the band in dB below a full-scale sample (a full-scale sine reads -3), from the variance each bin of the spectrum stands for (the module's note says how)."""
    lo, hi = _bin_of(lo_hz, spectrum), _bin_of(hi_hz, spectrum)
    variance = sum(10 ** ((spectrum.db[i] + FULL_SCALE_DB) / 10) / WINDOW_POWER for i in range(lo, hi + 1)) / len(spectrum.db)
    return 10 * math.log10(variance + 1e-30) - SAMPLE_FULL_SCALE_DB


@dataclass(frozen=True)
class ScopeFrame:
    """What the page draws once: the bins in whole dB over the floor (0 to SCOPE_RANGE_DB), from SCOPE_LO_HZ up, SCOPE_BINS of them, and the level of the passband in whole dBFS."""
    bins: tuple[int, ...]
    level: int


class ScopeMeter:
    """Spectra in, a picture every SCOPE_EVERY_SEC out: the power of every scope bin averaged over the spectra since the last picture, the floor under it kept slowly (the quarter-quietest bin, which a signal
    narrower than three quarters of the passband does not move), the level of the passband from the same spectra."""

    def __init__(self) -> None:
        self._power = [0.0] * SCOPE_BINS
        self._level = 0.0
        self._count = 0
        self.floor: float | None = None

    def feed(self, spectrum: Spectrum) -> None:
        """One spectrum of the stream."""
        edge = (SCOPE_HI_HZ - SCOPE_LO_HZ) / SCOPE_BINS
        for i in range(SCOPE_BINS):
            lo, hi = SCOPE_LO_HZ + i * edge, SCOPE_LO_HZ + (i + 1) * edge
            self._power[i] += 10 ** (band_db(spectrum, lo, hi - 1e-6) / 10)
        self._level += 10 ** (level_dbfs(spectrum) / 10)
        self._count += 1

    def take(self, update_floor: bool = True) -> ScopeFrame | None:
        """The picture of the spectra fed since the last one, or None when there were none. The floor follows the picture unless `update_floor` is false (the radio is transmitting: the spectrum is of our own signal)."""
        if self._count == 0:
            return None
        db = [10 * math.log10(p / self._count + 1e-30) for p in self._power]
        level = 10 * math.log10(self._level / self._count + 1e-30)
        self._power, self._level, self._count = [0.0] * SCOPE_BINS, 0.0, 0
        quiet = sorted(db)[SCOPE_BINS // 4]
        if self.floor is None:
            self.floor = quiet
        elif update_floor:
            self.floor += (FLOOR_FALL if quiet < self.floor else FLOOR_RISE) * (quiet - self.floor)
        floor = self.floor
        return ScopeFrame(tuple(max(0, min(SCOPE_RANGE_DB, round(v - floor))) for v in db), max(LEVEL_MIN_DBFS, min(LEVEL_MAX_DBFS, round(level))))

    def reset(self) -> None:
        self._power, self._level, self._count, self.floor = [0.0] * SCOPE_BINS, 0.0, 0, None


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
