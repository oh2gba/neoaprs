"""The one maker of the station's frames (neoaprs/services/beaconframe.py) for any radio, the radios as the registry gives them (`support/seamshapes.py` over stub lines): the position and the status the
same on every radio but for what the radio decides (its own path where it may carry one, the cut to its frame, said once for each radio), the position field of the iGate that asks no interlock, a moving
station's fix on every radio; a radio of the old shape read as one of the registry's and making the same frames; one maker shared by the beacons of the radios and the status report; the timer of a radio
of any id with the interval of neoaprs/beaconrule.py and its last send in the radio's own row."""
import logging
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

import pytest

from neoaprs import ax25
from neoaprs.config import BEACON_SENT, HF_BEACON_SENT, Config
from neoaprs.radiospec import FM_ID, HF_ID, RadioId, RadioSpec
from neoaprs.radiotypes.common import FM_ALLOWED, FM_LIMITS, HF_LIMITS
from neoaprs.services.beacon import Beacon, memory_key_of
from neoaprs.services.beaconframe import BeaconError, BeaconFrames, NoFix, OldLine, air_of
from neoaprs.services.radioset import AirRadio, fit
from neoaprs.services.rigstatus import RigStatus
from neoaprs.tncwatchdog import TncStats
from tests.support.clock import FixedClock
from tests.support.env import ON_AIR
from tests.support.gps import FakeFixes, fix_at
from tests.support.seamshapes import FrozenAir, LiveShape, RegistryShape, frozen_air
from tests.support.stubtnc import HF_WITH_PATHS, StubTnc

BOTH = replace(ON_AIR, hf_enabled=True, station_comment="NeoAPRS")
POSITION = b"=6010.20N/02456.40E-NeoAPRS"


def radio_of(config: Config, id: RadioId, line: StubTnc | None = None) -> LiveShape:
    """Radio `id` of the settings as the registry gives it: its kind, limits and choices from its spec, the rest from a stub line."""
    spec = config.radio(id)
    assert spec is not None
    return LiveShape(spec, config.radios, line if line is not None else StubTnc(max_frame=123 if spec.kind == "hf" else None))       # type: ignore[arg-type]  # (a stub, not a Tnc)


def with_radios(config: Config, *specs: RadioSpec) -> Config:
    """The settings with these radios (any number, any ids), as they are stored."""
    return replace(config, radios=specs)


def third(path: str = "WIDE2-1", kind: str = "fm", type: str = "kiss", enabled: bool = True) -> RadioSpec:
    return RadioSpec(3, kind, type, "", enabled, 3, settings={"path": path} if kind == "fm" else {})        # type: ignore[arg-type]


def capped_with_paths(spec: RadioSpec) -> FrozenAir:
    """A radio with a frame cap that carries paths (no type has both: over HF itself no path goes)."""
    air = frozen_air(spec)
    return replace(air, limits=replace(air.limits, max_frame=123), allowed=replace(air.allowed, paths=True))


# ---- the position and the status for any radio

def test_the_position_is_the_same_on_every_radio_but_the_path_which_the_radio_decides() -> None:
    frames = BeaconFrames(lambda: BOTH, None, FixedClock())
    fm, hf = frames.position(radio_of(BOTH, FM_ID)), frames.position(radio_of(BOTH, HF_ID))
    assert fm.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:" + POSITION.decode()
    assert hf.tnc2() == "OH2GBA>APZNEO:" + POSITION.decode(), "HF carries no path, whatever beacon/path says"
    assert fm.info == hf.info and fm.source == hf.source and fm.destination == hf.destination


@pytest.mark.parametrize(("path", "frame_path"), [("WIDE2-1", "WIDE2-1"), ("DIRECT", ""), ("", "WIDE2-2")])
def test_a_third_radio_goes_by_its_own_path_not_the_stations(path: str, frame_path: str) -> None:
    config = with_radios(replace(BOTH), *BOTH.radios, third(path))
    frames = BeaconFrames(lambda: config, None, FixedClock())
    radio = radio_of(config, 3)
    assert radio.name == "FM 2" and frames.position(radio).path_text == frame_path, "an empty path is the recommended one of the symbol, DIRECT none"
    assert frames.position(radio_of(config, FM_ID)).path_text == "WIDE1-1,WIDE2-1", "radio 1 keeps beacon/path"
    status = frames.status("QRV", radio)
    assert status is not None and status.path_text == frame_path


