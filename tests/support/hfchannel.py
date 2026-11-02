"""An HF channel for real Mercury instances on one computer, in pure Python: N stations, each with the two named pipes of Mercury's `-x fifo` audio backend (`-i RX_FIFO -o TX_FIFO`: what the station hears is written to its RX
pipe, what it transmits is read from its TX pipe), and one thread that is the air between them at a sound card's pace, 8000 samples a second in blocks of 20 ms. The audio is raw s32le mono with the 16-bit sample in the top
half of each 32-bit word (`pcm_to_s32le`, `s32le_to_pcm`).

    channel = Channel(snr_db=20)
    a = channel.add("A", rx_a, tx_a)                   # the pipes exist (os.mkfifo) before the Mercury that opens them is started; the channel may start before or after it
    b = channel.add("B", rx_b, tx_b)
    channel.set_link("A", "B", gain_db=-12, delay=40)  # a weaker, later path between the two (both ways unless symmetric=False); a gain of -inf is no path at all (a hidden station)
    channel.start()                                    # a daemon thread; stop() joins it and closes the pipes
    ... mercury -x fifo -i RX -o TX -p PORT -b BPORT -m 1 -C INI ...
    channel.report()                                   # per station: blocks sent / heard, keyed, overlapped, dropped, starved; channel: blocks, collisions

What it does with a block: every station's TX pipe is read without ever blocking (Mercury writes nothing while it does not transmit, so no data is silence); a station with 160 samples (or a frame's tail, padded after two blocks
without more) is **keyed** in this block; each receiver gets the sum over the keyed others of the link's gain times their samples (delayed, and through the link's shaper if it has one), plus white Gaussian noise, clipped to
int16. A keyed station hears only noise (a radio with its PTT down does not receive). Two keyed in one block are a **collision**, counted for the channel and, as `overlapped_blocks`, for each of them. Every receiver gets noise in
every block, even when nobody transmits: Mercury's busy detector takes its floor from what it hears, and on digital zero it read BUSY for a minute (scripts/mercury-bench), so a block is never all zero (unless `snr_db` is
infinite, for exact-value tests, which is not for Mercury).

`Channel.process_block()` does one block without pacing: the tests of this module step it by hand with the pipes filled in advance, and a given seed with the same bytes in gives the same bytes out; with the thread the bytes
depend on when Mercury wrote them."""
import math
import os
import random
import sys
import threading
import time
from array import array
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

NONBLOCK: int = getattr(os, "O_NONBLOCK", 0)                # (POSIX; the Windows type check knows no such name: the benches on named pipes run on Linux)
RATE = 8000                                                 # samples a second: Mercury's sound card rate
SAMPLE_BYTES = 4                                            # s32le
FULL_SCALE = 32768                                          # int16
# The level that SNR is counted against: the RMS of a DATAC3 frame as Mercury 1.9.21 plays it on its fifo backend, measured with `scripts/mercury-measure frame` (2 November 2026: RMS 7276 of 32768, -13.1 dBFS, peak 15739,
# -6.4 dBFS, a crest factor of 6.7 dB, the same for every payload since the frame is always its full size). A transmission at gain 0 dB has this RMS, so the SNR of the channel is codec2's: the signal's own power against the
# noise in 3 kHz, which is how the delivered-frames table of Mercury's docs/MODES.md counts it.
REFERENCE_RMS = 7276.0
SNR_BANDWIDTH = 3000.0                                      # Hz: the noise that counts is the noise in a voice channel, SNR in 3 kHz as the HF modes are specified; white noise at 8000 samples a second spreads over 4 kHz
TAIL_BLOCKS = 2                                             # blocks that a partial block waits for the rest of it before it is padded with zeros and played: the end of a frame is not a multiple of a block
READ_SIZE = 1 << 17
MAX_READS = 16                                              # reads of one pipe in one block (a pipe holds 64 KB, so the second read finds it empty)
SWAP = sys.byteorder == "big"


def pcm_to_s32le(samples: array[int]) -> bytes:
    """int16 samples as Mercury's fifo backend writes and reads them: each in the top half of a little-endian 32-bit word."""
    words = array("i", [s << 16 for s in samples])
    if SWAP:
        words.byteswap()
    return words.tobytes()


