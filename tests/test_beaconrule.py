"""The beacon with many radios (plan rule 3.1, neoaprs/beaconrule.py): one interval for the station, raised on each radio to that radio's own floor, so that the FM radio at 20 minutes beside an HF radio at
30 is not slowed to 30; each radio's own "beacon" tick (Send on), the last one never leaving the beacon on no radio (the main radio has it then), and with one radio on that one whatever its tick; a radio's
beacon whose tick is off sends nothing by its timer and refuses Beacon now, and is planned again at once when ticked; SmartBeaconing on the radio that has it and the timed beacon with the latest fix on the one
that has not; the raise said once in the log, for the radio it raises, a restart of the radio not saying it again; a stored Send on that is not true or false said once, not at every tick; and a save
through the controller that unticks the HF radio's Send on and ticks it again."""
import logging
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from neoaprs import beaconrule
from neoaprs.beaconrule import SETTING_MIN_MIN, beacon_interval, beacon_radios, floor_of, interval_words, station_interval, ticked
from neoaprs.config import DEFAULTS, MIN_BEACON_INTERVAL_MIN, Config
from neoaprs.radiospec import FM_ID, HF_ID, RadioSpec
from neoaprs.radiotypes import TYPES
from neoaprs.services.beacon import NOT_ON_THIS_RADIO, Beacon
from neoaprs.services.beaconframe import BeaconFrames
from neoaprs.web.beaconwire import BeaconNow
from neoaprs.web.handlers import beacon_now
from neoaprs.web.dispatch import UserError
from tests.support.clock import FixedClock
from tests.support.env import ON_AIR, Env, idle_for, until
from tests.support.fakedriver import registry_of, spec, with_radios
from tests.support.fakemercury import Air
from tests.support.gps import FakeFixes, fix_at
from tests.test_beaconframe import radio_of

POSITION = "=6010.20N/02456.40E-NeoAPRS"


def station(minutes: int, *radios: RadioSpec) -> Config:
    """The operator's station with these radios and this interval."""
    return with_radios(replace(ON_AIR, beacon_interval_min=minutes), radios)


OWN = (spec(1), spec(2, "hf"))            # John's: an FM radio and an HF radio, both on


# ---- the interval on each radio

def test_the_fm_radio_at_20_minutes_is_not_slowed_by_the_hf_radio_at_30() -> None:
    config = station(20, *OWN)
    assert [beacon_interval(20, s, config.radios) for s in config.radios] == [20, 30], "each radio its own floor"
    assert station_interval(20, config.radios, config.main_radio) == 20 and config.beacon_interval() == 20, "our position goes out every 20 minutes on some radio"
    assert interval_words(20, config.radios, config.main_radio) == "20 min on FM, 30 min on HF"
    assert [beacon_interval(45, s) for s in config.radios] == [45, 45] and [beacon_interval(0, s) for s in config.radios] == [0, 0], "a longer interval stays on both, Off stays Off"
    hf_alone = station(20, spec(1, enabled=False), spec(2, "hf"))
    assert station_interval(20, hf_alone.radios, hf_alone.main_radio) == 30 and interval_words(20, hf_alone.radios, hf_alone.main_radio) == "30 min", "the HF radio alone: raised"
    fm_alone = station(20, spec(1), spec(2, "hf", enabled=False))
    assert interval_words(25, fm_alone.radios, fm_alone.main_radio) == "25 min" and station_interval(25, fm_alone.radios, fm_alone.main_radio) == 25


def test_each_type_has_its_floor_and_only_a_floor_above_the_settings_own_raises() -> None:
    assert SETTING_MIN_MIN == MIN_BEACON_INTERVAL_MIN == 20 and min(t.limits.beacon_min_min for t in TYPES) == SETTING_MIN_MIN, "no type is floored below what the setting holds by itself"
    for t in TYPES:
        radio = spec(9, t.kind, t.key)
        assert floor_of(radio) == t.limits.beacon_min_min == (30 if t.kind == "hf" else 20), t.key
        assert beacon_interval(20, radio) == (30 if t.kind == "hf" else 20) and beacon_interval(90, radio) == 90 and beacon_interval(0, radio) == 0, t.key
    assert beacon_interval(1, spec(1)) == 1 and beacon_interval(1, spec(2, "hf")) == 30, "a Config made by hand below the setting's own minimum is the FM radio's as it is (the tests' quick beacons)"