def test_the_status_is_the_text_with_its_time_on_any_radio_by_that_radios_path() -> None:
    clock = FixedClock()
    frames = BeaconFrames(lambda: BOTH, None, clock)
    fm, hf = frames.status("QRV 145.500", radio_of(BOTH, FM_ID)), frames.status("QRV 145.500", radio_of(BOTH, HF_ID))
    assert fm is not None and fm.tnc2() == "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:>211200zQRV 145.500"
    assert hf is not None and hf.tnc2() == "OH2GBA>APZNEO:>211200zQRV 145.500"
    assert frames.status("", radio_of(BOTH, HF_ID)) is None
    with pytest.raises(BeaconError, match="56 characters"):
        frames.status("x" * 56, radio_of(BOTH, HF_ID))


def test_the_comment_is_cut_to_each_radios_frame_and_each_cut_is_said_once_for_that_radio(caplog: pytest.LogCaptureFixture) -> None:
    long = replace(BOTH, station_comment="A comment as long as the settings allow, 43", beacon_path="WIDE1-1,WIDE2-1,WIDE3-1,WIDE4-1,WIDE5-1,WIDE6-1,WIDE7-1")
    frames = BeaconFrames(lambda: long, None, FixedClock())
    capped, other = capped_with_paths(long.radios[0]), replace(capped_with_paths(long.radios[0]), id=4)
    cut = frames.position(capped)
    assert len(ax25.encode(cut)) == 123 and cut.info == b"=6010.20N/02456.40E-A comment as long as the settings allo"
    frames.position(capped)
    assert frames.position(other) == cut
    told = [r.getMessage() for r in caplog.records if "its comment is cut" in r.getMessage()]
    assert len(told) == 2 and all("more than the radio carries (123): its comment is cut to 'A comment as long as the settings allo'" in t for t in told), "once for each radio, not once for each frame"
    assert len(ax25.encode(frames.position(radio_of(long, FM_ID)))) > 123, "a radio with no cap sends it whole"


def test_a_radio_that_may_carry_no_path_gets_none_and_a_frame_that_does_not_fit_even_without_its_comment_is_refused() -> None:
    frames = BeaconFrames(lambda: BOTH, None, FixedClock())
    assert frames.frame_for(radio_of(BOTH, HF_ID), b">" + b"x" * 100).path == ()
    with pytest.raises(BeaconError, match="more than the 256"):
        frames.frame_for(radio_of(BOTH, FM_ID), b"=" + b"x" * 256)
    with pytest.raises(BeaconError, match="shortening its comment is not enough"):
        frames.frame_for(radio_of(BOTH, HF_ID), b"T#005," + b"1," * 60)


def test_the_settings_that_make_no_frame_make_none_on_any_radio() -> None:
    for changes in ({"station_call": ""}, {"station_lat": None}, {"station_symbol_code": " "}, {"station_comment": "x" * 44}):
        config = replace(BOTH, **changes)                                                       # type: ignore[arg-type]
        frames = BeaconFrames(lambda c=config: c, None, FixedClock())                           # type: ignore[misc]
        for id in (FM_ID, HF_ID):
            with pytest.raises(BeaconError):
                frames.position(radio_of(config, id))


# ---- the position field of the iGate

def test_the_position_field_is_the_positions_information_field_and_asks_only_for_a_call() -> None:
    rx_only = replace(BOTH, station_transmit=False)
    frames = BeaconFrames(lambda: rx_only, None, FixedClock())
    assert frames.position_info() == POSITION, "nothing is transmitted: receive only makes it all the same"
    with pytest.raises(BeaconError):
        frames.position(radio_of(rx_only, FM_ID))
    with pytest.raises(BeaconError):
        BeaconFrames(lambda: replace(BOTH, station_call="NOCALL!"), None, FixedClock()).position_info()


def test_a_moving_stations_frame_is_the_fix_on_every_radio_and_nothing_without_one() -> None:
    clock = FixedClock()
    moving = replace(BOTH, gps_source="gpsd", station_symbol_code=">")
    gps = FakeFixes(fix_at(clock(), speed_kmh=54.0, course_deg=270))
    frames = BeaconFrames(lambda: moving, gps, clock)
    fm, hf = frames.position_and_fix(radio_of(moving, FM_ID)), frames.position_and_fix(radio_of(moving, HF_ID))
    assert fm[0].info == hf[0].info == frames.position_info() == b"=//w5#TW?M>eM[/A=000103NeoAPRS" and fm[1] is hf[1] is gps.fix, "the HF radio, with no SmartBeaconing, sends the same fix by time"
    gps.fix = None
    with pytest.raises(NoFix, match="no position fix"):
        frames.position(radio_of(moving, HF_ID))
    with pytest.raises(NoFix, match="no GPS is set up"):
        BeaconFrames(lambda: moving, None, clock).position_info()


# ---- the old shape