def s32le_to_pcm(data: bytes) -> array[int]:
    """The int16 samples of s32le bytes (a length that is not a multiple of 4 loses its last bytes)."""
    words = array("i")
    words.frombytes(data[:len(data) - len(data) % SAMPLE_BYTES])
    if SWAP:
        words.byteswap()
    return array("h", [w >> 16 for w in words])


Shaper = Callable[[array[int]], array[int]]


@dataclass
class Link:
    """What a transmission goes through on its way from one station to another (one direction): a gain in dB (`-inf`: no path), a delay in samples, and an optional shaper called with each block, delayed and before the gain, for
    a fading filter (it keeps its own state between blocks and returns as many samples as it was given)."""
    gain_db: float = 0.0
    delay: int = 0
    shaper: Shaper | None = None
    factor: float = field(init=False, default=1.0)

    def __post_init__(self) -> None:
        self.factor = math.pow(10, self.gain_db / 20)               # (-inf gives 0.0: no path)


FLAT = Link()


# ---- fading: the Watterson HF channel of one link

# The test channels of CCIR 520-2 (the mid-latitude ones of ITU-R F.1487): two paths of equal power, each multiplied by a complex Gaussian process with a Gaussian Doppler spectrum, the second path delayed. Each is
# (the delay of the second path in ms, the Doppler spread in Hz: twice the spectrum's standard deviation, as F.1487 defines it). Mercury's own simulator (common/watterson.c in its source, the presets ccir-good, ccir-moderate,
# ccir-poor and ccir-flutter) has the same four with the same numbers, and codec2's `ch`, the simulator behind the delivered-frames table of Mercury's docs/MODES.md, calls the poor one "MPP" (multipath poor, 1 Hz and
# 2 ms) and the moderate one "MPM". "poor" is the channel to show a mode's limits on: a fade of 10 dB or more about once in two seconds.
PRESETS: dict[str, tuple[float, float]] = {"good": (0.5, 0.1), "moderate": (1.0, 0.5), "poor": (2.0, 1.0), "flutter": (0.5, 10.0)}
HILBERT_TAPS = 47                  # a Hamming-windowed Hilbert transformer of this many taps turns the real signal into its analytic one: flat within 0.1 dB from 500 to 3500 Hz, which holds the modes (DATAC3 sits at 1219 to 1781 Hz), and 23 multiplications a sample; codec2 and Mercury use 257 taps, which pure Python cannot afford a block at a time
TAP_RATE_FACTOR = 64               # the tap process is drawn at this many times the Doppler spread and interpolated linearly in between (Mercury's gaussian_interp_ratio: the process has no energy above three standard deviations, 1.5 times the spread)
FIR_FLOOR = 1e-4                   # the Gaussian impulse response of the tap filter is cut where it has fallen to this (Mercury's gaussian_tap_setup)


def hilbert_taps(count: int = HILBERT_TAPS) -> list[tuple[int, float]]:
    """The non-zero taps of the Hilbert transformer as (m, h[m]) about its centre: h[m] = 2 / (pi m) for odd m, under a Hamming window (an odd `count`)."""
    half = count // 2
    taps = []
    for m in range(-half, half + 1):
        if m % 2:
            window = 0.54 + 0.46 * math.cos(math.pi * m / half)
            taps.append((m, window * 2 / (math.pi * m)))
    return taps


