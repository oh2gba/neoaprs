"""The noise of the busy-detector measurements (scripts/mercury-measure busy and autobusy): what one receiver hears besides the channel's white noise, in scenes. A `Scene` stands in for `random.Random` of the channel
(tests/support/hfchannel.py calls `gauss(0, sigma)` for every sample of every block, so the scene sees every sample in order), and `BusyChannel` gives each receiver a scene of its own.

    white       the channel's white noise
    ssb         white noise through a receiver's 300 to 2700 Hz filter, as the audio of an SSB radio is
    carriers    the same with three steady carriers at 600, 1300 and 2100 Hz that stand `excess` dB over the noise of their 150 Hz band (heterodynes, the carriers of broadcasters)
    step        white noise that rises by `excess` dB `EVENT_SEC` seconds after `arm()` and stays (the band opens, a new source of QRM)
    ramp        white noise that rises by `excess` dB over `RAMP_SEC` seconds after `arm()` (the slow rise of a band's noise towards the evening)
    bursts      white noise with bursts of static `excess` dB over it, 150 ms long, a few seconds apart, from `arm()` on (QRN)
    fade        white noise whose level wanders by up to `excess` dB with a time of a few seconds, always (the band noise of an HF band)
    narrow      white noise through a narrow receiver filter, 500 to 2300 Hz at four poles: the bands beside the passband are 20 dB and more under the ones in it (a 1.8 kHz filter, the least Mercury's own notes allow)
    narrowvoice the same with the voice-like signal of `voice`
    voice       white noise with a voice-like signal `excess` dB over it from `arm()` on for `VOICE_SEC` seconds: noise through the receiver's filter and a low pass at 800 Hz (a spectrum that falls with the pitch, as speech's does),
                switched on and off in syllables of a few tenths of a second with a pause now and then

The time of an event is counted from `arm()`, which the measurement calls when the quiet part begins (the sample count of the scene, 8000 a second)."""
import math
import random
from collections.abc import Callable
from typing import Any

from tests.support.hfchannel import RATE, Channel

RECEIVER_BAND_HZ = 150.0                    # the bands of Mercury's detector (modem/channel_busy.h BUSY_BAND_HZ)
EVENT_SEC = 20.0                            # when an event of a scene begins, after `arm()`
RAMP_SEC = 120.0
VOICE_SEC = 60.0
BURST_SEC = 0.15
BURST_GAP_SEC = 4.0                         # the mean gap between two bursts
FADE_TAU_SEC = 4.0
KINDS = ("white", "ssb", "carriers", "step", "ramp", "bursts", "fade", "voice", "narrow", "narrowvoice")


class Bandpass:
    """Two biquads in a row, a high pass and a low pass of 12 dB an octave: the audio of an SSB receiver, as a radio's filter gives it (300 to 2700 Hz)."""

    def __init__(self, low_hz: float, high_hz: float) -> None:
        self.stages = [self._coefficients(low_hz, True), self._coefficients(high_hz, False)]
        self.state = [[0.0, 0.0], [0.0, 0.0]]

    @staticmethod
    def _coefficients(hz: float, high_pass: bool) -> tuple[float, float, float, float, float]:
        w = 2 * math.pi * hz / 8000.0
        alpha = math.sin(w) / (2 * 0.7071)
        cos = math.cos(w)
        a0 = 1 + alpha
        if high_pass:
            b0, b1, b2 = (1 + cos) / 2, -(1 + cos), (1 + cos) / 2
        else:
            b0, b1, b2 = (1 - cos) / 2, 1 - cos, (1 - cos) / 2
        return b0 / a0, b1 / a0, b2 / a0, -2 * cos / a0, (1 - alpha) / a0

    def __call__(self, x: float) -> float:
        for (b0, b1, b2, a1, a2), z in zip(self.stages, self.state, strict=True):
            y = b0 * x + z[0]
            z[0] = b1 * x - a1 * y + z[1]
            z[1] = b2 * x - a2 * y
            x = y
        return x


