"""The scope and the transmit level in the modem part (neoaprs/mercuryscoping.py, mercurymodem.py): the ini the daemon writes (the gain, the UI interface on a port of its own with the waterfall off), the link to the program's UI,
the rows of the waterfall made only while a page wants them, the gain sent live and the peak the status says, a Mercury without the interface (no scope, the gain waits for the next start), and the tune tone that follows the gain. The
program is the fake Mercury of the suite (tests/support/fakemercury.py), whose UI is tests/support/fakemercuryui.py; the real Mercury is tests/test_mercury_scope_real.py."""
import asyncio
import json
import socket
import time
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs import mercurychannel  # noqa: F401  (the module that holds the hold)
from neoaprs import mercuryhelper
from neoaprs.mercury import CONTROL_OFFSET, UI_OFFSET
from neoaprs.mercuryscope import ROW_BINS, ROW_FIRST_BIN, ScopeRow, byte_of_db
from neoaprs.mercurymodem import CHANNEL_BUSY, INI_FILE, TRANSMITTING, Mercury
from neoaprs.source import Backoff
from tests.support import fakemercury
from tests.support.env import until
from tests.support.fakemercury import UI_LOG_FILE, UI_SCENE_FILE, Air
from tests.test_mercury_modem import HF, QUICK, _ports_of_this_test  # noqa: F401  (the fixture gives each test ports of its own)

UI_NEAR = 400                                    # the UI port of a test is this far above its KISS port (tests/support/fixtures.py: inside the range of the worker)


def modem(tmp_path: Path, no_ui: bool = False) -> Mercury:
    m = Mercury(tmp_path, finder=lambda: fakemercury.program(no_ui=no_ui), backoff=QUICK, control_backoff=Backoff([0.05, 0.05]))
    m.ports = lambda: []
    return m


def sent(tmp_path: Path) -> list[str]:
    """The commands the fake program's UI was given, one a line."""
    try:
        return (tmp_path / UI_LOG_FILE).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def test_the_ui_port_is_the_kiss_port_plus_a_fixed_distance_and_a_pair_whose_ui_port_is_taken_is_not_free() -> None:
    assert UI_OFFSET == 2000, "10100 with Mercury's defaults: not Mercury's own 10000"
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = taken.getsockname()[1] - mercuryhelper.UI_OFFSET
        assert port > 0 and not mercuryhelper.pair_free(port), "a broadcast port whose UI port something holds is passed over"


async def test_the_ini_has_the_gain_and_the_ui_interface_on_its_own_port_with_the_waterfall_off(tmp_path: Path) -> None:
    m = modem(tmp_path)
    await m.start(replace(HF, mercury_tx_gain_db=-4))
    try:
        ini = (tmp_path / INI_FILE).read_text()
        assert m.tx_gain_db == -4 and "[audio]\ntx_gain_db = -4\n" in ini
        assert f"[main]\nui_enabled = true\nui_port = {m.broadcast_port + UI_NEAR}\nwaterfall_enabled = false\n" in ini and m.ui_port == m.broadcast_port + UI_NEAR
        assert m.control_port == m.broadcast_port + CONTROL_OFFSET
        await until(lambda: m.scope, 10.0)
    finally:
        await m.stop()
    assert not m.scope and m.tx_peak_dbfs is None


async def test_a_mercury_something_else_runs_and_the_speaker_of_the_dummy_have_no_ui_of_ours(tmp_path: Path) -> None:
    air = Air(frame_sec=0.2)
    station = air.station()
    await air.start()
    m = Mercury(tmp_path, backoff=QUICK, control_backoff=Backoff([0.05, 0.05]))
    m.ports = lambda: []
    try:
        await m.start(HF, attach=station.url)
        assert m.ui_port == 0 and not m.scope and not m.live_gain, "its UI port, if it has one, is not ours to know"
    finally:
        await m.stop()
        await air.aclose()
    s = modem(tmp_path)
    s.speaker = True
    assert s.ui_port == 0


