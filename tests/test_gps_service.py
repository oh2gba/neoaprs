"""The GPS service (neoaprs/services/gps.py) on the real feed and a fake gpsd, with a clock the test holds: the state of the GPS from `off` to `stale`, the fix to beacon with and the one to put our row at, `moved`
for the station book and the ALOHA circle, and the feed started again when the settings change."""
from datetime import timedelta

import pytest

from neoaprs.gpsfeed import GpsFeed
from neoaprs.services.gps import Gps
from neoaprs.source import Backoff, Source
from tests.support.env import idle_for, remember_stop, until
from tests.support.gps import fake_gpsd, fix_at, tpv
from tests.support.rig import ServiceRig


class Rig(ServiceRig):
    def __init__(self, **changes: object) -> None:
        super().__init__(**{"gps_source": "gpsd", **changes})
        self.feed = GpsFeed(self.clock, Backoff([0.05]), connect_sec=1.0)
        self.gps = Gps(self.feed, lambda: self.config, self.clock, tick_sec=0.01)
        self.feed.fixed.connect(self.gps.take)
        self.feed.changed.connect(self.gps.feed_changed)
        self.moved = 0
        self.gps.moved.connect(lambda: setattr(self, "moved", self.moved + 1))
        self.changes = 0
        self.gps.changed.connect(lambda: setattr(self, "changes", self.changes + 1))
        remember_stop(self.gps.stop)


def test_a_gps_that_is_off_is_off_and_has_no_fix_and_no_problem() -> None:
    rig = Rig(gps_source="off")
    assert (rig.gps.state, rig.gps.problem, rig.gps.current(), rig.gps.fix, rig.gps.fix_age_sec) == ("off", "", None, None, None)
    assert rig.gps.why_none() == "the GPS is off (gps/source)"


async def test_the_state_goes_from_connecting_to_no_fix_to_fix_to_stale() -> None:
    gpsd = await fake_gpsd()
    rig = Rig(gps_source="gpsd", gps_host=gpsd.address)
    assert rig.gps.state == "connecting" and rig.gps.why_none() == "waiting for the GPS"
    await rig.gps.start()
    await until(lambda: rig.feed.state is Source.State.CONNECTED and gpsd.watching)
    assert rig.gps.state == "no_fix" and rig.gps.problem == "the receiver has no position fix yet" and rig.gps.current() is None
    gpsd.send(tpv(60.43, 24.145, speed=15.0, track=270.0))
    await until(lambda: rig.gps.fix is not None)
    fix = rig.gps.fix
    assert rig.gps.state == "fix" and rig.gps.problem == "" and rig.gps.current() == fix and rig.gps.fix_age_sec == 0.0
    rig.clock.advance(120)
    assert rig.gps.state == "fix" and rig.gps.current() == fix, "120 seconds old is still fresh"
    rig.clock.advance(1)
    assert rig.gps.state == "stale" and rig.gps.current() is None and rig.gps.fix == fix
    assert rig.gps.problem == "the latest GPS fix is 121 s old" and rig.gps.why_none() == rig.gps.problem
    gpsd.send(tpv(60.44, 24.146))
    await until(lambda: rig.gps.state == "fix")


async def test_a_gpsd_that_is_not_there_is_connecting_with_the_reason() -> None:
    gpsd = await fake_gpsd()
    gpsd.hang_up()
    await gpsd.stop()
    rig = Rig(gps_source="gpsd", gps_host=gpsd.address)
    await rig.gps.start()
    await until(lambda: rig.feed.state is Source.State.WAITING)
    assert rig.gps.state == "connecting" and "refused" in rig.gps.problem.lower() and rig.gps.problem == rig.feed.problem


