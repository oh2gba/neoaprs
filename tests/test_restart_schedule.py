"""The beacon and the status report keep their schedule across a restart (neoaprs/services/memory.py): the rows `beacon/last_sent_at`, `status/last_sent_at` and `status/last_text` of a real Store on a
temporary database, a clock the test holds, a Tnc that is a stub. A second Beacon or RigStatus on the same Store is the daemon started again."""
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from neoaprs.clock import iso
from neoaprs.config import DEFAULTS, STATE_KEYS, Config
from neoaprs.rigctld import read_rig
from neoaprs.services.beacon import Beacon
from neoaprs.services.rigstatus import RigStatus
from neoaprs.store import Store
from tests.support.stubtnc import StubTnc
from tests.support.clock import FixedClock
from tests.support.env import Env, idle_for, ON_AIR, remember_stop, until
from tests.support.fakes import FakeRigctld, rigctld
from tests.support.storedb import store_at

BEACON_ROW, STATUS_ROW, TEXT_ROW = STATE_KEYS[:3]


class Daemon:
    """One run of the daemon's beacon and status: made again on the same Store and clock after a stop."""

    def __init__(self, store: Store, clock: FixedClock, **changes: object) -> None:
        self.config: Config = replace(ON_AIR, **{"beacon_interval_min": 30, **changes})             # type: ignore[arg-type]   (on: the defaults are a beacon that is off)
        self.tnc = StubTnc()
        self.beacon = Beacon(self.tnc, lambda: self.config, clock, first_delay_sec=30.0, tick_sec=0.01, memory=store)
        self.status = RigStatus(self.tnc, lambda: self.config, self.beacon, clock, poll_sec=0.01, read=lambda host, port: read_rig(host, port, 0.3), memory=store)
        remember_stop(self.beacon.stop)
        remember_stop(self.status.stop)

    async def stop(self) -> None:
        await self.status.stop()
        await self.beacon.stop()

    def infos(self) -> list[bytes]:
        return [f.info for f in self.tnc.sent]

    def reports(self) -> list[bytes]:
        return [i for i in self.infos() if i.startswith(b">")]


async def quiet() -> None:
    await idle_for(0.15)


async def kept(tmp_path: Path) -> tuple[Store, FixedClock]:
    clock = FixedClock()
    return await store_at(tmp_path / "neoaprs.sqlite", clock), clock


async def beacon_sent_ago(store: Store, clock: FixedClock, minutes: float) -> None:
    assert await store.put_setting(BEACON_ROW, iso(clock() - timedelta(minutes=minutes)) or "")


# ---- the beacon ----------------------------------------------------------------------------------------------------------------------------------

async def test_the_time_of_each_beacon_is_written_to_the_row_after_the_send(tmp_path: Path) -> None:
    store, clock = await kept(tmp_path)
    d = Daemon(store, clock, beacon_interval_min=60, status_interval_min=60)
    assert await store.setting(BEACON_ROW) is None
    await d.beacon.start()
    clock.advance(30)
    await until(lambda: len(d.infos()) == 1)
    clock.advance(100)
    assert d.beacon.send_now()
    await d.beacon.stop()
    assert await store.setting(BEACON_ROW) == "2026-10-21T12:02:10Z", "the latest send, whether the timer's or a request"
    assert BEACON_ROW not in DEFAULTS.to_data(), "state, not a setting"


async def test_a_start_ten_minutes_after_a_beacon_with_an_hour_interval_sends_the_first_fifty_minutes_later(tmp_path: Path) -> None:
    store, clock = await kept(tmp_path)
    await beacon_sent_ago(store, clock, 10)
    d = Daemon(store, clock, beacon_interval_min=60)
    await d.beacon.start()
    assert d.beacon.next_due == clock() + timedelta(minutes=50)
    clock.advance(30)
    await quiet()
    assert d.infos() == [], "not thirty seconds after the start"
    clock.advance(49 * 60 + 29)
    await quiet()
    assert d.infos() == []
    clock.advance(1)
    await until(lambda: len(d.infos()) == 1)
    await d.stop()


@pytest.mark.parametrize("minutes_ago", [120, None], ids=["two hours after a beacon", "no stored time"])
async def test_a_start_two_hours_after_a_beacon_or_with_no_stored_time_sends_the_first_at_thirty_seconds(tmp_path: Path, minutes_ago: int | None) -> None:
    store, clock = await kept(tmp_path)
    if minutes_ago is not None:
        await beacon_sent_ago(store, clock, minutes_ago)
    d = Daemon(store, clock, beacon_interval_min=60)
    await d.beacon.start()
    assert d.beacon.next_due == clock() + timedelta(seconds=30)
    clock.advance(30)
    await until(lambda: len(d.infos()) == 1)
    await d.stop()


async def test_a_stored_time_that_is_not_a_time_or_is_in_the_future_counts_as_none(tmp_path: Path) -> None:
    store, clock = await kept(tmp_path)
    for text in ("yesterday", "2026-10-21T13:00:00Z", "2026-10-21T10:00:00"):          # (not a time; ahead of the clock; no zone)
        assert await store.put_setting(BEACON_ROW, text)
        d = Daemon(store, clock, beacon_interval_min=60)
        await d.beacon.start()
        assert d.beacon.next_due == clock() + timedelta(seconds=30), text
        await d.stop()


async def test_a_beacon_on_request_moves_the_schedule_as_before_and_is_remembered(tmp_path: Path) -> None:
    store, clock = await kept(tmp_path)
    await beacon_sent_ago(store, clock, 10)
    d = Daemon(store, clock, beacon_interval_min=60)
    await d.beacon.start()
    clock.advance(60)
    assert d.beacon.send_now()
    assert d.beacon.next_due == clock() + timedelta(minutes=60)
    await d.stop()
    assert await store.setting(BEACON_ROW) == "2026-10-21T12:01:00Z"