class _Tap:
    """One path's gain g(t): unit-variance complex white noise at a low rate through a Gaussian FIR (the impulse response exp(-4 pi^2 sigma^2 t^2), so that the power spectrum is Gaussian with the standard deviation sigma),
    scaled to E|g|^2 = 1 and interpolated linearly up to the sample rate, exactly as Mercury's watterson.c does it; a spread of 0 is a steady path (g = 1)."""

    def __init__(self, doppler_hz: float, rate: int, rng: random.Random) -> None:
        self._rng = rng
        self.ratio = 1
        self.fir: list[float] = []
        self._history: list[complex] = []
        self._index = 0
        self._phase = 0
        self.previous = self.following = 1 + 0j
        if doppler_hz <= 0:
            return
        sigma = doppler_hz / 2
        self.ratio = max(1, int(rate / (TAP_RATE_FACTOR * doppler_hz)))
        low_rate = rate / self.ratio
        half = max(2, math.ceil(math.sqrt(math.log(1 / FIR_FLOOR)) / (2 * math.pi * sigma) * low_rate))
        self.fir = [math.exp(-4 * math.pi ** 2 * sigma ** 2 * ((k - half) / low_rate) ** 2) for k in range(2 * half + 1)]
        scale = 1 / math.sqrt(2 * sum(h * h for h in self.fir))
        self.fir = [h * scale for h in self.fir]
        self._history = [self._draw() for _ in self.fir]                    # (prefilled, so the process starts in its steady state)
        self.previous, self.following = self._next(), self._next()

    def _draw(self) -> complex:
        return complex(self._rng.gauss(0.0, 1.0), self._rng.gauss(0.0, 1.0))

    def _next(self) -> complex:
        """The next sample of the process at the low rate: one more draw into the history, the FIR over it."""
        self._history[self._index] = self._draw()
        self._index = (self._index + 1) % len(self.fir)
        history = self._history
        index = self._index
        total = 0j
        for h in self.fir:
            total += h * history[index]
            index += 1
            if index == len(history):
                index = 0
        return total

    def gains(self, count: int) -> list[complex]:
        """The next `count` values of g(t) at the sample rate."""
        if not self.fir:
            return [1 + 0j] * count
        out = []
        ratio, phase, previous, following = self.ratio, self._phase, self.previous, self.following
        for _ in range(count):
            out.append(previous + (phase / ratio) * (following - previous))
            phase += 1
            if phase == ratio:
                phase = 0
                previous, following = following, self._next()
        self._phase, self.previous, self.following = phase, previous, following
        return out


class Fading:
    """The Watterson HF channel (ITU-R F.1487) on one link, a `Shaper`: the real signal is made analytic (the Hilbert transformer above), each path's copy of it is delayed and multiplied by its own gain process, the paths are
    summed and the real part is the signal the receiver hears, with the same average power as what was sent (the paths' powers sum to 1). `Fading("poor")` is a CCIR 520-2 preset; `Fading(delay_ms=2.0, doppler_hz=1.0)`
    any two-path channel; `paths=1` a single path (no echo). The same seed gives the same channel; every link needs an instance of its own (the delay line and the gain processes are state), which `Channel.set_fading`
    hands out. The output lags the input by HILBERT_TAPS // 2 samples (the transformer's delay, 2.9 ms), which the pace of a frame does not notice."""

    def __init__(self, preset: str | None = None, delay_ms: float = 2.0, doppler_hz: float = 1.0, seed: int = 0, rate: int = RATE, paths: int = 2) -> None:
        if preset is not None:
            if preset not in PRESETS:
                raise ValueError(f"no fading preset {preset!r}: {', '.join(PRESETS)}")
            delay_ms, doppler_hz = PRESETS[preset]
        if paths not in (1, 2):
            raise ValueError("a path or two")
        self.preset, self.delay_ms, self.doppler_hz, self.seed = preset, delay_ms, doppler_hz, seed
        rng = random.Random(seed)
        self.delay = math.ceil(delay_ms * rate / 1000) if paths == 2 else 0          # (rounded up to a whole sample, as Mercury does)
        self.taps = hilbert_taps()
        self.half = HILBERT_TAPS // 2
        self._paths: list[tuple[int, float, _Tap]] = [(0, 1 / math.sqrt(paths), _Tap(doppler_hz, rate, rng))]      # (delay in samples, gain, the gain process)
        if paths == 2:
            self._paths.append((self.delay, 1 / math.sqrt(2), _Tap(doppler_hz, rate, rng)))
        self._input: list[float] = [0.0] * (2 * self.half)                    # the last 2 * half input samples: what the transformer needs of the past
        self._zi: list[float] = [0.0] * self.delay                             # the last `delay` analytic samples, for the delayed path
        self._zq: list[float] = [0.0] * self.delay

    def describe(self) -> str:
        return f"{self.preset or 'fading'}: {len(self._paths)} path(s), {self.delay_ms:g} ms, {self.doppler_hz:g} Hz, seed {self.seed}"

    def __call__(self, samples: array[int]) -> array[int]:
        count = len(samples)
        half = self.half
        history = self._input + list(samples)
        # the analytic signal at the block's positions, `half` samples late: in-phase the sample itself, quadrature the transformer over the samples round it
        zi = history[half:half + count]
        zq = [0.0] * count
        for m, h in self.taps:
            zq = [q + h * x for q, x in zip(zq, history[half - m:half - m + count])]
        self._input = history[-2 * half:]
        delay = self.delay
        all_i, all_q = self._zi + zi, self._zq + zq
        out = [0.0] * count
        for path_delay, gain, tap in self._paths:
            gains = tap.gains(count)
            start = delay - path_delay
            out = [y + gain * (g.real * i - g.imag * q) for y, g, i, q in zip(out, gains, all_i[start:start + count], all_q[start:start + count])]
        if delay:
            self._zi, self._zq = all_i[-delay:], all_q[-delay:]
        return array("h", [32767 if v > 32767 else -32768 if v < -32768 else round(v) for v in out])


