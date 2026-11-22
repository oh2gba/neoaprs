"""Tests for the GPS serial port in the resource table (neoaprs/services/gps.py, claims.py): held
while the source is serial, released on change and stop, waits for a radio's port, and a save that
gives one port to both is refused."""

from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs.claims import Claim, Claims
from neoaprs.config import Config, SettingError
from neoaprs.gpsfeed import GpsFeed
from neoaprs.radiospec import RadioSpec
from neoaprs.serialprobe import claim_value
from neoaprs.services.gps import Gps
from neoaprs.source import Backoff, Source
from neoaprs.tncsearch import claimed
from neoaprs.web.confighandlers import refuse_held
from tests.support.clock import FixedClock
from tests.support.env import ON_AIR, Env, idle_for, remember_stop, until


class GpsRig:
    def __init__(self, **changes: object) -> None:
        self.config = replace(ON_AIR, **changes)  # type: ignore[arg-type]
        self.claims = Claims()
        self.feed = GpsFeed(FixedClock(), Backoff([0.05]), connect_sec=1.0)
        self.gps = Gps(self.feed, lambda: self.config, FixedClock(), tick_sec=0.01, claims=self.claims)
        remember_stop(self.gps.stop)

    def save(self, **changes: object) -> None:
        self.config = replace(self.config, **changes)  # type: ignore[arg-type]
        self.gps.settings_changed()


async def test_the_receivers_port_is_the_stations_while_it_is_read_and_let_go_when_the_source_changes_and_at_the_stop(
    tmp_path: Path,
) -> None:
    # (nothing there yet: the feed waits for it, and the port is the receiver's all the same)
    device = str(tmp_path / "gps")
    rig = GpsRig(gps_source="serial", gps_device=device)
    mine = Claim("gps", claim_value(device) or "", None)
    await rig.gps.start()
    await until(lambda: rig.claims.all() == (mine,))
    assert claimed(rig.claims, 1) == {mine.value: "held by the GPS receiver"}, "what a radio's search leaves out"
    rig.save(gps_source="off")
    await until(lambda: rig.claims.all() == ())
    rig.save(gps_source="serial", gps_device="socket://127.0.0.1:9")
    await idle_for(0.1)
    assert rig.claims.all() == (), "a TCP address is no device of the station"
    rig.save(gps_device=device)
    await until(lambda: rig.claims.all() == (mine,))
    await rig.gps.stop()
    assert rig.claims.all() == ()


async def test_a_port_a_radio_holds_is_not_opened_and_the_receiver_takes_it_once_the_radio_lets_go(
    tmp_path: Path,
) -> None:
    device = str(tmp_path / "gps")
    rig = GpsRig(gps_source="serial", gps_device=device)
    rig.claims.hold(Claim("serial", claim_value(device) or "", 1))
    await rig.gps.start()
    await idle_for(0.2)
    assert (
        rig.feed.state is Source.State.STOPPED
        and rig.gps.problem == "the receiver's port is held by radio 1"
        and [c.holder for c in rig.claims.all()] == [1]
    )
    rig.claims.release(1)
    await until(
        lambda: (
            rig.claims.all() == (Claim("gps", claim_value(device) or "", None),)
            and rig.feed.state is not Source.State.STOPPED
        )
    )


async def test_the_receiver_waits_only_for_a_serial_device_and_not_for_a_claim_of_another_kind_with_the_same_text(
    tmp_path: Path,
) -> None:
    device = str(tmp_path / "gps")
    rig = GpsRig(gps_source="serial", gps_device=device)
    value = claim_value(device) or ""
    rig.claims.hold(Claim("serial", value, 1))
    # (a card's id that reads like the path: no serial device of the station)
    rig.claims.hold(Claim("sound_card", value, 2))
    await rig.gps.start()
    await idle_for(0.1)
    assert rig.gps.problem == "the receiver's port is held by radio 1"
    rig.claims.release(1)
    await until(lambda: Claim("gps", value, None) in rig.claims.all() and rig.feed.state is not Source.State.STOPPED)


def kiss(id: int, port: str) -> RadioSpec:
    return RadioSpec(id, "fm", "kiss", "", True, id, settings={"port": port})


def test_a_save_that_gives_the_receivers_port_to_a_radio_or_a_radios_port_to_the_receiver_is_refused_and_a_swap_is_not() -> (
    None
):
    claims = Claims()
    before = Config(radios=(kiss(1, "/dev/ttyUSB0"), kiss(3, "")), gps_source="serial", gps_device="/dev/ttyACM9")
    claims.hold(Claim("gps", claim_value("/dev/ttyACM9") or "", None))
    with pytest.raises(SettingError) as held:
        refuse_held(before, replace(before, radios=(kiss(1, "/dev/ttyUSB0"), kiss(3, "/dev/ttyACM9"))), claims)
    assert (held.value.key, held.value.code, held.value.params) == (
        "radio/3/port",
        "radio.resource_held",
        {"resource": "serial", "holder": "GPS", "held_by": 0},
    )
    with pytest.raises(SettingError) as held:
        refuse_held(before, replace(before, radios=(kiss(1, "/dev/ttyUSB0"), kiss(3, "/dev/ttyACM9"))), Claims())
    assert held.value.params["held_by"] == 0, "the receiver's port by the settings, before the receiver holds it"
    with pytest.raises(SettingError) as held:
        refuse_held(before, replace(before, gps_device="/dev/ttyUSB0"), claims)
    assert (held.value.key, held.value.code, held.value.params) == (
        "gps/device",
        "radio.resource_held",
        {"resource": "gps", "holder": "FM", "held_by": 1},
    )
    found = Claims()
    # (the port radio 3's search found)
    found.hold(Claim("serial", claim_value("/dev/ttyUSB5") or "", 3))
    with pytest.raises(SettingError) as held:
        refuse_held(before, replace(before, gps_device="/dev/ttyUSB5"), found)
    assert (held.value.key, held.value.params["held_by"]) == ("gps/device", 3)
    # (the receiver moves and radio 3 takes its old port, in one save)
    refuse_held(
        before,
        replace(before, gps_device="/dev/ttyACM8", radios=(kiss(1, "/dev/ttyUSB0"), kiss(3, "/dev/ttyACM9"))),
        claims,
    )
    refuse_held(
        before, replace(before, gps_source="off", radios=(kiss(1, "/dev/ttyUSB0"), kiss(3, "/dev/ttyACM9"))), claims
    )


async def test_the_daemons_receiver_holds_its_port_and_find_my_radio_passes_it_over(tmp_path: Path) -> None:
    e = Env(tmp_path)
    await e.start()
    try:
        device = str(e.ports / "probe_gps")
        assert await e.ctl.save_config(replace(e.ctl.config, gps_source="serial", gps_device=device))
        value = claim_value(device) or ""
        await until(lambda: Claim("gps", value, None) in e.ctl.radios.claims.all())
        assert e.ctl.radiofinder._unclaimed([device], 1) == [], "Find my radio never tries the receiver's port"
        with pytest.raises(SettingError):
            refuse_held(
                e.ctl.config,
                replace(
                    e.ctl.config,
                    radios=tuple(
                        replace(s, settings={**s.settings, "port": device}) if s.id == 1 else s
                        for s in e.ctl.config.radios
                    ),
                ),
                e.ctl.radios.claims,
            )
        assert await e.ctl.save_config(replace(e.ctl.config, gps_source="off"))
        await until(lambda: all(c.kind != "gps" for c in e.ctl.radios.claims.all()))
    finally:
        await e.stop()