async def test_a_changed_interval_is_planned_again_from_the_stored_time(tmp_path: Path) -> None:
    store, clock = await kept(tmp_path)
    await beacon_sent_ago(store, clock, 10)
    d = Daemon(store, clock, beacon_interval_min=60)
    await d.beacon.start()
    d.config = replace(d.config, beacon_interval_min=15)
    d.beacon.settings_changed()
    assert d.beacon.next_due == clock() + timedelta(minutes=5), "ten minutes after the stored one, an interval of fifteen: five minutes from now"
    d.config = replace(d.config, beacon_interval_min=5)
    d.beacon.settings_changed()
    assert d.beacon.next_due == clock() + timedelta(seconds=30), "the stored one plus five minutes passed before the start: thirty seconds after the start"
    await d.stop()


async def test_a_beacon_with_the_interval_at_zero_stays_off_whatever_is_stored(tmp_path: Path) -> None:
    store, clock = await kept(tmp_path)
    await beacon_sent_ago(store, clock, 10)
    d = Daemon(store, clock, beacon_interval_min=0)
    await d.beacon.start()
    assert d.beacon.next_due is None
    await d.stop()


# ---- the status ----------------------------------------------------------------------------------------------------------------------------------

async def first_run(store: Store, clock: FixedClock, **changes: object) -> Daemon:
    """A run that sends its status and is stopped, so that the rows are written."""
    d = Daemon(store, clock, **changes)
    await d.status.start()
    await until(lambda: len(d.reports()) == 1)
    await d.stop()
    return d


async def test_the_time_and_the_text_of_a_status_are_written_to_the_rows_after_the_send(tmp_path: Path) -> None:
    store, clock = await kept(tmp_path)
    assert await store.setting(STATUS_ROW) is None and await store.setting(TEXT_ROW) is None
    await first_run(store, clock, station_status="QRV 145.500")
    assert await store.setting(STATUS_ROW) == "2026-10-21T12:00:00Z" and await store.setting(TEXT_ROW) == "QRV 145.500"
    assert not set(STATE_KEYS) & set(DEFAULTS.to_data()) and Config.from_data(await store.settings()) == DEFAULTS, "state, not settings: the form does not list them and reading the settings leaves them alone"


async def test_a_restart_inside_the_interval_sends_no_status_even_when_the_text_differs(tmp_path: Path) -> None:
    store, clock = await kept(tmp_path)
    await first_run(store, clock, station_status="QRV 145.500", status_interval_min=30)
    clock.advance(10 * 60)
    d = Daemon(store, clock, station_status="At the cottage", status_interval_min=30)
    await d.status.start()
    await quiet()
    assert d.tnc.sent == [] and d.status.last_text == "QRV 145.500" and d.status.last_sent_at == clock() - timedelta(minutes=10)
    await d.stop()


async def test_a_restart_after_the_interval_sends_no_status_when_the_text_is_the_same(tmp_path: Path) -> None:
    store, clock = await kept(tmp_path)
    await first_run(store, clock, station_status="QRV 145.500", status_interval_min=30)
    clock.advance(31 * 60)
    d = Daemon(store, clock, station_status="QRV 145.500", status_interval_min=30)
    await d.status.start()
    await quiet()
    assert d.tnc.sent == []
    assert d.status.status_frame() is not None, "?APRSS still answers with the status that was kept"
    await d.stop()


async def test_a_restart_after_the_interval_sends_a_status_when_the_text_differs(tmp_path: Path) -> None:
    store, clock = await kept(tmp_path)
    await first_run(store, clock, station_status="QRV 145.500", status_interval_min=30)
    clock.advance(31 * 60)
    d = Daemon(store, clock, station_status="At the cottage", status_interval_min=30)
    await d.status.start()
    await until(lambda: len(d.reports()) == 1)
    assert d.reports()[0].endswith(b"At the cottage")
    await d.stop()
    assert await store.setting(TEXT_ROW) == "At the cottage" and await store.setting(STATUS_ROW) == "2026-10-21T12:31:00Z"


async def test_a_radio_status_after_a_restart_goes_out_only_when_the_frequency_or_the_mode_changed(tmp_path: Path) -> None:
    store, clock = await kept(tmp_path)
    rigd: FakeRigctld = await rigctld()
    await first_run(store, clock, status_rigctld=rigd.address, status_interval_min=30)
    assert await store.setting(TEXT_ROW) == "QRV 14.074 MHz USB"
    clock.advance(31 * 60)
    same = Daemon(store, clock, status_rigctld=rigd.address, status_interval_min=30)
    await same.status.start()
    await quiet()
    assert same.tnc.sent == [], "the same frequency and mode"
    await same.stop()
    rigd.hz = 7074000
    moved = Daemon(store, clock, status_rigctld=rigd.address, status_interval_min=30)
    await moved.status.start()
    await until(lambda: len(moved.reports()) == 1)
    assert moved.reports()[0].endswith(b"QRV 7.074 MHz USB")
    await moved.stop()


# ---- the whole daemon ----------------------------------------------------------------------------------------------------------------------------

async def test_a_daemon_started_again_inside_the_interval_plans_its_beacon_from_the_one_before(tmp_path: Path) -> None:
    first = Env(tmp_path)
    await first.start()
    assert await first.ctl.save_config(replace(first.ctl.config, beacon_interval_min=60))
    assert first.ctl.beacon.send_now()
    sent = first.now()
    await first.stop()
    clock = FixedClock(sent + timedelta(minutes=10))
    second = Env(tmp_path, clock=clock)
    await second.start()
    assert second.ctl.beacon.next_due == sent + timedelta(minutes=60)
    await second.stop()