@pytest.mark.parametrize(("changes", "problem"), [
    ({"gps_source": "serial", "gps_device": ""}, "no port set: give gps/device the receiver's port"),
    ({"gps_source": "gpsd", "gps_host": ""}, "no address set: give gps/host the gpsd's host:port"),
])
async def test_a_source_without_its_port_or_address_is_connecting_and_says_what_to_give(changes: dict[str, str], problem: str) -> None:
    rig = Rig(**changes)
    await rig.gps.start()
    await until(lambda: rig.gps.problem == problem)
    assert rig.gps.state == "connecting" and rig.gps.why_none() == problem and rig.gps.current() is None
    assert rig.feed.state is Source.State.CONNECTING and not rig.feed._tasks


async def test_giving_the_port_after_the_source_starts_the_feed() -> None:
    rig = Rig(gps_source="serial", gps_device="")
    await rig.gps.start()
    await until(lambda: rig.gps.problem != "")
    gpsd = await fake_gpsd()
    rig.set(gps_source="gpsd", gps_host=gpsd.address)
    rig.gps.settings_changed()
    await until(lambda: rig.feed.state is Source.State.CONNECTED and gpsd.watching)
    assert rig.gps.state == "no_fix" and rig.feed.describe() == f"gpsd at {gpsd.address}"


async def test_a_stale_fix_tells_the_feeds_problem_too() -> None:
    gpsd = await fake_gpsd()
    rig = Rig(gps_source="gpsd", gps_host=gpsd.address)
    await rig.gps.start()
    await until(lambda: gpsd.watching)
    gpsd.send(tpv(60.43, 24.145))
    await until(lambda: rig.gps.fix is not None)
    rig.clock.advance(200)
    gpsd.send(tpv(None, None, mode=1))
    await until(lambda: rig.feed.problem != "")
    assert rig.gps.state == "stale" and rig.gps.problem == "the latest GPS fix is 200 s old (the receiver has no position fix yet)"


async def test_the_fix_to_put_our_row_at_is_the_latest_even_when_it_is_old_and_only_for_a_mobile_station() -> None:
    gpsd = await fake_gpsd()
    rig = Rig(gps_source="gpsd", gps_host=gpsd.address)
    await rig.gps.start()
    await until(lambda: gpsd.watching)
    gpsd.send(tpv(60.43, 24.145))
    await until(lambda: rig.gps.fix is not None)
    rig.clock.advance(3600)
    assert rig.gps.current() is None and rig.gps.mobile_fix() == rig.gps.fix
    rig.set(gps_source="off")
    assert rig.gps.mobile_fix() is None


async def test_changed_is_told_for_a_fix_and_for_a_fix_that_grows_old() -> None:
    gpsd = await fake_gpsd()
    rig = Rig(gps_source="gpsd", gps_host=gpsd.address)
    await rig.gps.start()
    await until(lambda: gpsd.watching)
    gpsd.send(tpv(60.43, 24.145))
    await until(lambda: rig.gps.state == "fix")
    seen = rig.changes
    rig.clock.advance(121)
    await until(lambda: rig.changes > seen)
    assert rig.gps.state == "stale"
    seen = rig.changes
    await idle_for(0.1)
    assert rig.changes == seen, "told when something changed, not at every tick"


# ---- moved

def test_our_row_follows_the_first_fix_then_after_five_seconds_and_ten_metres() -> None:
    rig = Rig()
    rig.gps.take(fix_at(rig.clock()))
    assert rig.moved == 1
    rig.clock.advance(10)
    rig.gps.take(fix_at(rig.clock(), lat=60.43002))                                  # 2 m
    assert rig.moved == 1, "far too near"
    rig.clock.advance(1)
    rig.gps.take(fix_at(rig.clock(), lat=60.4301))                                   # 11 m, 11 seconds after the row was put
    assert rig.moved == 2
    rig.clock.advance(2)
    rig.gps.take(fix_at(rig.clock(), lat=60.4310))                                   # 100 m but 2 seconds after
    assert rig.moved == 2, "not more often than every 5 seconds"
    rig.clock.advance(3)
    rig.gps.take(fix_at(rig.clock(), lat=60.4310))
    assert rig.moved == 3


