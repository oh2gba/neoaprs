"""Failing tests of suspected bugs in the HF scope, transmit gain and channel busy of 0.17.x (the bug hunt of 4 Nov 2026). Each fails on v0.17.4; not for merging as it is."""
import asyncio
import time
from pathlib import Path

from neoaprs.mercurymodem import CHANNEL_BUSY, Mercury
from neoaprs.mercuryui import MercuryUi
from neoaprs.channelbusy import OccupancyBusy
from tests.support.env import Env
from tests.support.fakemercury import Air
from tests.test_channelbusy import Air as BandAir, frame, first, STEP_SEC


async def test_stale_mercury_busy_survives_a_restart(tmp_path: Path) -> None:
    m = Mercury(tmp_path)
    now = time.monotonic()
    m.auto_busy(False, now)          # the spectrum is read: clear
    m._on_busy(True, now)            # Mercury's own detector says BUSY ON (a step in the noise), kept, not believed
    assert not m.busy
    await m.stop()                   # the settings were saved: the modem stops (and would start again)
    assert not m.busy
    m._auto_at -= 2.0                # the restart took over a second; the new link is not up yet
    assert m.hold() == "", f"after the restart frames are held: {m.hold()!r} busy={m.busy}"


async def test_two_picture_loops_after_off_on_in_one_tick(tmp_path: Path) -> None:
    m = Mercury(tmp_path)
    m._ui = MercuryUi("127.0.0.1", 9, lambda t: None, lambda b: None, lambda s: None)
    m._ui.connected = True
    m.want_scope(True)
    await asyncio.sleep(0.01)        # the loop is in its sleep
    m.want_scope(False)
    m.want_scope(True)               # (a page's off and on, two command tasks run in the same tick)
    await asyncio.sleep(0.01)
    loops = [t for t in m._tasks._tasks if t.get_name() == "mercury-scope" and not t.done()]
    try:
        assert m._scope_task is not None and len(loops) == 1, f"_scope_task={m._scope_task} loops={len(loops)}"
    finally:
        await m._tasks.cancel_all()


async def test_a_page_that_asks_and_leaves_in_one_go_is_kept_for_ever(tmp_path: Path) -> None:
    air = Air(frame_sec=0.2)
    station = air.station()
    e = Env(tmp_path, radio=station, web=True)
    await e.start()
    try:
        api = e.server.api

        class C:
            def send_json(self, text: str) -> None: pass
            def buffered(self) -> int: return 0
        c = C()
        api.attach(c)
        api.on_command(c, '{"cmd": "hf_scope", "on": true}')
        api.detach(c)                   # (the frame and the close came in one read)
        await asyncio.sleep(0.1)
        assert api.topics.scope.pages == 0 and not e.ctl.mercury._wanted, f"pages={api.topics.scope.pages} wanted={e.ctl.mercury._wanted}"
    finally:
        await e.stop()
        await air.aclose()


def test_a_steady_wide_signal_holds_the_channel_again_after_every_transmission() -> None:
    air, d = BandAir(seed=3), OccupancyBusy()
    air.run(d, 30.0)
    states = air.run(d, 600.0, frame(6.0))         # ten minutes of a steady 6 dB hump 600 Hz wide
    assert all(states[int(1 / STEP_SEC):]), "busy all along"
    d.pause()                                       # our frame went (the 20 s hold had given up)
    again = air.run(d, 2.0, frame(6.0))
    assert first(again) is None, f"busy again {first(again)} s after the transmission: the next frame waits another 20 s"


async def test_the_orphan_loop_doubles_after_the_link_comes_back(tmp_path: Path) -> None:
    m = Mercury(tmp_path)
    m._ui = MercuryUi("127.0.0.1", 9, lambda t: None, lambda b: None, lambda s: None)
    m._ui.connected = True
    m.want_scope(True)
    await asyncio.sleep(0.01)
    m.want_scope(False)
    m.want_scope(True)
    await asyncio.sleep(0.01)
    m._ui.connected = False
    m._ui_state(False)
    m._ui.connected = True
    m._ui_state(True)
    await asyncio.sleep(0.01)
    loops = [t for t in m._tasks._tasks if t.get_name() == "mercury-scope" and not t.done()]
    try:
        assert len(loops) == 1, f"{len(loops)} picture loops"
    finally:
        await m._tasks.cancel_all()