def test_a_radio_of_the_old_shape_is_read_as_the_registrys_radio_of_its_kind() -> None:
    fm, hf, capped = (air_of(line, lambda: BOTH, old=True) for line in (StubTnc(), StubTnc(max_frame=123), StubTnc(max_frame=123, rtype=HF_WITH_PATHS)))
    assert isinstance(fm, OldLine) and (fm.id, fm.kind, fm.name, fm.max_frame, fm.allowed, fm.limits) == (FM_ID, "fm", "FM", None, BOTH.radios[0].rtype.allowed, BOTH.radios[0].rtype.limits)
    assert (hf.id, hf.kind, hf.name, hf.max_frame, hf.allowed.paths, hf.limits.beacon_jitter_sec) == (HF_ID, "hf", "HF", 123, False, 300)
    assert capped.allowed.paths and capped.choice("path") == "WIDE1-1,WIDE2-1", "an HF radio that carries paths has radio 1's, for its kind has none"
    live = radio_of(BOTH, HF_ID)
    assert air_of(live, lambda: BOTH) is live and air_of(live, lambda: BOTH, old=True) is live, "a radio of the registry is itself"


class BothShapes(StubTnc):
    """A stub line that is also a radio of the registry's shape with choices of its own (as a test's stub may be): its path is the recommended one, not the station's beacon/path."""
    id, kind, name, limits, allowed = FM_ID, "fm", "FM", FM_LIMITS, FM_ALLOWED
    stats = TncStats()

    def choice(self, key: str) -> Any:
        return {"beacon": True, "path": "", "digipeat": False}[key]


class OnePick:
    """The registry's choice of a radio with this one radio in it."""
    def __init__(self, radio: AirRadio) -> None:
        self.main = radio

    def get(self, id: RadioId) -> AirRadio | None:
        return self.main if id == self.main.id else None

    def email(self) -> AirRadio | None:
        return self.main


async def test_a_radio_of_both_shapes_is_read_by_the_call_the_old_one_by_the_stations_path_the_new_one_by_its_own() -> None:
    clock, line = FixedClock(), BothShapes()
    old, new = Beacon(line, lambda: BOTH, clock), Beacon(line, lambda: BOTH, clock, frames=BeaconFrames(lambda: BOTH, None, clock))
    assert isinstance(old.radio, OldLine) and new.radio is line
    assert old.frame().path_text == old.frame(line).path_text == "WIDE1-1,WIDE2-1", "the old call: the station's beacon/path, as the beacon always read it"
    assert new.frame().path_text == new.frame(line).path_text == "WIDE2-2", "the new call: the radio's own choice, empty the recommended path"
    for status, path in ((RigStatus(line, lambda: BOTH, old, clock), "WIDE1-1,WIDE2-1"), (RigStatus(OnePick(line), lambda: BOTH, old, clock), "WIDE1-1,WIDE2-1"),
                         (RigStatus(OnePick(line), lambda: BOTH, new.frames, clock), "WIDE2-2")):
        status.last_text = "QRV"
        answer = status.status_frame(line)
        assert answer is not None and answer.path_text == path
    assert await RigStatus(line, lambda: replace(BOTH, station_status="QRV"), old, clock).send_now() == "" and line.sent[-1].path_text == "WIDE1-1,WIDE2-1"


@pytest.mark.parametrize("id", [FM_ID, HF_ID])
def test_a_radio_of_the_old_shape_makes_the_frames_its_radio_of_the_registry_makes(id: RadioId) -> None:
    line = StubTnc(max_frame=123 if id == HF_ID else None)
    frames = BeaconFrames(lambda: BOTH, None, FixedClock())
    old, new = air_of(line, lambda: BOTH, old=True), radio_of(BOTH, id, line)
    assert frames.position(old) == frames.position(new) and frames.status("QRV", old) == frames.status("QRV", new)
    assert Beacon(line, lambda: BOTH, FixedClock()).frame() == frames.position(new), "the old call of the beacon makes the same frame"
    assert old.send_frame(frames.position(old)) and line.sent == [frames.position(new)] and old.usable and old.why_unusable() == ""


# ---- one maker for every radio

def test_the_beacons_of_the_radios_and_the_status_report_share_the_one_maker() -> None:
    clock = FixedClock()
    frames = BeaconFrames(lambda: BOTH, None, clock)
    fm, hf = Beacon(radio_of(BOTH, FM_ID), lambda: BOTH, clock, frames=frames), Beacon(radio_of(BOTH, HF_ID), lambda: BOTH, clock, frames=frames)
    status = RigStatus(RegistryShape([fm.radio, hf.radio]), lambda: BOTH, fm, clock)            # type: ignore[list-item]
    assert fm.frames is hf.frames is status.frames is frames
    assert (fm.radio.id, hf.radio.id) == (FM_ID, HF_ID)
    assert fm.frame() == frames.position(fm.radio) and hf.frame() == frames.position(hf.radio) and fm.frame(hf.radio) == hf.frame(), "a beacon's frame for another radio is that radio's"
    assert fm.position_info() == frames.position_info() and fm.status_frame("QRV", hf.radio) == frames.status("QRV", hf.radio)
    assert Beacon(StubTnc(), lambda: BOTH, clock).frames is not frames, "a beacon made the old way has its own"