@dataclass(eq=False)
class Station:
    """One Mercury's two pipes and what the channel counted of it."""
    name: str
    rx_fifo: str                                            # the channel writes what the station hears here
    tx_fifo: str                                            # the channel reads what the station transmits here
    blocks_sent: int = 0                                    # blocks in which it was keyed (it transmitted samples that are not all zero)
    blocks_heard: int = 0                                   # blocks in which it was not keyed and a transmission of another reached it
    overlapped_blocks: int = 0                              # of its keyed blocks, those in which another was keyed too
    dropped: int = 0                                        # blocks that could not be written: nobody reads the pipe yet, it is full, or the reader is gone
    starved: int = 0                                        # blocks in which a part of a block (fewer than 160 samples) waited for the rest of it
    keyed: bool = False                                     # keyed in the latest block
    _rx_fd: int | None = field(default=None, repr=False)
    _tx_fd: int | None = field(default=None, repr=False)
    _pending: bytearray = field(default_factory=bytearray, repr=False)
    _stale: int = field(default=0, repr=False)              # blocks the part of a block waited without more
    _tail: int = field(default=0, repr=False)               # blocks in which its latest transmission can still be heard (delays)
    _block: array[int] | None = field(default=None, repr=False)     # the samples it transmitted in the latest block, None when it was not keyed
    _history: array[int] = field(default_factory=lambda: array("h"), repr=False)

    @property
    def keyed_blocks(self) -> int:
        return self.blocks_sent

    def counts(self) -> dict[str, int]:
        return {"blocks_sent": self.blocks_sent, "blocks_heard": self.blocks_heard, "keyed_blocks": self.keyed_blocks, "overlapped_blocks": self.overlapped_blocks, "dropped": self.dropped, "starved": self.starved}