async def test_the_feed_is_on_for_the_busy_control_and_rows_of_the_waterfall_are_made_only_while_a_page_wants_the_scope_and_say_where_the_tone_is_and_whether_the_radio_transmits(tmp_path: Path) -> None:
    m = modem(tmp_path)
    rows: list[ScopeRow] = []
    m.scope_row.connect(rows.append)
    await m.start(HF)
    try:
        await until(lambda: m.scope, 10.0)
        await until(lambda: "set_waterfall on" in sent(tmp_path))
        await asyncio.sleep(0.5)
        assert rows == [], "nobody wants the scope: no row is made (the spectrum is read all the same, by the busy control)"
        m.want_scope(True)
        await until(lambda: len(rows) >= 3)
        row = rows[-1]
        tone = round(1500 / 7.8125) - ROW_FIRST_BIN
        assert len(row.bins) == ROW_BINS and row.tx is False and -90 <= row.level <= 0
        assert row.bins[tone] > row.bins[tone - 5] + 20 and row.bins[tone] == byte_of_db(-30.0), "the fake program's tone at 1500 Hz stands in its own bin of the modem, 7.8 Hz wide"
        m.keyed = True
        mark = len(rows)
        await until(lambda: len(rows) > mark + 2)
        assert all(r.tx for r in rows[mark + 2:]), "keyed: the rows are of our own signal"
        m.keyed = False
        m.want_scope(False)
        await asyncio.sleep(0.3)
        seen = len(rows)
        await asyncio.sleep(0.5)
        assert len(rows) <= seen + 1
        assert "set_waterfall off" not in sent(tmp_path), "the feed stays on: the busy control reads it"
    finally:
        m.keyed = False
        await m.stop()


async def test_the_gain_is_sent_to_the_running_program_and_the_peak_it_says_is_told_to_the_page(tmp_path: Path) -> None:
    m = modem(tmp_path)
    told = 0

    def changed() -> None:
        nonlocal told
        told += 1
    m.changed.connect(changed)
    await m.start(HF)
    try:
        await until(lambda: m.scope and m.state == "running", 10.0)
        assert m.live_gain and m.tx_peak_dbfs is None, "Mercury says -120 before anything was transmitted"
        m.set_tx_gain(7)
        await until(lambda: "set_tx_gain 7" in sent(tmp_path))
        assert m.tx_gain_db == 7
        await until(lambda: m.tx_peak_dbfs == 1, 5.0)                          # (-6.4 dBFS at gain 0, +7 dB: 0.6, whole dB)
        m.set_tx_gain(99)
        await until(lambda: "set_tx_gain 20" in sent(tmp_path))
        assert m.tx_gain_db == 20, "Mercury's own limit"
        before = len(sent(tmp_path))
        m.set_tx_gain(20)
        await asyncio.sleep(0.1)
        assert len(sent(tmp_path)) == before, "the same gain again is nothing"
    finally:
        await m.stop()
    assert told > 0


async def test_a_mercury_without_the_ui_has_no_scope_and_the_gain_waits_for_the_next_start(tmp_path: Path) -> None:
    m = modem(tmp_path, no_ui=True)
    await m.start(replace(HF, mercury_tx_gain_db=2))
    try:
        await until(lambda: m.state == "running", 10.0)
        await asyncio.sleep(0.5)
        assert not m.scope and not m.live_gain, "no interface: the controller starts the modem again at a change of the gain (it is in the settings the restart is decided by)"
        m.want_scope(True)
        m.set_tx_gain(5)
        assert m.tx_gain_db == 5 and sent(tmp_path) == [], "nothing could be sent"
        assert m.state == "running" and m.describe() == "Mercury DATAC3, listening"
    finally:
        await m.stop()


async def test_the_link_is_made_again_for_a_program_started_again(tmp_path: Path) -> None:
    m = modem(tmp_path)
    await m.start(HF)
    try:
        await until(lambda: m.scope, 10.0)
        m.want_scope(True)
        await until(lambda: "set_waterfall on" in sent(tmp_path))
        pid = m.pid
        assert pid is not None
        import os
        import signal
        os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))          # (Windows has no SIGKILL: its SIGTERM is TerminateProcess, as sudden)
        await until(lambda: m.pid != pid and m.scope and m.state == "running", 20.0)
        assert sent(tmp_path).count("set_waterfall on") >= 2, "what a page wants is asked for again of the new program"
    finally:
        await m.stop()


async def test_the_tune_tone_follows_the_gain_and_is_begun_again_when_the_gain_moves_under_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from neoaprs import mercurytune
    monkeypatch.setattr(mercurytune, "TUNE_SEC", 5.0)
    air = Air(frame_sec=0.2)
    station = air.station()
    await air.start()
    m = Mercury(tmp_path, backoff=QUICK, control_backoff=Backoff([0.05, 0.05]))
    m.ports = lambda: []
    await m.start(replace(HF, mercury_tx_gain_db=5), attach=station.url)
    try:
        await until(lambda: m.state == "running")
        await m.tune()
        await until(lambda: station.tuned == ["TUNE -10"])                      # (-15 dBFS and the gain of 5 dB)
        m.set_tx_gain(8)
        await until(lambda: station.tuned == ["TUNE -10", "TUNE OFF", "TUNE -7"])
        assert m.test == "tune" and m.hold() == "the radio is transmitting", "the hold stays on while the tone is begun again"
        await asyncio.sleep(0.3)
        await until(lambda: m.test == "tune" and station.tuned[-1] == "TUNE -7")
        m.set_tx_gain(-30)
        await until(lambda: station.tuned[-1] == "TUNE -35")
        await m.tune_stop()
        await until(lambda: station.tuned[-1] == "TUNE OFF")
        assert m.test == ""
        count = len(station.tuned)
        m.set_tx_gain(0)
        await asyncio.sleep(0.2)
        assert len(station.tuned) == count, "no tone, nothing to move"
    finally:
        await m.stop()
        await air.aclose()


