"""The scope and the transmit level against the real Mercury (the one scripts/build-mercury --install builds, on its fifo audio backend, the simulated channel of tests/support/hfchannel.py as its air): its UI interface listens on the
loopback only, sends no spectrum until it is asked, sends it when asked, and the level worked back from it (neoaprs/mercuryscope.py) is the RMS of the channel's noise of known level; `set_tx_gain` changes the gain the status says, and
the tune tone's level is the peak the status says (a TUNE while the tone is on is refused, so a new level takes TUNE OFF first). Skipped where the built Mercury or named pipes are not there."""
import asyncio
import math
import os
import time
from pathlib import Path

import pytest

from neoaprs import kiss
from neoaprs.channelbusy import OccupancyBusy
from neoaprs.mercuryhelper import find, foreign_listeners
from neoaprs.mercuryscope import ROW_BINS, ROW_OFFSET_DB, ROW_STEP_DB, RowMeter, bands_db, parse_spectrum, parse_status
from neoaprs.mercuryui import MercuryUi
from neoaprs.source import Backoff
from tests.support.env import until
from tests.support.hfchannel import Channel
from tests.support.realmercury import fifo, start_mercury, stop

FIRST_PORT = 19400                      # (this test's own ports: the KISS port, the control port 200 above, the UI port 300 above)


def db_of_byte(byte: int) -> float:
    """A byte of a row as the modem's dB."""
    return ROW_OFFSET_DB + byte * ROW_STEP_DB