class Channel:
    """The air: see the module's docstring."""

    def __init__(self, snr_db: float = 30.0, seed: int = 0, block_ms: int = 20, on_block: Callable[[int, frozenset[str]], None] | None = None) -> None:
        if RATE * block_ms % 1000:
            raise ValueError(f"a block of {block_ms} ms is not a whole number of samples at {RATE} a second")
        self.snr_db = snr_db                                # of a transmission at gain 0 dB (REFERENCE_RMS) against the noise in 3 kHz; may be changed while it runs
        self.block_samples = RATE * block_ms // 1000
        self.block_bytes = self.block_samples * SAMPLE_BYTES
        self.block_sec = block_ms / 1000
        self.on_block = on_block                            # called after each block, in the channel's thread, with the block's number and the names of the stations that were keyed
        self.stations: dict[str, Station] = {}
        self.links: dict[tuple[str, str], Link] = {}
        self.blocks = 0
        self.collisions = 0
        self.late_blocks = 0                                # blocks that started a whole block late or more (the machine was too busy for the pace)
        self.work_sec_total = 0.0
        self.work_sec_max = 0.0
        self.failure: BaseException | None = None
        self._rng = random.Random(seed)
        self._lock = threading.RLock()
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None
        self._max_delay: dict[str, int] = {}

    @property
    def noise_sigma(self) -> float:
        """The standard deviation of the noise at each receiver, int16 units: white over 0 to 4 kHz, so its power in 3 kHz is three quarters of it, and that is what REFERENCE_RMS is `snr_db` above."""
        return REFERENCE_RMS * math.pow(10, -self.snr_db / 20) * math.sqrt(RATE / 2 / SNR_BANDWIDTH)

    def add(self, name: str, rx_fifo: str | os.PathLike[str], tx_fifo: str | os.PathLike[str]) -> Station:
        with self._lock:
            if name in self.stations:
                raise ValueError(f"a station {name} is on the channel already")
            station = self.stations[name] = Station(name, os.fspath(rx_fifo), os.fspath(tx_fifo))
            self._open_tx(station)
            self._open_rx(station)
            return station

    def set_link(self, a: str, b: str, gain_db: float = 0.0, delay: int = 0, shaper: Shaper | None = None, symmetric: bool = True) -> None:
        """The path from a to b (and from b to a, with the same values, unless symmetric is False). The shaper of a symmetric link is shared by the two directions, so give a stateful one to one direction."""
        for name in (a, b):
            if name not in self.stations:
                raise ValueError(f"no station {name} on the channel")
        if delay < 0:
            raise ValueError("a delay is a number of samples, not negative")
        with self._lock:
            for source, target in ((a, b), (b, a)) if symmetric else ((a, b),):
                self.links[(source, target)] = Link(gain_db, delay, shaper)
            for source in {a, b}:
                self._max_delay[source] = max((link.delay for (s, _), link in self.links.items() if s == source), default=0)

    def set_fading(self, preset: str | None, seed: int = 0, **fading: float) -> None:
        """Every link between the stations on the channel now (each direction on its own) goes through a Watterson channel of this preset (`Fading`; None: flat again), with its own random seed derived from `seed`; a link's
        gain and delay are kept. Stations added later are flat until this is called again."""
        with self._lock:
            names = list(self.stations)
            for n, source in enumerate(names):
                for k, target in enumerate(names):
                    if source == target:
                        continue
                    link = self.links.get((source, target), FLAT)
                    shaper = None if preset is None and not fading else Fading(preset, seed=seed * 1000 + n * len(names) + k, **fading)        # type: ignore[arg-type]
                    self.links[(source, target)] = Link(link.gain_db, link.delay, shaper)

    # ---- the thread ----

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("the channel is running")
        self._stopping.clear()
        self._thread = threading.Thread(target=self._run, name="hf channel", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Ends the thread and closes the pipes; raises what ended the thread early, if anything did."""
        self._stopping.set()
        if self._thread is not None:
            self._thread.join(5)
            self._thread = None
        with self._lock:
            for station in self.stations.values():
                for fd in (station._rx_fd, station._tx_fd):
                    if fd is not None:
                        os.close(fd)
                station._rx_fd = station._tx_fd = None
        if self.failure is not None:
            raise RuntimeError("the channel's thread ended with an error") from self.failure

    def __enter__(self) -> "Channel":
        self.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.stop()

    def _run(self) -> None:
        origin = time.monotonic()
        k = 0
        try:
            while not self._stopping.is_set():
                wait = origin + k * self.block_sec - time.monotonic()          # (block k is due at origin + k * 20 ms, so the pace never drifts)
                if wait > 0:
                    if self._stopping.wait(wait):
                        break
                elif wait < -self.block_sec:
                    self.late_blocks += 1
                self.process_block()
                k += 1
        except BaseException as error:
            self.failure = error

    # ---- one block ----

    def process_block(self) -> frozenset[str]:
        """Reads a block from every station, mixes and writes a block to every station; the names of those that were keyed."""
        began = time.perf_counter()
        with self._lock:
            number = self.blocks
            sent = {name: block for name, station in self.stations.items() if (block := self._take(station)) is not None}
            keyed = frozenset(sent)
            for station in self.stations.values():
                self._advance(station, sent.get(station.name))
                station.keyed = station.name in keyed
            if len(keyed) > 1:
                self.collisions += 1
            for station in self.stations.values():
                if station.keyed:
                    station.blocks_sent += 1
                    station.overlapped_blocks += len(keyed) > 1
                self._deliver(station)
            self.blocks += 1
            took = time.perf_counter() - began
            self.work_sec_total += took
            self.work_sec_max = max(self.work_sec_max, took)
        if self.on_block is not None:
            self.on_block(number, keyed)
        return keyed

    def _take(self, station: Station) -> array[int] | None:
        """The station's next block of samples if it is keyed in this one, from what its pipe has given so far."""
        fresh = self._read(station)
        pending = station._pending
        if len(pending) < self.block_bytes:
            if not pending:
                station._stale = 0
                return None
            station._stale = 0 if fresh else station._stale + 1
            if station._stale < TAIL_BLOCKS:
                station.starved += 1
                return None
            pending.extend(bytes(self.block_bytes - len(pending)))
            station._stale = 0
        block = s32le_to_pcm(bytes(pending[:self.block_bytes]))
        del pending[:self.block_bytes]
        station._stale = 0
        return block if any(block) else None

    def _read(self, station: Station) -> bool:
        """Takes everything the TX pipe has, without waiting; whether there was anything."""
        if station._tx_fd is None and not self._open_tx(station):
            return False
        got = False
        for _ in range(MAX_READS):
            assert station._tx_fd is not None
            try:
                data = os.read(station._tx_fd, READ_SIZE)
            except BlockingIOError:
                break
            except OSError:
                self._close_tx(station)
                break
            if not data:
                break
            station._pending.extend(data)
            got = True
        return got

    def _open_tx(self, station: Station) -> bool:
        try:
            station._tx_fd = os.open(station.tx_fifo, os.O_RDONLY | NONBLOCK)
        except OSError:                                         # (not made yet: tried again in the next block)
            return False
        return True

    def _close_tx(self, station: Station) -> None:
        if station._tx_fd is not None:
            os.close(station._tx_fd)
        station._tx_fd = None

    def _open_rx(self, station: Station) -> bool:
        try:
            station._rx_fd = os.open(station.rx_fifo, os.O_WRONLY | NONBLOCK)
        except OSError:                                         # (ENXIO: Mercury has not opened its side yet)
            return False
        return True

    def _advance(self, station: Station, block: array[int] | None) -> None:
        """Keeps what the station's links need of its past: the latest samples for a delayed link, and how long its latest transmission can still be heard."""
        delay = self._max_delay.get(station.name, 0)
        station._block = block
        if block is not None:
            station._tail = 1 + -(-delay // self.block_samples)
        else:
            station._tail = max(0, station._tail - 1)
        if delay:
            history = station._history
            history.extend(block if block is not None else array("h", bytes(2 * self.block_samples)))
            del history[:max(0, len(history) - delay - self.block_samples)]

    def _heard(self, source: Station, link: Link) -> array[int]:
        if link.delay:
            history = source._history
            end = len(history) - link.delay
            samples = history[max(0, end - self.block_samples):end]
            if len(samples) < self.block_samples:
                samples = array("h", bytes(2 * (self.block_samples - len(samples)))) + samples
        else:
            samples = source._block if source._block is not None else array("h", bytes(2 * self.block_samples))
        return link.shaper(samples) if link.shaper is not None else samples

    def _deliver(self, receiver: Station) -> None:
        sigma = self.noise_sigma
        gauss = self._rng.gauss
        mixed = [gauss(0.0, sigma) for _ in range(self.block_samples)] if sigma else [0.0] * self.block_samples
        reached = False
        if not receiver.keyed:
            for source in self.stations.values():
                link = self.links.get((source.name, receiver.name), FLAT)
                if source is receiver or not source._tail or not link.factor:
                    continue
                heard = self._heard(source, link)
                factor = link.factor
                mixed = [m + factor * s for m, s in zip(mixed, heard)]
                reached = True
            receiver.blocks_heard += reached
        data = array("i", [(32767 if v > 32767 else -32768 if v < -32768 else round(v)) << 16 for v in mixed])
        if SWAP:
            data.byteswap()
        self._write(receiver, data.tobytes())

    def _write(self, station: Station, data: bytes) -> None:
        if station._rx_fd is None and not self._open_rx(station):
            station.dropped += 1
            return
        assert station._rx_fd is not None
        try:
            os.write(station._rx_fd, data)                      # (a block is far under PIPE_BUF, so it goes whole or not at all)
        except BlockingIOError:
            station.dropped += 1
        except OSError:                                         # (the reader is gone: opened again when the next one appears)
            os.close(station._rx_fd)
            station._rx_fd = None
            station.dropped += 1

    def report(self) -> dict[str, Any]:
        with self._lock:
            return {
                "stations": {name: station.counts() for name, station in self.stations.items()},
                "totals": {"blocks": self.blocks, "collisions": self.collisions, "late_blocks": self.late_blocks,
                           "block_ms_mean": 1000 * self.work_sec_total / self.blocks if self.blocks else 0.0, "block_ms_max": 1000 * self.work_sec_max},
            }
