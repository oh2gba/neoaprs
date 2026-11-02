"""The beacon interval the status tells the page (neoaprs/web/api.py): the one in force, which is the setting raised to the HF floor while the HF radio is on, not the number stored."""
from dataclasses import replace
from pathlib import Path

from tests.support.env import Env
from tests.support.fakemercury import Air


async def test_the_status_tells_the_interval_in_force_and_not_the_one_stored(tmp_path: Path) -> None:
    air = Air(frame_sec=0.2)
    await air.start()
    e = Env(tmp_path, web=True, radio=air.station(), settings={"beacon/interval_min": "20"})
    await e.start()
    assert e.server is not None
    assert (await e.server.api.status())["beacon_interval_min"] == 30, "20 stored, 30 at the least while the HF radio is on"
    await e.ctl.change_config(lambda c: replace(c, beacon_interval_min=60))
    assert (await e.server.api.status())["beacon_interval_min"] == 60
    await e.ctl.change_config(lambda c: replace(c, beacon_interval_min=0))
    assert (await e.server.api.status())["beacon_interval_min"] == 0, "Off stays Off"
    await e.stop()
    await air.aclose()