# ---- the automatic channel-busy control

def air(tmp_path: Path, blocks: list[list[float]] | None = None, noise_db: float = -60.0) -> None:
    """The air of the fake program's UI: noise at a level and bands lifted by so many dB."""
    (tmp_path / UI_SCENE_FILE).write_text(json.dumps({"blocks": blocks or [], "noise_db": noise_db}), encoding="utf-8")


async def test_the_channel_is_busy_by_the_spectrum_for_a_signal_as_wide_as_a_frame_and_not_for_a_carrier_or_a_step(tmp_path: Path) -> None:
    m = modem(tmp_path)
    await m.start(HF)
    try:
        await until(lambda: m.scope and m.state == "running", 10.0)
        await asyncio.sleep(3.0)
        assert not m.busy and m.hold() == "", "the fake program's air has a carrier at 1500 Hz 30 dB over the noise, which is a run of one band"
        air(tmp_path, [[1200, 1800, 12]])
        await until(lambda: m.busy and m.hold() == CHANNEL_BUSY, 10.0)
        assert m.describe().endswith("channel busy")
        air(tmp_path, [])
        await until(lambda: not m.busy, 10.0)
        air(tmp_path, [], noise_db=-35.0)
        await asyncio.sleep(4.0)
        assert not m.busy, "a step of 25 dB in the noise is no signal"
    finally:
        await m.stop()


async def test_the_spectrum_is_not_judged_while_the_radio_transmits_and_for_a_moment_after(tmp_path: Path) -> None:
    m = modem(tmp_path)
    await m.start(HF)
    try:
        await until(lambda: m.scope, 10.0)
        await asyncio.sleep(2.0)
        air(tmp_path, [[1200, 1800, 15]])
        m.keyed, m._keyed_at = True, time.monotonic()
        await asyncio.sleep(2.0)
        assert not m.busy and m.hold() == TRANSMITTING, "our own signal is no other station's"
        m.keyed = False
        m._keyed_at = time.monotonic()
        await asyncio.sleep(0.2)
        assert not m.busy, "the end of our own frame is still in the spectrum for a moment"
        await until(lambda: m.busy, 10.0)
    finally:
        m.keyed = False
        await m.stop()


def test_mercurys_own_busy_lines_are_the_state_only_while_the_spectrum_is_not_read() -> None:
    m = Mercury(Path("."))
    now = time.monotonic()
    m._on_busy(True, now)
    assert m.busy, "no spectrum: Mercury's detector is the channel's state"
    m.auto_busy(False, now)
    assert not m.busy, "the spectrum says it is clear: it wins"
    m._on_busy(False, now)
    m._on_busy(True, now)
    assert not m.busy and m._mercury_busy, "Mercury's lines are kept, not believed, while the spectrum is read"
    m.auto_busy(True, now)
    assert m.busy
    m.auto_lost(now)
    assert m.busy and m._mercury_busy, "the link is gone: Mercury's detector again"
    m._on_busy(False, now)
    assert not m.busy


def test_a_spectrum_that_stops_without_a_word_is_given_up_after_a_second() -> None:
    m = Mercury(Path("."))
    m._on_busy(False, time.monotonic())
    m.auto_busy(True, time.monotonic())
    assert m.hold() == CHANNEL_BUSY
    m._auto_at = time.monotonic() - 2.0
    assert m.hold() == "" and not m.busy and m._auto_at == 0.0, "its busy state is not believed once nothing feeds it: Mercury's (clear) is"


async def test_what_a_stopped_program_said_of_the_channel_holds_nothing_after_a_restart(tmp_path: Path) -> None:
    m = Mercury(tmp_path)
    now = time.monotonic()
    m.auto_busy(False, now)                 # the spectrum is read: clear
    m._on_busy(True, now)                   # Mercury's own detector says BUSY ON (a step in the noise): kept, not believed
    assert not m.busy
    await m.stop()                          # the settings were saved: the modem stops, and is started again
    m._auto_at -= 2.0                       # (were anything kept: the restart took over a second, the new link not yet up)
    assert m.hold() == "" and not m.busy, "the old program's BUSY does not hold the frames of the new one"