def test_a_radio_of_a_type_that_is_none_takes_the_longest_floor_of_its_kind_or_of_every_type() -> None:
    assert floor_of(spec(5, "hf", "hf-of-tomorrow")) == 30 and floor_of(spec(6, "fm", "fm-of-tomorrow")) == 20
    assert floor_of(spec(7, "lora", "lora-of-tomorrow")) == max(t.limits.beacon_min_min for t in TYPES) == 30, "a kind with no type yet: the longest floor of all"
    assert beacon_interval(20, spec(7, "lora", "lora-of-tomorrow")) == 30


# ---- the radios it goes out on (Send on)

def test_the_beacon_goes_out_on_the_radios_that_are_ticked_and_on_and_with_every_tick_off_on_the_main_radio() -> None:
    assert beacon_radios(OWN, None) == (FM_ID, HF_ID), "ticked by default: both, as today"
    assert beacon_radios((spec(1), spec(2, "hf", beacon="false")), None) == (FM_ID,) and beacon_radios((spec(1, beacon="false"), spec(2, "hf")), None) == (HF_ID,)
    untick = (spec(1, beacon="false"), spec(2, "hf", beacon="false"), spec(3, beacon="false"))
    assert beacon_radios(untick, FM_ID) == (FM_ID,) and beacon_radios(untick, 3) == (3,), "the last tick is never off: with none ticked the main radio has the beacon"
    config = station(20, *untick)
    assert beacon_radios(config.radios, config.main_radio) == (FM_ID,), "the main radio of the settings: the first enabled"
    assert beacon_radios((spec(1, enabled=False), spec(2, "hf", beacon="false"), spec(3)), 2) == (3,), "a radio that is off is never one, ticked or not"
    assert beacon_radios((spec(1, enabled=False), spec(2, "hf", enabled=False)), None) == () and station_interval(20, (spec(1, enabled=False),), None) == 20, "no radio on: none, and the setting as it is"
    assert ticked(spec(1)) and not ticked(spec(1, beacon="false")) and ticked(spec(4, "lora", "lora-of-tomorrow")), "a kind with no type yet has the field's default"


def test_with_one_radio_on_the_beacon_goes_out_on_it_whatever_its_tick() -> None:
    for alone in ((spec(1, beacon="false"),), (spec(1, beacon="false"), spec(2, "hf", enabled=False)), (spec(1, enabled=False), spec(2, "hf", beacon="false"))):
        on = next(s.id for s in alone if s.enabled)
        assert beacon_radios(alone, None) == (on,)
        config = station(20, *alone)
        assert Beacon(radio_of(config, on), lambda config=config: config, FixedClock()).goes_out, "one radio: nothing changes"


async def test_a_radio_whose_send_on_is_not_ticked_sends_nothing_refuses_beacon_now_and_is_planned_at_once_when_ticked() -> None:
    clock = FixedClock()
    settings = {"now": station(20, spec(1), spec(2, "hf", beacon="false"))}
    frames = BeaconFrames(lambda: settings["now"], None, clock)
    fm, hf = (Beacon(radio_of(settings["now"], id), lambda: settings["now"], clock, frames=frames) for id in (FM_ID, HF_ID))
    for b in (fm, hf):
        await b.start()
    try:
        assert (fm.goes_out, hf.goes_out, fm.interval_min, hf.interval_min) == (True, False, 20, 0)
        assert fm.next_due is not None and hf.next_due is None, "its timer plans nothing"
        clock.advance(3600)
        hf._tick()
        assert hf.last_sent is None and not hf.radio.line.lines(), "and sends nothing when it ticks"   # type: ignore[attr-defined]
        assert not hf.send_now() and hf.problem == NOT_ON_THIS_RADIO and not hf.radio.line.lines(), "Beacon now goes on the ticked radios only"   # type: ignore[attr-defined]
        assert fm.send_now() and fm.radio.line.lines() == ["OH2GBA>APZNEO,WIDE2-2:" + POSITION]       # type: ignore[attr-defined]
        settings["now"] = station(20, spec(1), spec(2, "hf"))
        hf.settings_changed()
        assert hf.interval_min == 30 and hf.next_due == hf._started + timedelta(seconds=hf.first_delay_sec), "ticked again: planned at once, as a changed interval is"     # type: ignore[operator]
        assert hf.send_now() and hf.radio.line.lines() == ["OH2GBA>APZNEO:" + POSITION], "the HF radio direct"   # type: ignore[attr-defined]
    finally:
        for b in (fm, hf):
            await b.stop()


