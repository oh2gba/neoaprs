"""The HF channel for real Mercury instances (tests/support/hfchannel.py) on real named pipes: the tests play the stations' Mercury by writing s32le to each station's TX pipe and reading its RX pipe, and step the channel a block
at a time (`process_block`) so that nothing waits for the clock. A noiseless channel (`snr_db=inf`) gives exact samples; a noisy one is measured: a tone sent by one station is heard by the others as the same tone scaled by the
link's gain with noise at the asked SNR, a keyed station hears only noise, two keyed in one block are a collision that the receiver hears mixed, a delay, a fade shaper, clipping, a station whose pipes are not there yet does not
stall the others, a part of a block waits for its rest, a reader that is slow or gone costs blocks (counted), the same seed and bytes give the same bytes, and the pace holds in a thread and costs a small part of a block."""
import math
import os
import random
import time
from array import array
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.support.hfchannel import HILBERT_TAPS, PRESETS, REFERENCE_RMS, RATE, Attack, Channel, Fading, _Tap, hilbert_taps, pcm_to_s32le, s32le_to_pcm

BLOCK = 160
INF = math.inf
TONE_RMS = REFERENCE_RMS                                    # a transmission of the reference level
Feed = Callable[[int], None]


def tone(blocks: float, freq: float = 1000.0, rms: float = TONE_RMS) -> array[int]:
    """A sine of whole periods per block (1000 Hz: 20 periods in 160 samples) at this RMS."""
    return array("h", [round(rms * math.sqrt(2) * math.sin(2 * math.pi * freq * i / RATE)) for i in range(int(blocks * BLOCK))])


def rms(samples: array[int] | list[float]) -> float:
    return math.sqrt(sum(s * s for s in samples) / len(samples))


def amplitude(samples: array[int], freq: float = 1000.0) -> float:
    """The amplitude of the sine of this frequency in the samples (by projection: the samples hold whole periods)."""
    return 2 / len(samples) * sum(s * math.sin(2 * math.pi * freq * i / RATE) for i, s in enumerate(samples))


def minus(samples: array[int], other: array[int], factor: float = 1.0) -> list[float]:
    return [s - factor * o for s, o in zip(samples, other)]


class Rig:
    """The stations' ends of the pipes. The test's reader end of each RX pipe is open before the station is added (the channel opens its end without waiting, as it does for Mercury), the writer end of each TX pipe after."""

    def __init__(self, tmp_path: Path, names: str, **channel: object) -> None:
        self.folder = tmp_path
        self.channel = Channel(**channel)                   # type: ignore[arg-type]
        self.readers: dict[str, int] = {}
        self.writers: dict[str, int] = {}
        self.heard: dict[str, bytearray] = {n: bytearray() for n in names}
        for name in names:
            rx, tx = tmp_path / f"{name}.rx", tmp_path / f"{name}.tx"
            os.mkfifo(rx)
            os.mkfifo(tx)
            self.readers[name] = os.open(rx, os.O_RDONLY | os.O_NONBLOCK)
            self.channel.add(name, rx, tx)
            self.writers[name] = os.open(tx, os.O_WRONLY | os.O_NONBLOCK)

    def send(self, name: str, samples: array[int]) -> None:
        data = pcm_to_s32le(samples)
        assert os.write(self.writers[name], data) == len(data)

    def drain(self, name: str) -> None:
        while True:
            try:
                data = os.read(self.readers[name], 1 << 16)
            except BlockingIOError:
                return
            if not data:
                return
            self.heard[name].extend(data)

    def run(self, blocks: int, plan: dict[int, list[tuple[str, array[int]]]] | None = None) -> None:
        """`blocks` blocks of the channel; `plan` says what each station's Mercury writes just before block k."""
        for k in range(blocks):
            for name, samples in (plan or {}).get(k, []):
                self.send(name, samples)
            self.channel.process_block()
            for name in self.heard:
                self.drain(name)

    def samples(self, name: str, first: int = 0, last: int | None = None) -> array[int]:
        """What the station heard, from block `first` up to block `last` (not included)."""
        data = bytes(self.heard[name])
        return s32le_to_pcm(data[first * BLOCK * 4:None if last is None else last * BLOCK * 4])

    def close(self) -> None:
        self.channel.stop()
        for fd in (*self.readers.values(), *self.writers.values()):
            os.close(fd)