def test_the_one_fit_function_and_the_beacons_maker_make_the_same_frame_where_nothing_is_cut() -> None:
    frames = BeaconFrames(lambda: BOTH, None, FixedClock())
    for id in (FM_ID, HF_ID):
        radio: AirRadio = radio_of(BOTH, id)
        assert frames.position(radio) == fit(radio, BOTH, POSITION, None), "the radio's path where it may carry one, by the same rule as every frame of ours"


# ---- the timer of any radio

def test_the_interval_of_a_radios_beacon_is_the_beacon_rule_s_for_that_radio() -> None:
    clock = FixedClock()
    fm_only = with_radios(replace(BOTH, beacon_interval_min=20), replace(BOTH.radios[0]), replace(BOTH.radios[1], enabled=False), third())
    with_hf = with_radios(replace(BOTH, beacon_interval_min=20), *BOTH.radios, third())
    off = with_radios(replace(BOTH, beacon_interval_min=0), *BOTH.radios, third())
    assert Beacon(radio_of(fm_only, 3), lambda: fm_only, clock).interval_min == 20
    assert Beacon(radio_of(with_hf, 3), lambda: with_hf, clock).interval_min == Beacon(radio_of(with_hf, FM_ID), lambda: with_hf, clock).interval_min == 20, "an FM radio is not slowed by an HF radio that is on (plan rule 3.1)"
    assert Beacon(radio_of(with_hf, HF_ID), lambda: with_hf, clock).interval_min == HF_LIMITS.beacon_min_min == 30, "the HF radio is raised to its own floor"
    assert Beacon(radio_of(off, 3), lambda: off, clock).interval_min == 0, "Off stays Off"
    gone, without = radio_of(with_hf, 3), replace(BOTH, beacon_interval_min=20)
    assert Beacon(gone, lambda: without, clock).interval_min == 0, "a radio the settings do not have sends no timed beacon"


def test_each_radio_keeps_its_last_beacon_in_its_own_row() -> None:
    assert (memory_key_of(FM_ID), memory_key_of(HF_ID), memory_key_of(3)) == ("radio/1/beacon_last_sent_at", "radio/2/beacon_last_sent_at", "radio/3/beacon_last_sent_at"), "the rows of before are none of them"
    assert {BEACON_SENT, HF_BEACON_SENT}.isdisjoint({memory_key_of(FM_ID), memory_key_of(HF_ID)}), "migration 31 renamed today's two rows"


class Rows:
    """The rows of the settings table as a dict (services/memory.Memory)."""
    def __init__(self, **rows: str) -> None:
        self.rows = dict(rows)

    async def setting(self, key: str) -> str | None:
        return self.rows.get(key)

    async def put_settings(self, data: dict[str, str]) -> bool:
        self.rows.update(data)
        return True


async def test_a_third_radios_beacon_sends_on_its_radio_by_its_path_and_remembers_it_in_its_row(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, "neoaprs.beacon")
    clock = FixedClock()
    config = with_radios(replace(BOTH, hf_enabled=False, beacon_interval_min=20), BOTH.radios[0], replace(BOTH.radios[1], enabled=False), third("WIDE2-1"))
    earlier = clock() - timedelta(minutes=5)
    rows = Rows(**{"radio/3/beacon_last_sent_at": earlier.strftime("%Y-%m-%dT%H:%M:%SZ"), memory_key_of(FM_ID): "2000-01-01T00:00:00Z"})
    line = StubTnc()
    beacon = Beacon(radio_of(config, 3, line), lambda: config, clock, memory=rows, frames=BeaconFrames(lambda: config, None, clock))
    await beacon.start()
    try:
        assert beacon.next_due == earlier + timedelta(minutes=20), "its own row, not radio 1's"
        assert beacon.send_now() and line.lines() == ["OH2GBA>APZNEO,WIDE2-1:" + POSITION.decode()]
    finally:
        await beacon.stop()
    assert datetime.fromisoformat(rows.rows["radio/3/beacon_last_sent_at"]) == clock() and rows.rows[memory_key_of(FM_ID)] == "2000-01-01T00:00:00Z"
    assert not [r for r in caplog.records if "raised" in r.getMessage()], "no HF radio on: nothing is raised"