def test_smartbeaconing_goes_on_the_radio_that_has_it_and_the_other_sends_the_latest_fix_on_its_interval() -> None:
    clock = FixedClock()
    moving = replace(station(20, *OWN), gps_source="gpsd", station_symbol_code=">")
    gps = FakeFixes(fix_at(clock(), speed_kmh=54.0, course_deg=270))
    frames = BeaconFrames(lambda: moving, gps, clock)
    fm, hf = (Beacon(radio_of(moving, id), lambda: moving, clock, frames=frames) for id in (FM_ID, HF_ID))
    assert fm._mobile(moving) and not hf._mobile(moving) and hf.interval_min == 30, "one plan for the station's GPS, on the radio where SmartBeaconing is allowed; the HF radio's timed beacon at its floor"
    assert hf.send_now() and hf.radio.line.lines() == ["OH2GBA>APZNEO:=//w5#TW?M>eM[/A=000103NeoAPRS"], "the HF beacon by time carries the fix of now"    # type: ignore[attr-defined]
    assert hf.next_due is None and hf.mobile.last is None, "planned as a fixed station's (it is not started), not by SmartBeaconing"


async def test_the_raise_is_said_once_in_the_log_for_the_radio_it_raises(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.beacon")
    clock = FixedClock()
    config = station(20, *OWN)
    frames = BeaconFrames(lambda: config, None, clock)
    beacons = [Beacon(radio_of(config, id), lambda: config, clock, frames=frames) for id in (FM_ID, HF_ID)]
    for b in beacons:
        await b.start()
        b.settings_changed()
    hf = beacons[1]
    await hf.stop()
    await hf.start()                                        # (the HF radio restarted: its interval is the one it had)
    for b in beacons:
        await b.stop()
    raised = [r.getMessage() for r in caplog.records if "raised" in r.getMessage()]
    assert raised == ["the beacon interval 20 min is raised to 30 on the HF radio: 30 minutes is the shortest its type takes"], "once, for the HF radio alone, and not again when it restarts"


async def test_a_stored_send_on_that_is_not_true_or_false_is_said_once_and_not_at_every_tick(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs")
    clock = FixedClock()
    config = station(20, spec(1), spec(2, "hf", beacon="maybe"))          # (a row `db set` refuses: a newer program's, or a database restored or edited by hand)
    frames = BeaconFrames(lambda: config, None, clock)
    fm, hf = (Beacon(radio_of(config, id), lambda: config, clock, frames=frames) for id in (FM_ID, HF_ID))
    for b in (fm, hf):
        await b.start()
    try:
        for _ in range(60):
            clock.advance(1)
            fm._tick()
            hf._tick()
        assert hf.goes_out and hf.interval_min == 30 and beacon_radios(config.radios, config.main_radio) == (FM_ID, HF_ID), "the field's default: ticked, as today"
    finally:
        for b in (fm, hf):
            await b.stop()
    told = [r.getMessage() for r in caplog.records if "radio/2/beacon" in r.getMessage()]
    assert told == ["radio/2/beacon: 'maybe' is not true or false; the default true is used"], "said once, at the beacon's start"


async def test_a_save_that_unticks_the_hf_radios_send_on_stops_its_beacon_and_one_that_ticks_it_again_plans_it_at_once(tmp_path: Path) -> None:
    air = Air(frame_sec=0.2)
    await air.start()
    e = Env(tmp_path, hf=air.station(), settings={"beacon/interval_min": "20"})
    hf = e.ctl.hf_beacon
    hf.tick_sec = e.ctl.beacon.tick_sec = 0.02
    await e.start()

    def send_on(text: str) -> Config:
        c = e.ctl.config
        return with_radios(c, [replace(r, settings={**r.settings, "beacon": text}) if r.id == HF_ID else r for r in c.radios])

    try:
        await until(lambda: e.hf.usable and hf.running)
        started = hf._started
        assert (hf.interval_min, hf.next_due) == (30, started + timedelta(seconds=hf.first_delay_sec)) and e.ctl.beacon.interval_min == 20     # type: ignore[operator]
        assert await e.ctl.save_config(send_on("false"))
        assert e.ctl.config.radio(HF_ID).settings["beacon"] == "false" and (hf.goes_out, hf.interval_min, hf.next_due) == (False, 0, None), "the save stops its timer"     # type: ignore[union-attr]
        assert e.ctl.beacon.interval_min == 20 and e.ctl.beacon.next_due is not None, "the FM radio's goes on"
        e.now.advance(60)                                                       # type: ignore[attr-defined]
        await idle_for(0.15)
        assert hf.last_sent is None, "nothing on the HF radio"
        assert await e.ctl.save_config(send_on("true"))
        assert hf._started == started and hf.interval_min == 30, "ticked again by the save, the radio not restarted"
        await until(lambda: hf.last_sent is not None)                           # (planned at once: the first beacon was due a minute ago)
        assert hf.last_reason == "interval" and hf.next_due is not None and hf.next_due >= e.now() + timedelta(minutes=30)
    finally:
        await e.stop()
        await air.aclose()


async def test_beacon_now_of_the_page_goes_on_the_radios_the_registry_says_the_beacon_goes_out_on_and_on_no_other() -> None:
    """The page's Beacon now (web/handlers.py `beacon_now`) asks the registry's `beaconing`, not the flat tickboxes: with radios 1 and 2 on and ticked by the old keys but the beacon going out on radios 1
    and 3, it goes on 1 and 3; when none of them sends, the refusal is the first one's reason."""
    sent: list[str] = []

    class Stub:
        def __init__(self, name: str, goes: bool = True) -> None:
            self.name, self.goes, self.problem = name, goes, "" if goes else f"{name} is not connected"

        def send_now(self, reason: str) -> bool:
            sent.append(self.name)
            return self.goes

    fm, hf, third = Stub("fm"), Stub("hf"), Stub("third")
    ctl = SimpleNamespace(config=replace(DEFAULTS, hf_enabled=True), beacon=fm, hf_beacon=hf, radios=SimpleNamespace(beaconing=lambda: [SimpleNamespace(beacon=fm), SimpleNamespace(beacon=third)]))
    await beacon_now(SimpleNamespace(ctl=ctl), BeaconNow(cmd="beacon_now"))       # type: ignore[arg-type]
    assert sent == ["fm", "third"]
    quiet = Stub("third", goes=False)
    ctl.radios = SimpleNamespace(beaconing=lambda: [SimpleNamespace(beacon=quiet)])
    with pytest.raises(UserError, match="third is not connected"):
        await beacon_now(SimpleNamespace(ctl=ctl), BeaconNow(cmd="beacon_now"))   # type: ignore[arg-type]


# ---- which radios a save leaves the beacon on, at the registry

def test_beacon_now_goes_on_the_radios_whose_send_on_is_ticked() -> None:
    rig = registry_of(station(20, spec(1), spec(2, "hf", beacon="false"), spec(3)))
    assert [r.id for r in rig.registry.beaconing()] == [1, 3]
    rig.put(station(20, spec(1, beacon="false"), spec(2, "hf", beacon="false"), spec(3, beacon="false")))
    assert [r.id for r in rig.registry.beaconing()] == [1], "none ticked: the main radio"
    rig.put(station(20, spec(1, enabled=False), spec(2, "hf", beacon="false", enabled=False), spec(3, beacon="false")))
    assert [r.id for r in rig.registry.beaconing()] == [3], "one radio on: that one"
    assert beaconrule.beacon_radios(DEFAULTS.radios, DEFAULTS.main_radio) == (FM_ID,), "a new station of today's defaults: its FM radio"