@pytest.fixture
def make(tmp_path: Path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("named pipes of this kind are POSIX's: the channel runs on Linux (the fading and the transformer are tested without them)")
    rigs: list[Rig] = []

    def build(names: str = "ABC", **channel: object) -> Rig:
        folder = tmp_path / f"rig{len(rigs)}"
        folder.mkdir()
        rigs.append(Rig(folder, names, **channel))
        return rigs[-1]
    yield build
    for rig in rigs:
        rig.close()


def plan_of(*sends: tuple[int, str, array[int]]) -> dict[int, list[tuple[str, array[int]]]]:
    """Each send (block, station, samples) written whole at its block: the samples of a block at a time."""
    plan: dict[int, list[tuple[str, array[int]]]] = {}
    for start, name, samples in sends:
        for i in range(len(samples) // BLOCK):
            plan.setdefault(start + i, []).append((name, samples[i * BLOCK:(i + 1) * BLOCK]))
    return plan


# ---- the conversion ----

def test_s32le_round_trips_int16_with_the_sample_in_the_top_half() -> None:
    samples = array("h", [0, 1, -1, 32767, -32768, 12345, -12345])
    data = pcm_to_s32le(samples)
    assert len(data) == 4 * len(samples)
    assert s32le_to_pcm(data) == samples
    assert data[:8] == bytes([0, 0, 0, 0, 0, 0, 1, 0])      # (0, then 1 << 16 little-endian)
    assert data[8:12] == bytes([0, 0, 0xFF, 0xFF])          # -1 << 16
    assert s32le_to_pcm(data + b"\x01\x02") == samples        # (a part of a word is dropped)
    assert s32le_to_pcm(bytes([0xFF, 0xFF, 0x34, 0x12])) == array("h", [0x1234])        # (what is in the low half does not matter)


# ---- what is heard ----

def test_a_tone_is_heard_as_the_same_tone_scaled_by_the_gain_with_noise_at_the_asked_snr(make) -> None:
    rig = make("ABC", snr_db=20.0, seed=3)
    rig.channel.set_link("A", "C", gain_db=20 * math.log10(0.5))
    sent = tone(40)
    rig.run(40, plan_of((0, "A", sent)))
    sigma = rig.channel.noise_sigma
    for name, factor in (("B", 1.0), ("C", 0.5)):
        heard = rig.samples(name)
        assert len(heard) == 40 * BLOCK
        assert amplitude(heard) == pytest.approx(factor * TONE_RMS * math.sqrt(2), rel=0.02)
        noise = minus(heard, sent, factor)
        assert rms(noise) == pytest.approx(sigma, rel=0.06)
        # the SNR of the reference level in 3 kHz (the noise is white up to 4 kHz, so 3/4 of it is in the band) is what was asked, for the link of gain 0 dB
        if factor == 1.0:
            snr = 20 * math.log10(TONE_RMS / (rms(noise) * math.sqrt(3 / 4)))
            assert snr == pytest.approx(20.0, abs=0.6)
    assert rig.channel.noise_sigma == pytest.approx(REFERENCE_RMS * 0.1 * math.sqrt(4 / 3))


def test_the_noise_is_there_without_any_transmission_and_the_default_channel_is_clean_but_not_silent(make) -> None:
    rig = make("AB")
    rig.run(10)
    for name in "AB":
        heard = rig.samples(name)
        assert len(heard) == 10 * BLOCK
        assert any(heard)
        assert rms(heard) == pytest.approx(REFERENCE_RMS * 10 ** (-30 / 20) * math.sqrt(4 / 3), rel=0.15)


def test_a_link_of_minus_infinity_is_no_path_at_all(make) -> None:
    rig = make("ABC", snr_db=INF)
    rig.channel.set_link("A", "C", gain_db=-INF, symmetric=False)
    sent = tone(3)
    rig.run(3, plan_of((0, "A", sent)))
    assert rig.samples("B") == sent
    assert not any(rig.samples("C"))
    assert rig.channel.report()["stations"]["C"]["blocks_heard"] == 0


def test_two_stations_keyed_in_the_same_blocks_are_a_collision_and_a_third_hears_both_mixed(make) -> None:
    rig = make("ABC", snr_db=INF)
    a, b = tone(10, 1000.0), tone(10, 500.0)
    rig.run(15, plan_of((0, "A", a), (5, "B", b)))
    heard = rig.samples("C")
    expected = array("h", [(a[i] if i < 10 * BLOCK else 0) + (b[i - 5 * BLOCK] if 5 * BLOCK <= i < 15 * BLOCK else 0) for i in range(15 * BLOCK)])
    assert heard == expected
    report = rig.channel.report()
    assert report["totals"]["blocks"] == 15 and report["totals"]["collisions"] == 5
    assert report["stations"]["A"] == {"blocks_sent": 10, "blocks_heard": 5, "keyed_blocks": 10, "overlapped_blocks": 5, "dropped": 0, "starved": 0}
    assert report["stations"]["B"] == {"blocks_sent": 10, "blocks_heard": 5, "keyed_blocks": 10, "overlapped_blocks": 5, "dropped": 0, "starved": 0}
    assert report["stations"]["C"] == {"blocks_sent": 0, "blocks_heard": 15, "keyed_blocks": 0, "overlapped_blocks": 0, "dropped": 0, "starved": 0}


def test_a_keyed_station_hears_only_noise_and_the_others_again_when_it_stops(make) -> None:
    rig = make("AB", snr_db=20.0, seed=5)
    b = tone(20, 500.0)
    rig.run(20, plan_of((0, "B", b), (5, "A", tone(5))))
    sigma = rig.channel.noise_sigma
    assert rig.channel.report()["stations"]["A"]["blocks_sent"] == 5
    keyed = rig.samples("A", 5, 10)
    assert rms(keyed) == pytest.approx(sigma, rel=0.1)
    assert abs(amplitude(keyed, 500.0)) < 0.1 * TONE_RMS
    for first, last in ((0, 5), (10, 20)):
        heard = rig.samples("A", first, last)
        assert amplitude(heard, 500.0) == pytest.approx(TONE_RMS * math.sqrt(2), rel=0.03)
        assert rms(minus(heard, b[first * BLOCK:last * BLOCK])) == pytest.approx(sigma, rel=0.1)
    assert rig.samples("B", 5, 10) != array("h", bytes(2 * 5 * BLOCK))            # (and B, keyed all the time, never heard A)
    assert amplitude(rig.samples("B", 5, 10)) < 0.1 * TONE_RMS


def test_the_sum_of_loud_transmissions_is_clipped_to_int16(make) -> None:
    rig = make("ABC", snr_db=INF)
    loud = array("h", [30000] * BLOCK)
    quiet = array("h", [-30000] * BLOCK)
    rig.run(2, plan_of((0, "A", loud), (0, "B", loud), (1, "A", quiet), (1, "B", quiet)))
    assert rig.samples("C") == array("h", [32767] * BLOCK + [-32768] * BLOCK)


def test_a_delay_moves_the_signal_by_that_many_samples_even_over_a_block_boundary(make) -> None:
    rig = make("ABC", snr_db=INF)
    rig.channel.set_link("A", "B", delay=10)
    rig.channel.set_link("A", "C", delay=200)
    pulse = array("h", [0] * BLOCK)
    pulse[155] = 1000
    pulse2 = array("h", [0] * BLOCK)
    pulse2[0] = 700
    rig.run(5, plan_of((0, "A", pulse), (1, "A", pulse2)))
    for name, delay in (("B", 10), ("C", 200)):
        heard = rig.samples(name)
        assert [(i, s) for i, s in enumerate(heard) if s] == [(155 + delay, 1000), (BLOCK + delay, 700)]


def test_a_shaper_is_applied_to_its_link_before_the_gain(make) -> None:
    rig = make("ABC", snr_db=INF)
    rig.channel.set_link("A", "B", gain_db=20 * math.log10(0.5), shaper=lambda s: array("h", [-x for x in s]), symmetric=False)
    sent = tone(2)
    rig.run(2, plan_of((0, "A", sent)))
    assert rig.samples("C") == sent
    assert rig.samples("B") == array("h", [round(-x / 2) for x in sent])


def test_an_attack_mutes_the_first_milliseconds_of_every_transmission_from_its_first_sample_that_is_not_zero(make) -> None:
    rig = make("AB", snr_db=INF)
    attack = Attack(lambda: rig.channel.blocks, ms=30.0)
    rig.channel.set_link("A", "B", shaper=attack, symmetric=False)
    lead = 40                                                           # (silence ahead of the audio inside the first block: Mercury's 100 ms of it is no audio to a VOX)
    sent = array("h", bytes(2 * lead)) + array("h", [1000] * (3 * BLOCK - lead))
    rig.run(12, plan_of((1, "A", sent), (7, "A", sent)))                # (two transmissions with silent blocks between: the attack starts over)
    muted = 30 * RATE // 1000
    expected = array("h", sent)
    expected[lead:lead + muted] = array("h", bytes(2 * muted))
    assert rig.samples("B", 1, 4) == expected and rig.samples("B", 7, 10) == expected
    assert rig.samples("B", 4, 7) == array("h", bytes(2 * 3 * BLOCK)), "nothing but the transmissions"


# ---- fading: the Watterson channel ----


def test_the_hilbert_transformer_turns_a_tone_into_its_quadrature_and_a_steady_path_is_the_tone_itself_a_little_late() -> None:
    """A one-path channel with no Doppler spread is the identity but for the transformer's delay, and the transformer's quadrature of a cosine at 1 kHz is the sine, within a percent, which is what the fading multiplies."""
    half = HILBERT_TAPS // 2
    taps = dict(hilbert_taps())
    assert all(m % 2 for m in taps) and len(taps) == half + 1 and taps[1] == pytest.approx(2 / math.pi, rel=0.01) and taps[-1] == -taps[1]
    for freq in (500.0, 1000.0, 1500.0, 3000.0):
        quadrature = sum(h * math.sin(2 * math.pi * freq * m / RATE) for m, h in taps.items())          # (the transformer's response at this frequency is -j times this: 1 for the ideal one)
        assert quadrature == pytest.approx(1.0, abs=0.012), (freq, quadrature)
    steady = Fading(delay_ms=0.0, doppler_hz=0.0, paths=1)
    sent = tone(4)
    heard = array("h")
    for k in range(4):
        heard.extend(steady(sent[k * BLOCK:(k + 1) * BLOCK]))
    assert list(heard[half:half + 3 * BLOCK]) == pytest.approx(list(sent[:3 * BLOCK]), abs=1), "the tone itself, `half` samples late"


def test_two_steady_paths_are_an_echo_at_the_delay_with_the_powers_summing_to_one() -> None:
    half = HILBERT_TAPS // 2
    echo = Fading(delay_ms=2.0, doppler_hz=0.0)
    assert echo.delay == 16, "2 ms at 8000 samples a second"
    impulse = array("h", [0] * BLOCK)
    impulse[10] = 10000
    heard = echo(impulse)
    heard.extend(echo(array("h", [0] * BLOCK)))
    assert heard[10 + half] == pytest.approx(10000 / math.sqrt(2), abs=2) and heard[10 + half + 16] == pytest.approx(10000 / math.sqrt(2), abs=2)
    assert sum(abs(v) for i, v in enumerate(heard) if i not in (10 + half, 10 + half + 16)) < 0.25 * 10000, "the transformer's ripple only"


def test_the_gain_process_has_unit_power_and_the_gaussian_spectrum_of_the_doppler_spread() -> None:
    """The tap process at its low rate: E|g|^2 = 1, and its autocorrelation is the Gaussian spectrum's, exp(-2 pi^2 sigma^2 tau^2) with sigma half the spread (ITU-R F.1487), checked at one and three low-rate steps."""
    for spread in (1.0, 0.5):
        tap = _Tap(spread, RATE, random.Random(5))
        low_rate = RATE / tap.ratio
        assert 64 * spread <= low_rate < 128 * spread, "drawn at 64 to 128 times the spread"
        samples = [tap._next() for _ in range(20000)]
        power = sum(abs(g) ** 2 for g in samples) / len(samples)
        assert power == pytest.approx(1.0, rel=0.1), (spread, power)
        sigma = spread / 2
        for lag in (1, 3):
            measured = sum((samples[i] * samples[i + lag].conjugate()).real for i in range(len(samples) - lag)) / (len(samples) - lag) / power
            expected = math.exp(-2 * math.pi ** 2 * sigma ** 2 * (lag / low_rate) ** 2)
            assert measured == pytest.approx(expected, abs=0.04), (spread, lag, measured, expected)


def test_a_poor_channel_fades_a_tone_deeply_and_keeps_its_average_power(make) -> None:
    """Twenty seconds of a tone through the poor channel: the average power is the tone's within a decibel or so, and there are blocks faded by more than 10 dB (a fade of 10 dB about once in two seconds on this channel)."""
    poor = Fading("poor", seed=3)
    assert poor.describe() == "poor: 2 path(s), 2 ms, 1 Hz, seed 3" and PRESETS["poor"] == (2.0, 1.0)
    blocks = 1000
    sent = tone(1)
    levels = []
    for _ in range(blocks):
        heard = poor(sent)
        levels.append(rms(heard))
    average = math.sqrt(sum(v * v for v in levels) / blocks)
    assert 20 * math.log10(average / TONE_RMS) == pytest.approx(0.0, abs=1.5)
    deep = sum(1 for v in levels if v < TONE_RMS * 10 ** (-10 / 20))
    assert 20 <= deep <= 400, f"{deep} of {blocks} blocks more than 10 dB down"
    assert any(v > TONE_RMS * 1.3 for v in levels), "and the two paths add up in phase at times"


def test_set_fading_gives_each_direction_its_own_channel_and_keeps_the_links_gains(make) -> None:
    rig = make("ABC", snr_db=INF)
    rig.channel.set_link("A", "B", gain_db=-6.0, delay=0, symmetric=False)
    rig.channel.set_fading("poor", seed=1)
    links = rig.channel.links
    assert {key for key in links} == {("A", "B"), ("B", "A"), ("A", "C"), ("C", "A"), ("B", "C"), ("C", "B")}
    assert links[("A", "B")].gain_db == -6.0 and links[("B", "A")].gain_db == 0.0
    shapers = [link.shaper for link in links.values()]
    assert all(isinstance(s, Fading) for s in shapers) and len({s.seed for s in shapers}) == 6, "a channel of its own in each direction"
    rig.run(10, plan_of((0, "A", tone(8))))
    b, c = rig.samples("B", 2, 10), rig.samples("C", 2, 10)
    assert b != c and rms(b) > 0 and rms(c) > 0, "B and C hear A through different fades"
    rig.channel.set_fading(None)
    assert all(link.shaper is None for link in rig.channel.links.values()) and rig.channel.links[("A", "B")].gain_db == -6.0


def test_a_block_through_four_faded_links_costs_a_part_of_the_twenty_milliseconds(make, capsys) -> None:
    rig = make("ABCDE", snr_db=20.0)
    rig.channel.set_fading("poor", seed=2)
    rig.run(50, plan_of((0, "A", tone(50))))
    totals = rig.channel.report()["totals"]
    with capsys.disabled():
        print(f"\n5 stations, 1 keyed, every link faded: {totals['block_ms_mean']:.2f} ms a block on average, {totals['block_ms_max']:.2f} ms at most, of {1000 * rig.channel.block_sec:.0f}")
    assert totals["block_ms_mean"] < 12


def test_links_to_stations_that_are_not_there_or_with_a_negative_delay_are_refused(make) -> None:
    rig = make("AB")
    with pytest.raises(ValueError, match="no station Z"):
        rig.channel.set_link("A", "Z")
    with pytest.raises(ValueError, match="delay"):
        rig.channel.set_link("A", "B", delay=-1)
    with pytest.raises(ValueError, match="already"):
        rig.channel.add("A", "x", "y")


# ---- stations that are not ready ----

def test_a_station_whose_pipes_are_not_there_yet_does_not_stall_the_others_and_is_picked_up_when_they_are(make, tmp_path: Path) -> None:
    rig = make("AB", snr_db=INF)
    late = rig.channel.add("N", tmp_path / "N.rx", tmp_path / "N.tx")       # (neither pipe exists)
    sent = tone(4)
    started = time.monotonic()
    rig.run(4, plan_of((0, "A", sent)))
    assert time.monotonic() - started < 1
    assert rig.samples("B") == sent
    assert late.dropped == 4
    os.mkfifo(tmp_path / "N.rx")
    os.mkfifo(tmp_path / "N.tx")
    reader = os.open(tmp_path / "N.rx", os.O_RDONLY | os.O_NONBLOCK)
    rig.channel.process_block()                                              # (the channel opens the TX pipe it finds: only then can Mercury open its end for writing)
    writer = os.open(tmp_path / "N.tx", os.O_WRONLY | os.O_NONBLOCK)
    try:
        os.write(writer, pcm_to_s32le(sent[:BLOCK]))
        rig.run(1)
        assert late.blocks_sent == 1 and late.dropped == 4
        assert s32le_to_pcm(os.read(reader, 1 << 16))[-BLOCK:] == array("h", bytes(2 * BLOCK))      # (it hears nothing of its own transmission)
        assert rig.samples("B", 5, 6) == sent[:BLOCK]
    finally:
        os.close(reader)
        os.close(writer)


def test_a_station_whose_writer_never_opens_is_silent_and_costs_the_others_nothing(make, tmp_path: Path) -> None:
    rig = make("AB", snr_db=INF)
    os.mkfifo(tmp_path / "Q.rx")
    os.mkfifo(tmp_path / "Q.tx")
    reader = os.open(tmp_path / "Q.rx", os.O_RDONLY | os.O_NONBLOCK)
    quiet = rig.channel.add("Q", tmp_path / "Q.rx", tmp_path / "Q.tx")
    try:
        sent = tone(3)
        rig.run(3, plan_of((0, "A", sent)))
        assert rig.samples("B") == sent
        assert quiet.blocks_sent == 0 and quiet.starved == 0
        assert s32le_to_pcm(os.read(reader, 1 << 16)) == sent
    finally:
        os.close(reader)


def test_a_part_of_a_block_waits_for_the_rest_and_is_padded_when_no_more_comes(make) -> None:
    rig = make("AB", snr_db=INF)
    sent = tone(2)
    rig.send("A", sent[:100])
    rig.run(1)
    assert not any(rig.samples("B"))
    assert rig.channel.stations["A"].starved == 1 and rig.channel.stations["A"].blocks_sent == 0
    rig.send("A", sent[100:BLOCK])                                       # (the rest arrives: one whole block, no padding)
    rig.run(1)
    assert rig.samples("B", 1, 2) == sent[:BLOCK]
    rig.send("A", sent[BLOCK:BLOCK + 70])                                # (the end of a frame: 70 samples, then nothing)
    rig.run(1)
    rig.run(2)
    tail = rig.samples("B", 4, 5)
    assert tail == sent[BLOCK:BLOCK + 70] + array("h", bytes(2 * 90))
    assert rig.channel.stations["A"].blocks_sent == 2 and rig.channel.stations["A"].starved == 3


def test_blocks_of_digital_silence_from_a_station_are_not_a_transmission(make) -> None:
    rig = make("AB", snr_db=INF)
    rig.run(2, plan_of((0, "A", array("h", [0] * 2 * BLOCK))))
    assert rig.channel.stations["A"].blocks_sent == 0 and rig.channel.collisions == 0


def test_a_reader_that_does_not_read_costs_blocks_and_one_that_is_gone_and_comes_back_is_served_again(make) -> None:
    rig = make("AB")
    for _ in range(130):                                                 # (a pipe holds 64 KB: about a hundred blocks)
        rig.channel.process_block()
    dropped = rig.channel.stations["A"].dropped
    assert 20 <= dropped <= 40                                          # (small writes share a page: about 96 fit)
    rig.drain("A")
    rig.channel.process_block()
    assert rig.channel.stations["A"].dropped == dropped
    os.close(rig.readers["A"])
    rig.channel.process_block()
    rig.channel.process_block()
    assert rig.channel.stations["A"].dropped == dropped + 1 + 1          # (the write that found no reader, then the open that found none)
    rig.readers["A"] = os.open(rig.folder / "A.rx", os.O_RDONLY | os.O_NONBLOCK)
    rig.channel.process_block()
    assert rig.channel.stations["A"].dropped == dropped + 2
    assert len(os.read(rig.readers["A"], 1 << 16)) == BLOCK * 4


# ---- the run ----

def run_bytes(make, seed: int) -> list[bytes]:
    rig = make("ABC", snr_db=12.0, seed=seed)
    rig.channel.set_link("A", "C", gain_db=-9.0, delay=33)
    rig.run(12, plan_of((0, "A", tone(8)), (4, "B", tone(6, 700.0))))
    return [bytes(rig.heard[n]) for n in "ABC"]


def test_the_same_seed_and_the_same_bytes_in_give_the_same_bytes_out(make) -> None:
    first = run_bytes(make, 7)
    assert run_bytes(make, 7) == first
    assert run_bytes(make, 8) != first


def test_the_hook_gets_the_block_number_and_who_was_keyed(make) -> None:
    seen: list[tuple[int, frozenset[str]]] = []
    rig = make("ABC", snr_db=INF, on_block=lambda k, keyed: seen.append((k, keyed)))
    rig.run(4, plan_of((1, "A", tone(2)), (2, "B", tone(1))))
    assert seen == [(0, frozenset()), (1, frozenset("A")), (2, frozenset("AB")), (3, frozenset())]


def test_the_thread_keeps_the_pace_of_the_clock_and_delivers(make) -> None:
    rig = make("AB", snr_db=30.0)
    sent = tone(10)
    rig.send("A", sent)
    started = time.monotonic()
    rig.channel.start()
    try:
        time.sleep(0.5)
        for name in "AB":
            rig.drain(name)
    finally:
        rig.channel.stop()
    for name in "AB":
        rig.drain(name)                         # (a block the thread wrote between the read above and the stop is counted in `blocks`: it is read too, or the count and the samples differ by one)
    elapsed = time.monotonic() - started
    blocks = rig.channel.blocks
    assert elapsed / 0.02 - 4 <= blocks <= elapsed / 0.02 + 1, (blocks, elapsed)
    heard = rig.samples("B")
    assert len(heard) == blocks * BLOCK - 0 and amplitude(heard[:10 * BLOCK]) == pytest.approx(TONE_RMS * math.sqrt(2), rel=0.05)
    assert rig.channel.failure is None          # (the pace is the count of blocks above; how many started late in half a second says only how busy the machine was: a CI runner under -n auto started 13 of 26 late and kept the pace. The share of late blocks is measured over minutes by the simulation stage)


def test_a_block_of_eight_stations_costs_a_small_part_of_the_twenty_milliseconds(make, capsys) -> None:
    names = "ABCDEFGH"
    rig = make(names, snr_db=15.0)
    for i, name in enumerate(names[1:], 1):
        rig.channel.set_link("A", name, gain_db=-3.0 * i, delay=7 * i)
    rig.channel.set_link("B", "C", gain_db=-20.0, delay=300)
    plan = plan_of((0, "A", tone(60)), (0, "B", tone(60, 600.0)), (0, "C", tone(60, 400.0)))
    rig.run(60, plan)
    totals = rig.channel.report()["totals"]
    with capsys.disabled():
        print(f"\n8 stations, 3 keyed: {totals['block_ms_mean']:.2f} ms a block on average, {totals['block_ms_max']:.2f} ms at most, of {1000 * rig.channel.block_sec:.0f}")
    assert totals["block_ms_mean"] < 5 and totals["collisions"] == 60