async def test_the_ui_interface_of_the_real_mercury_gives_the_spectrum_the_level_and_the_gain(tmp_path: Path) -> None:
    program = find()
    if program is None or not hasattr(os, "mkfifo") or "gui_interface/websocket" not in (Path(program[0]).parent / "SOURCE.txt").read_text(encoding="utf-8", errors="replace"):
        pytest.skip("the Mercury that scripts/build-mercury --install builds (with the UI interface on the loopback) and named pipes are needed")
    ports = (FIRST_PORT, FIRST_PORT + 200)
    ui_port = FIRST_PORT + 300                           # (below the ports of the test workers, which begin at 20000: tests/test_mercury_modem.py)
    channel = Channel(snr_db=10.0, seed=3)
    rx, tx = fifo(tmp_path, "rx"), fifo(tmp_path, "tx")
    channel.add("A", rx, tx)
    channel.start()
    process = start_mercury(program[0], tmp_path, "a", rx, tx, ports, ui_port=ui_port)
    texts: list[str] = []
    spectra = []
    ui = MercuryUi("127.0.0.1", ui_port, texts.append, lambda data: spectra.append(parse_spectrum(data)), lambda up: None, backoff=Backoff([0.2, 0.5]))
    ui.start()
    control_reader: asyncio.StreamReader | None = None
    control_writer: asyncio.StreamWriter | None = None
    try:
        await until(lambda: ui.connected, timeout_sec=30.0)
        assert foreign_listeners([ui_port]) == [], "the UI port listens on the loopback and nowhere else (packaging/mercury/loopback.patch)"
        await until(lambda: any(parse_status(t) for t in texts), timeout_sec=10.0)
        status = next(s for s in map(parse_status, texts) if s is not None)
        assert status.tx_gain_db == 0.0 and status.audio_ok
        await asyncio.sleep(1.0)
        assert spectra == [], "the ini turned the waterfall off: no spectrum until it is asked for"
        ui.waterfall(True)
        await until(lambda: len(spectra) >= 20, timeout_sec=10.0)
        meter = RowMeter()
        rows = []
        for spectrum in spectra[-20:]:
            assert spectrum is not None and spectrum.sample_rate == 8000 and len(spectrum.db) == 512
            row = meter.feed(spectrum, False)
            if row is not None:
                rows.append(row)
        assert len(rows) == 10 and all(len(row.bins) == ROW_BINS for row in rows)
        expected = 20 * math.log10(channel.noise_sigma / 32768) + 10 * math.log10(308 / 512)
        level = sum(row.level for row in rows) / len(rows)
        assert abs(level - expected) <= 1.5, f"the level of the channel's noise: expected {expected:.1f} dBFS, the rows say {level:.1f}"
        mean = sorted(10 * math.log10(sum(10 ** (db_of_byte(row.bins[i]) / 10) for row in rows) / len(rows)) for i in range(ROW_BINS))
        assert mean[ROW_BINS * 9 // 10] - mean[ROW_BINS // 4] <= 8, "white noise is flat: no bin of the passband stands out of the rest"
        ui.waterfall(False)
        await asyncio.sleep(0.5)
        seen = len(spectra)
        await asyncio.sleep(1.0)
        assert len(spectra) <= seen + 1, "and no spectrum once it is switched off"
        assert ui.tx_gain(6)
        await until(lambda: any((s := parse_status(t)) is not None and s.tx_gain_db == 6.0 for t in texts[-6:]), timeout_sec=10.0)
        control_reader, control_writer = await asyncio.open_connection("127.0.0.1", ports[1])
        control_writer.write(b"TUNE -15\r")
        await until(lambda: any((s := parse_status(t)) is not None and s.tx_peak_dbfs == -15.0 for t in texts[-6:]), timeout_sec=10.0)
        control_writer.write(b"TUNE -9\r")
        await asyncio.sleep(0.5)
        assert not any((s := parse_status(t)) is not None and s.tx_peak_dbfs == -9.0 for t in texts[-3:]), "Mercury 1.9.21 refuses a TUNE while the tone is on, whatever its comment says"
        control_writer.write(b"TUNE OFF\r")
        await asyncio.sleep(1.0)
        control_writer.write(b"TUNE -9\r")
        await until(lambda: any((s := parse_status(t)) is not None and s.tx_peak_dbfs == -9.0 for t in texts[-6:]), timeout_sec=10.0)
        control_writer.write(b"TUNE OFF\r")
        await asyncio.sleep(0.5)
    finally:
        if control_writer is not None:
            control_writer.close()
        await ui.stop()
        stop(process, 5.0)
        channel.stop()


async def test_the_automatic_busy_control_sees_a_frame_of_another_real_mercury_and_nothing_else(tmp_path: Path) -> None:
    """Two real Mercury instances on the simulated channel: the spectrum of the receiver, read through its UI interface, makes the control busy while the other one's frame is on the air, and clear after it; and it is
    not busy on the noise before. The numbers of the channels it was measured on are in docs/mercury.md."""
    program = find()
    if program is None or not hasattr(os, "mkfifo") or "gui_interface/websocket" not in (Path(program[0]).parent / "SOURCE.txt").read_text(encoding="utf-8", errors="replace"):
        pytest.skip("the Mercury that scripts/build-mercury --install builds (with the UI interface on the loopback) and named pipes are needed")
    sender, receiver = (FIRST_PORT + 20, FIRST_PORT + 220), (FIRST_PORT + 40, FIRST_PORT + 240)
    ui_port = receiver[0] + 300                          # (below the ports of the test workers: see the test above)
    channel = Channel(snr_db=20.0, seed=5)
    pipes = {name: (fifo(tmp_path, f"{name}-rx"), fifo(tmp_path, f"{name}-tx")) for name in ("A", "B")}
    for name, (rx, tx) in pipes.items():
        channel.add(name, rx, tx)
    channel.set_link("A", "B", gain_db=-8.0, symmetric=False)                 # (a frame at 12 dB SNR in 3 kHz)
    channel.start()
    processes = [start_mercury(program[0], tmp_path, "a", *pipes["A"], sender), start_mercury(program[0], tmp_path, "b", *pipes["B"], receiver, ui_port=ui_port)]
    detector = OccupancyBusy()
    states: list[tuple[float, bool]] = []
    started = time.monotonic()

    def spectrum(data: bytes) -> None:
        seen = parse_spectrum(data)
        if seen is not None and time.monotonic() - started > 1.0:                      # (the first second of a Mercury's spectra is a window that fills up from zeros)
            now = time.monotonic()
            states.append((now, detector.update(now, bands_db(seen))))

    ui = MercuryUi("127.0.0.1", ui_port, lambda text: None, spectrum, lambda up: None, backoff=Backoff([0.2, 0.5]))
    ui.want_waterfall = True
    ui.start()
    writer: asyncio.StreamWriter | None = None
    try:
        for _ in range(150):
            try:
                _, writer = await asyncio.open_connection("127.0.0.1", sender[0])
                break
            except OSError:
                await asyncio.sleep(0.2)
        assert writer is not None, "Mercury did not open its port"
        await until(lambda: ui.connected and len(states) > 20, timeout_sec=30.0)
        await asyncio.sleep(12.0)                                                  # (the floors of the control settle on the noise)
        assert not any(busy for _, busy in states), "noise alone is not a signal"
        writer.write(kiss.encode(b"OH2A>APNEO1:=6010.20N/02456.40E-a frame for the control"))
        sent_at = time.monotonic()
        await until(lambda: any(busy for when, busy in states if when > sent_at), timeout_sec=6.0)
        went_on = next(when for when, busy in states if busy and when > sent_at)
        await until(lambda: not states[-1][1], timeout_sec=15.0)
        went_off = next(when for when, busy in states if not busy and when > went_on)
        assert 2.0 < went_off - went_on < 7.0, f"busy for {went_off - went_on:.1f} s: a frame is 3.8 s on the air and the hang is about a second"
    finally:
        if writer is not None:
            writer.close()
        await ui.stop()
        for process in processes:
            stop(process, 5.0)
        channel.stop()
