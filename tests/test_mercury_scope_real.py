"""The scope and the transmit level against the real Mercury (the one scripts/build-mercury --install builds, on its fifo audio backend, the simulated channel of tests/support/hfchannel.py as its air): its UI interface listens on the
loopback only, sends no spectrum until it is asked, sends it when asked, and the level worked back from it (neoaprs/mercuryscope.py) is the RMS of the channel's noise of known level; `set_tx_gain` changes the gain the status says, and
the tune tone's level is the peak the status says (a TUNE while the tone is on is refused, so a new level takes TUNE OFF first). Skipped where the built Mercury or named pipes are not there."""
import asyncio
import math
import os
from pathlib import Path

import pytest

from neoaprs.mercury import UI_OFFSET
from neoaprs.mercuryhelper import find, foreign_listeners
from neoaprs.mercuryscope import SCOPE_BINS, ScopeMeter, parse_spectrum, parse_status
from neoaprs.mercuryui import MercuryUi
from neoaprs.source import Backoff
from tests.support.env import until
from tests.support.hfchannel import Channel
from tests.support.realmercury import fifo, start_mercury, stop

FIRST_PORT = 19400                      # (this test's own ports: the KISS port, the control port 200 above, the UI port)


async def test_the_ui_interface_of_the_real_mercury_gives_the_spectrum_the_level_and_the_gain(tmp_path: Path) -> None:
    program = find()
    if program is None or not hasattr(os, "mkfifo") or "gui_interface/websocket" not in (Path(program[0]).parent / "SOURCE.txt").read_text(encoding="utf-8", errors="replace"):
        pytest.skip("the Mercury that scripts/build-mercury --install builds (with the UI interface on the loopback) and named pipes are needed")
    ports = (FIRST_PORT, FIRST_PORT + 200)
    ui_port = FIRST_PORT + UI_OFFSET
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
        meter = ScopeMeter()
        for spectrum in spectra[-20:]:
            assert spectrum is not None and spectrum.sample_rate == 8000 and len(spectrum.db) == 512
            meter.feed(spectrum)
        picture = meter.take()
        assert picture is not None and len(picture.bins) == SCOPE_BINS
        expected = 20 * math.log10(channel.noise_sigma / 32768) + 10 * math.log10(308 / 512)
        assert abs(picture.level - expected) <= 1.5, f"the level of the channel's noise: expected {expected:.1f} dBFS, the scope says {picture.level}"
        assert max(picture.bins) <= 8, "white noise is flat: nothing stands out of the floor"
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