class Scene:
    """What one receiver hears besides the channel's noise level (`sigma` is the channel's, whatever the scene)."""

    def __init__(self, kind: str, seed: int, excess_db: float = 0.0) -> None:
        if kind not in KINDS:
            raise ValueError(f"no scene {kind!r}")
        self.rng = random.Random(seed)
        self.kind = kind
        self.excess = excess_db
        self.filter = Bandpass(500.0, 2300.0) if kind.startswith("narrow") else Bandpass(300.0, 2700.0)
        self.second = Bandpass(500.0, 2300.0) if kind.startswith("narrow") else None
        self.scale = 1.0
        self.n = 0                                  # samples drawn
        self.armed: int | None = None               # the sample count at `arm()`
        if kind in ("ssb", "carriers", "narrow", "narrowvoice"):
            self.scale = self._unit(self._shape)
        self.carriers = [(2 * math.pi * hz / 8000.0, self.rng.uniform(0, 2 * math.pi)) for hz in (600.0, 1300.0, 2100.0)] if kind == "carriers" else []
        self.voice_filter = Bandpass(300.0, 2700.0)
        self.voice_low = 0.0
        self.voice_scale = self._voice_unit() if kind in ("voice", "narrowvoice") else 1.0
        self._burst_left = 0
        self._burst_next = 0
        self._fade = 0.0
        self._fade_target = 0.0
        self._voice_left = 0
        self._voice_on = False

    def _shape(self, x: float) -> float:
        """The receiver's filter: one pair of poles, or two for the narrow one."""
        y = self.filter(x)
        return y if self.second is None else self.second(y)

    def _unit(self, shape: Callable[[float], float]) -> float:
        probe = [shape(self.rng.gauss(0.0, 1.0)) for _ in range(40000)][4000:]
        for stage in (*self.filter.state, *(self.second.state if self.second else [])):
            stage[:] = [0.0, 0.0]
        return 1.0 / math.sqrt(sum(v * v for v in probe) / len(probe))

    def _voice_unit(self) -> float:
        """The scale that makes the voice (white noise through the receiver's filter and the low pass) have the RMS of unit white noise."""
        probe = [self._voice_sample() for _ in range(40000)][4000:]
        self.voice_filter.state = [[0.0, 0.0], [0.0, 0.0]]
        self.voice_low = 0.0
        return 1.0 / math.sqrt(sum(v * v for v in probe) / len(probe))

    def _voice_sample(self) -> float:
        self.voice_low += (self.voice_filter(self.rng.gauss(0.0, 1.0)) - self.voice_low) * (1.0 - math.exp(-2 * math.pi * 800.0 / RATE))
        return self.voice_low

    def arm(self) -> None:
        """The quiet part begins now: the events of the scene are counted from here."""
        self.armed = self.n
        self._burst_next = self.n + self._gap()

    def seconds(self) -> float | None:
        """Seconds since `arm()`, None before it."""
        return None if self.armed is None else (self.n - self.armed) / RATE

    def _gap(self) -> int:
        return int(self.rng.expovariate(1.0 / BURST_GAP_SEC) * RATE) + 1

    def gauss(self, mu: float, sigma: float) -> float:
        t = self.seconds()
        value = self.rng.gauss(0.0, 1.0) if self.kind in ("white", "step", "ramp", "bursts", "fade", "voice") else self._shape(self.rng.gauss(0.0, 1.0)) * self.scale
        gain_db = self._gain_db(t)
        value *= sigma * math.pow(10.0, gain_db / 20.0)
        if self.carriers:
            amplitude = sigma * math.sqrt(2 * (math.pow(10, self.excess / 10) - 1) * RECEIVER_BAND_HZ / 4000.0)
            value += sum(amplitude * math.sin(step * self.n + phase) for step, phase in self.carriers)
        if self.kind == "bursts":
            value += self._burst(sigma)
        elif self.kind in ("voice", "narrowvoice"):
            value += self._voice(sigma, t)
        self.n += 1
        return value

    def _gain_db(self, t: float | None) -> float:
        if self.kind == "step":
            return self.excess if t is not None and t >= EVENT_SEC else 0.0
        if self.kind == "ramp":
            return 0.0 if t is None else self.excess * min(1.0, max(0.0, (t - EVENT_SEC) / RAMP_SEC))
        if self.kind == "fade":
            if self.n % 800 == 0:
                self._fade_target = self.rng.uniform(-self.excess, self.excess)
            self._fade += (self._fade_target - self._fade) / (FADE_TAU_SEC * RATE)
            return self._fade
        return 0.0

    def _burst(self, sigma: float) -> float:
        if self.armed is None:
            return 0.0
        if self._burst_left > 0:
            self._burst_left -= 1
            return self.rng.gauss(0.0, 1.0) * sigma * math.pow(10.0, self.excess / 20.0)
        if self.n >= self._burst_next:
            self._burst_left = int(BURST_SEC * RATE)
            self._burst_next = self.n + self._burst_left + self._gap()
        return 0.0

    def _voice(self, sigma: float, t: float | None) -> float:
        if t is None or not EVENT_SEC <= t < EVENT_SEC + VOICE_SEC:
            return 0.0
        if self._voice_left <= 0:
            self._voice_on = not self._voice_on
            length = self.rng.uniform(0.1, 0.3) if self._voice_on else (1.0 if self.rng.random() < 0.15 else self.rng.uniform(0.05, 0.3))
            self._voice_left = int(length * RATE)
        self._voice_left -= 1
        if not self._voice_on:
            return 0.0
        return self._voice_sample() * self.voice_scale * sigma * math.pow(10.0, self.excess / 20.0)


class BusyChannel(Channel):
    """The channel with a scene of its own for every receiver (`feeds`), whatever the SNR it is set to says about the level."""

    feeds: dict[str, Any]

    def _deliver(self, receiver: Any) -> None:
        feed = self.feeds.get(receiver.name)
        if feed is not None:
            self._rng = feed
        super()._deliver(receiver)