def test_ten_metres_is_counted_from_where_the_row_was_put_not_from_the_last_fix() -> None:
    rig = Rig()
    rig.gps.take(fix_at(rig.clock()))
    for step in range(1, 12):
        rig.clock.advance(6)
        rig.gps.take(fix_at(rig.clock(), lat=60.43 + step * 0.00002))                 # 2.2 m a step
    assert rig.moved == 1 + 2, "at 11 m and at 22 m"


def test_our_row_does_not_follow_a_gps_while_the_beacon_is_not_mobile() -> None:
    rig = Rig(gps_source="off")
    rig.gps.take(fix_at(rig.clock()))
    rig.clock.advance(60)
    rig.gps.take(fix_at(rig.clock(), lat=61.0))
    assert rig.moved == 0 and rig.gps.fix is not None and rig.gps.mobile_fix() is None


# ---- the settings

async def test_a_change_of_the_source_starts_the_feed_afresh_and_forgets_the_fix() -> None:
    first, second = await fake_gpsd(), await fake_gpsd()
    rig = Rig(gps_source="gpsd", gps_host=first.address)
    await rig.gps.start()
    await until(lambda: first.watching)
    first.send(tpv(60.43, 24.145))
    await until(lambda: rig.gps.fix is not None)
    rig.set(gps_host=second.address)
    rig.gps.settings_changed()
    await until(lambda: second.watching and rig.feed.state is Source.State.CONNECTED)
    assert rig.gps.fix is None and rig.feed.target == second.address
    second.send(tpv(60.5, 24.2))
    await until(lambda: rig.gps.fix is not None)
    assert rig.gps.fix.lat == 60.5                                                      # type: ignore[union-attr]


async def test_a_gps_switched_off_stops_the_feed() -> None:
    gpsd = await fake_gpsd()
    rig = Rig(gps_source="gpsd", gps_host=gpsd.address)
    await rig.gps.start()
    await until(lambda: gpsd.watching)
    rig.set(gps_source="off")
    rig.gps.settings_changed()
    await until(lambda: rig.feed.state is Source.State.STOPPED)
    assert rig.gps.state == "off" and rig.gps.fix is None


async def test_the_serial_settings_are_what_the_feed_is_given() -> None:
    port = await fake_gpsd(greet=False)
    rig = Rig(gps_source="serial", gps_device=port.url, gps_baud=9600)
    await rig.gps.start()
    await until(lambda: rig.feed.state is Source.State.CONNECTED)
    assert (rig.feed.kind, rig.feed.target, rig.feed.baud) == ("serial", port.url, 9600)


async def test_a_change_of_another_setting_leaves_the_feed_alone() -> None:
    gpsd = await fake_gpsd()
    rig = Rig(gps_source="gpsd", gps_host=gpsd.address)
    await rig.gps.start()
    await until(lambda: gpsd.watching)
    rig.set(station_comment="x", beacon_travel="foot")
    rig.gps.settings_changed()
    await idle_for(0.1)
    assert gpsd.connections == 1


async def test_stop_ends_the_feed_and_the_tick() -> None:
    gpsd = await fake_gpsd()
    rig = Rig(gps_source="gpsd", gps_host=gpsd.address)
    await rig.gps.start()
    await until(lambda: gpsd.watching)
    await rig.gps.stop()
    assert rig.feed.state is Source.State.STOPPED and not rig.gps._tasks


def test_the_age_of_a_fix_is_counted_by_the_clock_of_the_program() -> None:
    rig = Rig(gps_source="gpsd")
    rig.gps.take(fix_at(rig.clock() - timedelta(seconds=100)))
    assert rig.gps.fix_age_sec == 100.0 and rig.gps.state == "fix"
    rig.clock.advance(30)
    assert rig.gps.state == "stale"
