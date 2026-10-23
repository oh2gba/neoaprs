"""The Controller (neoaprs/controller.py) as the composition root's object: the database opens at the start and closes at the stop, and what cannot be opened is refused with a reason."""
import asyncio
import sqlite3
from pathlib import Path

import pytest

from dataclasses import replace

from neoaprs.config import DEFAULTS, Config
from neoaprs.dberror import StoreError
from neoaprs.migrations import SCHEMA_VERSION
from neoaprs.source import Source
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.env import Env, until
from tests.support.ptyline import posix_only


async def test_the_start_makes_the_data_folder_and_the_database_and_the_stop_closes_it(tmp_path: Path) -> None:
    e = Env(tmp_path / "not" / "there" / "yet", operator=False)
    assert not e.ctl.running and e.ctl.db is None
    await e.start()
    assert e.ctl.running and e.ctl.db is not None and e.ctl.db.is_open and e.ctl.store.is_open()
    assert await e.ctl.store.put_setting("station/call", "OH2GBA") and (tmp_path / "not" / "there" / "yet" / DB_NAME).is_file()
    await e.stop()
    assert not e.ctl.running and not e.ctl.db.is_open and not e.ctl.store.is_open()


async def test_a_second_run_finds_what_the_first_kept(tmp_path: Path) -> None:
    first = Env(tmp_path, operator=False)
    await first.start()
    await first.ctl.store.put_setting("station/call", "OH2GBA")
    await first.stop()
    second = Env(tmp_path, operator=False)
    await second.start()
    assert await second.ctl.store.settings() == {"station/call": "OH2GBA"}
    await second.stop()


async def test_opening_again_and_stopping_again_are_harmless(tmp_path: Path) -> None:
    e = Env(tmp_path)
    await e.start()
    db = e.ctl.db
    await e.ctl.open_database()
    assert e.ctl.db is db
    await e.stop()
    await e.stop()


async def test_a_stop_without_a_start_is_harmless(tmp_path: Path) -> None:
    await Env(tmp_path).stop()


async def test_the_clock_of_the_controller_is_the_one_it_was_given(tmp_path: Path) -> None:
    clock = FixedClock()
    e = Env(tmp_path, clock)
    await e.start()
    assert e.ctl.clock is clock and e.ctl.store.now is clock
    await e.stop()


async def test_a_database_of_a_newer_version_is_refused_with_the_reason_and_leaves_no_thread(tmp_path: Path) -> None:
    db = sqlite3.connect(tmp_path / DB_NAME)
    db.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    db.close()
    e = Env(tmp_path)
    with pytest.raises(StoreError, match="newer NeoAPRS"):
        await e.start()
    assert e.ctl.db is None and not e.ctl.running
    await e.stop()


@pytest.mark.expects_errors
async def test_a_task_that_fails_is_told_in_the_log_and_the_stop_ends_the_rest(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    e = Env(tmp_path)
    await e.start()

    async def fails() -> None:
        raise RuntimeError("boom")

    async def waits() -> None:
        await asyncio.sleep(60)

    e.ctl.tasks.spawn(fails(), "fails")
    still = e.ctl.tasks.spawn(waits(), "waits")
    await asyncio.sleep(0.05)
    assert any("task fails failed" in r.getMessage() and "boom" in r.getMessage() for r in caplog.records)
    assert not still.done()
    await e.stop()
    assert still.cancelled() and len(e.ctl.tasks) == 0


async def test_the_start_reads_the_settings_and_puts_us_in_the_station_book(tmp_path: Path) -> None:
    first = Env(tmp_path, radio=False, operator=False)
    await first.start(connected=False)
    assert first.ctl.config == DEFAULTS
    await first.ctl.store.put_settings({"station/call": "oh2gba-7", "station/lat": "61.5", "station/lon": "25.5", "map/radius_km": "bad", "web/port": "8080", "web/allowed_hosts": "pi", "log/keep_days": "400", "update/check": "false"})
    await first.stop()
    second = Env(tmp_path, radio=False, operator=False)
    await second.start(connected=False)
    c = second.ctl.config
    assert (c.station_call, c.station_lat, c.station_lon, c.web_port, c.map_radius_km) == ("OH2GBA-7", 61.5, 25.5, 8080, 150), "a value that is wrong is the default"
    assert c.web_allowed_hosts == "pi", "the port and the hosts of the page are not on the page, and are settings all the same"
    me = second.ctl.stationbook.me
    assert me is not None and (me.call, me.lat, me.lon, me.is_me) == ("OH2GBA-7", 61.5, 25.5, True)
    await second.stop()


@posix_only
async def test_the_start_does_not_wait_for_the_search_and_the_stop_ends_it(tmp_path: Path) -> None:
    e = Env(tmp_path, radio=False, probe_seconds=30.0)
    e.new_pty("probe_1")                                          # a radio that says nothing: the search listens for the whole 30 seconds
    began = asyncio.get_running_loop().time()
    await e.start(connected=False)
    assert asyncio.get_running_loop().time() - began < 2.0 and e.ctl.running
    await until(lambda: e.tnc.state is Source.State.CONNECTING)
    await e.stop()
    assert asyncio.get_running_loop().time() - began < 5.0 and e.tnc.state is Source.State.STOPPED and len(e.ctl.tasks) == 0 and len(e.tnc._tasks) == 0


async def test_the_stop_ends_the_radio_the_tasks_and_the_database(tmp_path: Path) -> None:
    e = Env(tmp_path)
    await e.start()
    assert e.tnc.state is Source.State.CONNECTED and {t.get_name() for t in e.ctl.tasks} >= {"prune"}
    await e.stop()
    assert e.tnc.state is Source.State.STOPPED and len(e.ctl.tasks) == 0 and e.ctl.db is not None and not e.ctl.db.is_open and not e.ctl.packetlog.is_open()


async def test_the_settings_are_stored_and_read_back_by_the_next_run(tmp_path: Path) -> None:
    e = Env(tmp_path, radio=False)
    await e.start(connected=False)
    new = replace(e.ctl.config, station_comment="mobile", beacon_interval_min=10)
    assert await e.ctl.save_config(new) and e.ctl.config is new
    assert (await e.ctl.store.settings())["beacon/interval_min"] == "10" and Config.from_data(await e.ctl.store.settings()) == new
    await e.stop()
    assert not await e.ctl.save_config(replace(new, beacon_interval_min=0)), "the database is closed: nothing is stored"
    assert e.ctl.config is new
