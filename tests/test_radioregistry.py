"""The radio registry (neoaprs/radioregistry.py): the radios of the settings at run time, any
number. With test radios (tests/support/fakedriver.py): one per setting radio, a save restarts only
the radio whose key changed.
"""

import asyncio
import itertools
import json
import logging
from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs import ax25, emailrule, kiss, messagerule, radioregistry
from neoaprs.claims import Claim
from neoaprs.config import DEFAULTS, Config
from neoaprs.mercurydriver import MercuryDriver
from neoaprs.radiodriver import RunOverrides
from neoaprs.radioregistry import LiveRadio, RadioRegistry, driver_key, make_driver
from neoaprs.radiosearch import Found
from neoaprs.radiospec import FM_ID, HF_ID, RadioHeard, RadioId, RadioSpec, unheard_radio
from neoaprs.radiotype import RadioTypeError
from neoaprs.radiotypes import type_of
from neoaprs.services.radiofinder import RadioFinder
from neoaprs.services.radioset import ack_radio, answerable
from neoaprs.services.radioprobe import Timing
from neoaprs.source import Source
from neoaprs.station import Station
from neoaprs.tncdriver import TncDriver
from tests.support.air import from_internet
from tests.support.clock import FixedClock
from tests.support.env import ON_AIR, Env, until
from tests.support.fakedriver import FakeDriver, Rig, as_air, as_driver, as_pick, registry_of, spec, with_radios
from tests.support.faketnc import FakeTncServer
from tests.support.stubtnc import StubRadios, StubRegistry, StubTnc, as_air as stub_air, as_pick as stub_pick
from tests.support.tworadios import enabled_before, main_before, packet_before, station_before

T0 = FixedClock()()
THREE = [spec(1, port="/dev/ttyUSB0"), spec(2, "hf", enabled=False), spec(3, port="/dev/ttyUSB3")]


def three(**changes: object) -> list[RadioSpec]:
    """THREE with radio 3 changed."""
    return [*THREE[:2], replace(THREE[2], **changes)]  # type: ignore[arg-type]


def station(call: str, fm: int, hf: int) -> Station:
    return Station(
        call,
        first_heard=T0,
        last_heard=T0,
        heard_by={id: RadioHeard(count, T0) for id, count in ((FM_ID, fm), (HF_ID, hf)) if count},
    )


# ---- the radios there are


def test_a_radio_is_made_for_every_radio_of_the_settings_that_is_not_removed_with_its_driver_its_beacon_and_its_name() -> (
    None
):
    gone = spec(4, removed_at=T0, position=0)
    rig = Rig(with_radios(ON_AIR, [*THREE, gone]))
    assert rig.registry.all() == [] and rig.registry.senders() == [], "nothing before the first sync"
    assert rig.registry.sync(rig.config) == [1, 2, 3] and rig.registry.why == {
        1: "it is new",
        2: "it is new",
        3: "it is new",
    }
    radios = rig.registry.all()
    assert [r.id for r in radios] == [1, 2, 3] and rig.registry.get(4) is None and rig.registry.get(3) is radios[2], (
        "a removed radio has none"
    )
    assert [(r.name, r.kind, r.spec, r.driver, r.beacon, r.line.radio_id) for r in radios] == [
        (name, s.kind, s, rig.drivers[s.id], rig.beacons[s.id], s.id)
        for name, s in zip(("FM", "Mercury", "FM 2"), THREE, strict=True)
    ]
    assert [r.line.radio_name for r in radios] == ["", "", "FM 2"], (
        "the line of radio 1 and of radio 2 says today's words in its own log lines (`tnc`, `hf radio`: Tnc.label by its kind), any other its radio's name"
    )
    assert rig.made == [(1, "kiss"), (2, "mercury"), (3, "kiss")] and rig.wired == [1, 2, 3], (
        "one driver for each, and each handed to the wiring once"
    )
    assert rig.registry.enabled() == [radios[0], radios[2]] and rig.registry.senders() == [radios[0], radios[2]]
    assert rig.registry.sync(rig.config) == [] and rig.made == [(1, "kiss"), (2, "mercury"), (3, "kiss")], (
        "a sync with nothing new makes nothing"
    )
    assert rig.calls() == {1: [], 2: [], 3: []}, (
        "a sync asks nothing of a driver but its key: no radio is started by it"
    )


def test_the_radios_are_in_the_order_of_their_positions_and_a_radio_reads_the_settings_in_force() -> None:
    rig = registry_of(with_radios(ON_AIR, THREE))
    third = rig.registry.get(3)
    assert third is not None and (
        third.name,
        third.kind,
        third.rtype,
        third.limits,
        third.allowed,
        third.max_frame,
    ) == ("FM 2", "fm", type_of("kiss"), type_of("kiss").limits, type_of("kiss").allowed, None)
    hf = rig.registry.get(2)
    assert hf is not None and (hf.kind, hf.rtype, hf.max_frame, hf.limits.beacon_min_min, hf.allowed.paths) == (
        "hf",
        type_of("mercury"),
        123,
        30,
        False,
    )
    assert (
        rig.put(
            with_radios(
                ON_AIR,
                [
                    replace(THREE[0], position=9),
                    THREE[1],
                    replace(
                        THREE[2], name="Shack", settings={"port": "/dev/ttyUSB3", "path": "WIDE2-2", "digipeat": "true"}
                    ),
                ],
            )
        )
        == []
    )
    assert [r.id for r in rig.registry.all()] == [2, 3, 1] and rig.registry.senders()[0] is third, "by position"
    assert (
        third.name,
        third.line.radio_name,
        third.choice("path"),
        third.choice("digipeat"),
        third.choice("beacon"),
    ) == ("Shack", "Shack", "WIDE2-2", True, True), (
        "a name, a place and a choice restart nothing and are in force at once"
    )
    assert (
        rig.registry.name_of(1) == "FM" and rig.registry.name_of(3) == "Shack" and rig.registry.name_of(7) == "radio 7"
    )


def test_a_radio_of_the_registry_is_what_the_services_see_and_a_frame_goes_to_its_line() -> None:
    rig = registry_of(with_radios(ON_AIR, THREE))
    radio, pick = rig.registry.get(3), as_pick(rig.registry)
    assert radio is not None and pick.get(3) is radio and list(pick.enabled()) == rig.registry.enabled()
    air, line = as_air(radio), rig.drivers[3].line
    frame = ax25.Frame(ax25.Address("APRS"), ax25.Address.parse("OH2GBA"), (), info=b">a status")
    assert (air.id, air.kind, air.name, air.state, air.usable, air.why_unusable(), air.stats is line.stats) == (
        3,
        "fm",
        "FM 2",
        Source.State.STOPPED,
        False,
        line.why_unusable(),
        True,
    )
    assert as_driver(rig.drivers[3]).line is line and air.send_frame(frame) is False and line.sent == []
    line._set_state(Source.State.CONNECTED)
    assert air.usable and air.send_frame(frame) and line.sent == [frame]


# ---- a save: which radios restart


def test_a_sync_names_the_radio_whose_key_or_tickbox_changed_and_no_other_and_says_what_changed() -> None:
    rig = registry_of(with_radios(ON_AIR, THREE))
    assert (
        rig.put(with_radios(replace(ON_AIR, station_comment="another comment", beacon_interval_min=30), THREE)) == []
    ), "a setting of no radio restarts none"
    assert rig.put(with_radios(ON_AIR, three(settings={"port": "/dev/ttyACM0"}))) == [3] and rig.registry.why == {
        3: "port /dev/ttyUSB3 -> /dev/ttyACM0"
    }
    assert rig.put(
        with_radios(ON_AIR, [THREE[0], replace(THREE[1], enabled=True), *three(settings={"port": "/dev/ttyACM0"})[2:]])
    ) == [2] and rig.registry.why == {2: "switched on or off: off -> on"}
    assert rig.put(with_radios(replace(ON_AIR, serial_skip="/dev/ttyS0"), rig.config.radios)) == [1, 2, 3], (
        "what is the station's and in every driver's key restarts every radio"
    )
    assert rig.registry.why[1] == "ports to skip none -> /dev/ttyS0"
    assert rig.put(
        with_radios(
            replace(ON_AIR, serial_skip="/dev/ttyS0"),
            [replace(s, type="kiss-tcp", enabled=False) if s.id == 1 else s for s in rig.config.radios],
        )
    ) == [1]
    assert rig.registry.why == {1: "type kiss -> kiss-tcp, switched on or off: on -> off"}
    assert rig.calls() == {1: [], 2: [], 3: []} and rig.made == [(1, "kiss"), (2, "mercury"), (3, "kiss")], (
        "nothing was started, stopped or made by any of it: the controller restarts what the sync names"
    )


def test_a_sync_reads_what_differs_against_the_settings_in_force_at_that_moment() -> None:
    """The port the search found is put in force without a save (neoaprs/wiring.py): the next save
    must not take it for a change of the radio."""
    rig = registry_of(with_radios(ON_AIR, THREE))
    # Put in force past the registry
    rig.config = with_radios(replace(ON_AIR, serial_skip="/dev/ttyS0"), THREE)
    assert rig.put(with_radios(replace(ON_AIR, serial_skip="/dev/ttyS0", station_comment="x"), THREE)) == []
    assert rig.put(with_radios(replace(ON_AIR, station_comment="x"), THREE)) == [1, 2, 3]


# ---- the one lifecycle


async def test_a_restart_stops_the_radio_gives_it_the_settings_and_starts_it_while_it_is_enabled_and_touches_no_other(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, "neoaprs.controller")
    rig = registry_of(with_radios(ON_AIR, THREE))
    rig.run = RunOverrides(pattern="/tmp/probe_*", check_sec=0.0)
    await rig.registry.restart(3)
    assert rig.calls() == {1: [], 2: [], 3: ["stop", "configure", "start"]}, "radio 3 alone"
    assert rig.drivers[3].configured == [(THREE[2], rig.config, rig.run)], (
        "the settings in force: its own, the station's, the run's"
    )
    said = lambda: [r.getMessage() for r in caplog.records if r.name == "neoaprs.controller"]  # noqa: E731
    assert said() == ["the FM 2 radio is started: a fake kiss on /dev/ttyUSB3"]
    third, first = rig.registry.get(3), rig.registry.get(1)
    assert (
        third is not None
        and first is not None
        and third.state is Source.State.CONNECTED
        and third.usable
        and first.state is Source.State.STOPPED
    )
    await rig.registry.restart(2)
    assert rig.calls() == {1: [], 2: ["stop", "configure"], 3: []}, (
        "a radio whose tickbox is off takes the settings and stays stopped"
    )
    assert said()[-1] == "the Mercury radio is off in the settings"
    await rig.registry.restart(1)
    assert rig.put(with_radios(ON_AIR, three(enabled=False))) == [3]
    await rig.registry.restart(3)
    assert (
        rig.calls() == {1: ["stop", "configure", "start"], 2: [], 3: ["stop", "configure"]}
        and third.state is Source.State.STOPPED
        and first.state is Source.State.CONNECTED
    ), "radio 1 kept its line"
    await rig.registry.restart(9)
    assert rig.calls() == {1: [], 2: [], 3: []}, "a radio that is none is nobody's to restart"


async def test_a_third_radio_is_made_started_and_stopped_alone() -> None:
    rig = registry_of(with_radios(ON_AIR, THREE[:2]))
    for id in (1, 2):
        await rig.registry.restart(id)
    await rig.registry.beacons_as_set()
    assert rig.calls() == {1: ["stop", "configure", "start"], 2: ["stop", "configure"]} and [
        rig.beacons[id].running for id in (1, 2)
    ] == [True, False]
    assert (
        rig.put(with_radios(ON_AIR, THREE)) == [3] and rig.registry.why == {3: "it is new"} and rig.wired == [1, 2, 3]
    )
    third = rig.registry.get(3)
    assert (
        third is not None and third.state is Source.State.STOPPED and (third.name, third.line.radio_id) == ("FM 2", 3)
    ), "made by the sync, not started by it"
    await rig.registry.restart(3)
    await rig.registry.beacons_as_set()
    assert rig.calls() == {1: [], 2: [], 3: ["stop", "configure", "start"]} and third.usable and rig.beacons[3].running
    rig.claims.hold(Claim("serial", "/dev/ttyUSB3", 3))
    rig.claims.hold(Claim("serial", "/dev/ttyUSB0", 1))
    assert rig.put(with_radios(ON_AIR, [*THREE[:2], replace(THREE[2], removed_at=T0)])) == [3] and rig.registry.why == {
        3: "it is removed"
    }
    assert (
        rig.registry.get(3) is None
        and [r.id for r in rig.registry.all()] == [1, 2]
        and rig.registry.name_of(3) == "FM 2"
    ), "gone from the choices at once, though not stopped yet"
    await rig.registry.restart(3)
    assert (
        rig.calls() == {1: [], 2: [], 3: ["stop"]}
        and not rig.beacons[3].running
        and third.state is Source.State.STOPPED
    ), "stopped for good, its beacon with it"
    assert rig.claims.all() == (Claim("serial", "/dev/ttyUSB0", 1),), "and what it held is let go"
    assert rig.beacons[1].running and rig.registry.get(1).state is Source.State.CONNECTED, "radio 1 was not touched"  # type: ignore[union-attr]
    await rig.registry.restart(3)
    assert rig.calls() == {1: [], 2: [], 3: []}


async def test_each_beacon_runs_while_its_radio_is_on_and_stop_all_stops_every_radio() -> None:
    rig = registry_of(with_radios(ON_AIR, THREE))
    await rig.registry.beacons_as_set()
    assert [rig.beacons[id].running for id in (1, 2, 3)] == [True, False, True]
    rig.put(with_radios(ON_AIR, [replace(THREE[0], enabled=False), replace(THREE[1], enabled=True), THREE[2]]))
    await rig.registry.beacons_as_set()
    assert [rig.beacons[id].running for id in (1, 2, 3)] == [False, True, True]
    for id in (1, 2, 3):
        await rig.registry.restart(id)
    rig.calls()
    rig.claims.hold(Claim("serial", "/dev/ttyUSB3", 3))
    rig.put(with_radios(ON_AIR, [replace(THREE[0], enabled=False), replace(THREE[1], enabled=True)]))
    assert rig.beacons[3].running, "(its restart has not run)"
    await rig.registry.stop_all()
    assert rig.calls() == {1: ["stop"], 2: ["stop"], 3: ["stop"]}, "the one the settings no longer have too"
    assert not rig.beacons[3].running and rig.claims.all() == () and rig.registry.name_of(3) == "radio 3", (
        "stopped for good, its beacon with it, and what it held let go"
    )


async def test_the_registry_configures_every_radio_and_repoints_the_line_of_one() -> None:
    rig = registry_of(with_radios(ON_AIR, THREE))
    rig.registry.configure()
    assert rig.calls() == {1: ["configure"], 2: ["configure"], 3: ["configure"]}
    assert rig.registry.restart_key(3, rig.config) == (*rig.drivers[3].restart_key(THREE[2], rig.config, rig.run), True)
    assert rig.registry.restart_key(2, rig.config)[-1] is False, "the tickbox is the last of the key"
    stopped: list[str] = []
    line = rig.drivers[3].line

    async def stop() -> None:
        stopped.append("line stop")

    async def start() -> None:
        stopped.append("line start")

    line.stop, line.start = stop, start  # type: ignore[method-assign]
    await rig.registry.repoint(3)
    assert stopped == ["line stop", "line start"] and rig.calls() == {1: [], 2: [], 3: ["configure"]}, (
        "the line alone is stopped, pointed and started: the driver (the modem) is not stopped"
    )
    await rig.registry.repoint(9)


async def test_a_radio_whose_type_has_another_driver_gets_it_at_its_restart_on_the_line_it_had(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No two types of one kind have two drivers yet
    monkeypatch.setattr(
        radioregistry, "driver_key", lambda made_for: "tcp" if made_for.type == "kiss-tcp" else "serial"
    )
    rig = registry_of(with_radios(ON_AIR, THREE))
    await rig.registry.restart(3)
    old, radio = rig.drivers[3], rig.registry.get(3)
    assert radio is not None and radio.driver is old and radio.driver_key == "serial"
    assert rig.put(with_radios(ON_AIR, three(type="kiss-tcp"))) == [3] and rig.registry.why == {
        3: "type KISS TNC (Kenwood TH-D74/D75, Mobilinkd…) -> Your own Direwolf or soundmodem"
    }
    assert radio.driver is old and rig.wired == [1, 2, 3], "the driver in force until the restart"
    old.calls.clear()
    await rig.registry.restart(3)
    new = rig.drivers[3]
    assert (
        new is not old
        and radio.driver is new
        and radio.driver_key == "tcp"
        and rig.made[-1] == (3, "kiss-tcp")
        and rig.wired == [1, 2, 3, 3]
    ), "made around the settings, and handed to the wiring again"
    assert (
        old.calls == ["stop"]
        and new.calls == ["configure", "start"]
        and new.line is old.line
        and radio.line is old.line
    )


def test_the_driver_of_a_type_is_its_own_and_the_modems_for_the_dummy_hf_radio(tmp_path: Path) -> None:
    fm, hf = DEFAULTS.radios
    claims = registry_of(DEFAULTS).claims
    for key in ("kenwood-tnc2", "kenwood-d710", "kantronics", "kiss", "kiss-tcp", "dummy"):
        made_for = replace(fm, type=key)
        assert driver_key(made_for) == type_of(key).driver == "tnc" and isinstance(
            make_driver(made_for, claims, FixedClock(), tmp_path), TncDriver
        )
    assert driver_key(replace(hf, type="mercury")) == type_of("mercury").driver == "mercury"
    assert driver_key(replace(hf, type="dummy-hf")) == type_of("dummy-hf").driver == "mercury", (
        "the Dummy Mercury radio's speaker is the modem program: the modem's driver starts and stops it"
    )
    driver = make_driver(replace(hf, id=5), claims, FixedClock(), tmp_path)
    assert (
        isinstance(driver, MercuryDriver)
        and driver.line.radio_id == 5
        and driver.modem.holder == 5
        and driver.modem.folder == tmp_path / "radios" / "5"
        and driver.modem.claims is claims
    )
    with pytest.raises(RadioTypeError):
        driver_key(replace(fm, type="no-such-type"))


# ---- the choice of a radio

# FM on, HF on, heard on FM, on HF, the choice, the station in the book
CASES = list(itertools.product((True, False), (True, False), (0, 4), (0, 2), (None, FM_ID, HF_ID), (True, False)))


@pytest.mark.parametrize(("fm_on", "hf_on", "fm", "hf", "choice", "known"), CASES)
def test_the_radio_of_a_call_no_radio_heard_of_a_station_a_packet_and_an_email_are_the_rules_and_what_the_two_radios_chose_before(
    fm_on: bool, hf_on: bool, fm: int, hf: int, choice: RadioId | None, known: bool
) -> None:
    config = replace(DEFAULTS, fm_enabled=fm_on, hf_enabled=hf_on)
    rig = registry_of(config)
    if known:
        rig.book.seed([station("OH2GAX", fm, hf)])
        assert rig.registry.choose("OH2GAX", choice)
    registry = rig.registry
    found = rig.book.get("OH2GAX")
    heard, chosen = (found.heard_by, choice) if found is not None else ({}, None)
    assert registry.choice("OH2GAX") == chosen
    assert config.unheard_radio == unheard_radio(config.radios) == main_before(fm_on, hf_on)
    assert registry.for_station("OH2GAX") is (
        registry.get(by_rule)
        if (by_rule := messagerule.message_radio(chosen, heard, config.radios, T0)) is not None
        else None
    )
    assert registry.email() is (
        registry.get(mail) if (mail := emailrule.email_radio(config.radios, None)) is not None else None
    )
    assert getattr(registry.email(), "id", None) == (FM_ID if fm_on else HF_ID if hf_on else None), (
        "FM while it is on, as before; the Mercury radio alone carries a mail too (it was refused before)"
    )
    on_fm, on_hf = (
        replace(from_internet("OH2GAX", b">on FM", T0), via="rf", radio_id=FM_ID),
        replace(from_internet("OH2GAX", b">on HF", T0), via="rf", radio_id=HF_ID),
    )
    if not fm_on and not hf_on:
        assert (
            registry.senders() == []
            and registry.for_station("OH2GAX") is None
            and registry.for_packet(on_fm) is None
            and registry.enabled() == []
        ), "no radio: none (the two radios of before fell to the stopped FM line)"
        return
    to_station, answer_fm, answer_hf = (
        registry.for_station("OH2GAX"),
        registry.for_packet(on_fm),
        registry.for_packet(on_hf),
    )
    assert to_station is not None
    assert (registry.senders()[0].id, to_station.id) == (
        main_before(fm_on, hf_on),
        station_before(fm_on, hf_on, fm if known else 0, hf if known else 0, chosen),
    )
    assert [r.id for r in registry.enabled()] == enabled_before(fm_on, hf_on)
    assert (getattr(answer_fm, "id", None), getattr(answer_hf, "id", None)) == (
        FM_ID if fm_on else None,
        HF_ID if hf_on else None,
    ), "the radio the packet came on while it is on, else none: no other radio answers for it"
    for came, answer in ((FM_ID, answer_fm), (HF_ID, answer_hf)):
        assert answer is None or answer.id == packet_before(fm_on, hf_on, came), "while that radio is on, as before"
        assert answerable(registry, on_fm if came == FM_ID else on_hf) is (answer is not None), (
            "a query that came on a radio that is off now is not answered"
        )
        acked = ack_radio(registry, on_fm if came == FM_ID else on_hf, "OH2GAX")
        assert acked is not None and acked.id == (came if answer is not None else to_station.id), (
            "its ack goes on the radio a message to the station takes"
        )


def test_a_packet_from_the_internet_is_answered_on_no_radio() -> None:
    registry = registry_of(replace(DEFAULTS, hf_enabled=True)).registry
    with pytest.raises(ValueError, match="a packet from the internet is answered on no radio"):
        registry.for_packet(from_internet("OH2GAX", b">from the net", T0))


def test_with_three_radios_a_call_never_heard_goes_on_the_first_box_and_a_station_by_the_choice_or_by_what_fm_and_hf_heard() -> (
    None
):
    rig = registry_of(with_radios(ON_AIR, [spec(1, position=3), spec(2, "hf", position=2), spec(3, position=1)]))
    rig.book.seed([station("OH2NEAR", 3, 0), station("OH2FAR", 0, 2), station("OH2PICK", 3, 0)])
    registry = rig.registry
    assert registry.choose("OH2PICK", HF_ID)
    ids = lambda radio: None if radio is None else radio.id  # noqa: E731
    assert [r.id for r in registry.enabled()] == [3, 2, 1] and ids(registry.email()) == 3, (
        "no choice stored: email on the first box that can send (rule 3.5)"
    )
    assert (
        ids(registry.for_station("OH2NEAR")),
        ids(registry.for_station("OH2FAR")),
        ids(registry.for_station("OH2PICK")),
        ids(registry.for_station("OH2NEVER")),
    ) == (1, 2, 2, 3), "a call never heard goes on the first radio that can send, in the order of the boxes (rule 3.2)"
    assert rig.config.unheard_radio == 3
    rig.put(replace(rig.config, email_choice=2))
    assert ids(registry.email()) == 2, "the radio chosen in the E-mail tab, of any kind"
    rig.put(replace(rig.config, email_choice=1))
    assert ids(registry.email()) == 1
    rig.put(
        replace(
            with_radios(ON_AIR, [spec(1, position=3, enabled=False), spec(2, "hf", position=2), spec(3, position=1)]),
            email_choice=1,
        )
    )
    assert (ids(registry.for_station("OH2NEAR")), ids(registry.for_station("OH2PICK")), ids(registry.email())) == (
        3,
        2,
        3,
    ), "radio 1 off: the first box, the choice while it is on, email as with no choice stored"
    on_fm = replace(from_internet("OH2NEAR", b">on FM", T0), via="rf", radio_id=FM_ID)
    assert registry.for_packet(on_fm) is None and not answerable(registry, on_fm), (
        "a packet that came on a radio now off is answered on no radio"
    )
    assert ids(ack_radio(registry, on_fm, "OH2NEAR")) == 3 and ids(ack_radio(registry, on_fm, "OH2PICK")) == 2, (
        "its ack goes on the radio a message to that station takes"
    )


# ---- the operator's radio by station


def test_the_operators_radio_for_a_station_is_kept_by_id_a_row_of_before_is_read_and_the_choice_goes_with_the_station() -> (
    None
):
    rig = registry_of(replace(DEFAULTS, hf_enabled=True))
    rig.book.seed([station("OH2A", 3, 0), station("OH2B", 3, 2), station("OH2C", 0, 2)])
    registry, told = rig.registry, []
    rig.book.changed.connect(lambda changed: told.append((changed.call, registry.choice(changed.call))))
    assert (
        registry.choose("OH2A", HF_ID)
        and registry.choose("OH2B", FM_ID)
        and registry.choose("OH2C", HF_ID)
        and registry.choose("OH2C", None)
    )
    assert told == [("OH2A", HF_ID), ("OH2B", FM_ID), ("OH2C", HF_ID), ("OH2C", None)], (
        "the page is told with the station, with the choice in force"
    )
    assert (registry.choice("OH2A"), registry.choice("OH2B"), registry.choice("OH2C"), registry.choice("OH2Z")) == (
        HF_ID,
        FM_ID,
        None,
        None,
    )
    assert (
        registry.for_station("OH2A").id == HF_ID
        and registry.for_station("OH2B").id == FM_ID
        and registry.for_station("OH2C").id == HF_ID
    )  # type: ignore[union-attr]
    assert (
        rig.kept[-1] == registry.choices_text() == json.dumps({"OH2A": HF_ID, "OH2B": FM_ID}) and len(rig.kept) == 4
    ), "the row by the radios' ids (since migration 31), at every choice"
    again = registry_of(replace(DEFAULTS, hf_enabled=True))
    again.book.seed([station("OH2A", 3, 0), station("OH2B", 3, 2)])
    again.registry.restore(json.dumps({"OH2A": "hf", "OH2B": "fm"}))
    assert again.registry.choices_text() == rig.kept[-1], (
        "a row of before, in today's words, is read as the ids of radios 1 and 2"
    )
    assert not registry.choose("OH2A", 3) and len(rig.kept) == 4, "no such radio in the settings"
    assert (
        registry.choose("OH2A", None)
        and registry.choice("OH2A") is None
        and rig.kept[-1] == json.dumps({"OH2B": FM_ID})
    )
    registry.forget("OH2A")
    assert len(rig.kept) == 5, "a station with no choice takes none along"
    registry.forget("OH2B")
    assert rig.kept[-1] == "{}"
    registry.forget_all()
    assert len(rig.kept) == 6, "nothing to forget, nothing written"
    assert registry.choose("OH2B", FM_ID)
    registry.forget_all()
    assert rig.kept[-2:] == [json.dumps({"OH2B": FM_ID}), "{}"]
    assert (
        registry.choose("OH2Z", HF_ID)
        and registry.choice("OH2Z") == HF_ID
        and rig.kept[-1] == json.dumps({"OH2Z": HF_ID})
    ), "a call the book does not hold keeps its choice by call (plan rule 3.2)"
    later = registry_of(replace(DEFAULTS, hf_enabled=True))
    later.registry.restore(rig.kept[-1])
    assert later.registry.choice("OH2Z") == HF_ID and later.registry.choices_text() == rig.kept[-1], (
        "and across a restart, still without a station"
    )
    later.book.seed([station("OH2Z", 0, 2)])
    assert later.registry.choice("OH2Z") == HF_ID, "the station heard later has it"
    registry.forget("OH2Z")
    assert registry.choice("OH2Z") is None and rig.kept[-1] == "{}", "forgotten with the call"


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "not json",
        "[1, 2]",
        json.dumps({"OH2A": "hf", "OH2B": "lora", "OH2GONE": "fm", "OH2C": 7}),
        json.dumps({"OH2A": 2, "OH2B": True, "OH2C": 3, "OH2GONE": 1}),
    ],
)
async def test_the_choices_of_the_row_are_put_on_the_stations_of_the_book_and_a_row_that_is_none_is_no_choice(
    text: str | None,
) -> None:
    waited: list[str] = []

    async def written() -> None:
        waited.append("written")

    rig = registry_of(replace(DEFAULTS, hf_enabled=True))
    rig.book.seed([station("OH2A", 3, 0), station("OH2B", 3, 2), station("OH2C", 0, 2)])
    registry: RadioRegistry = RadioRegistry(
        rig.claims, rig._driver, rig._beacon, lambda: rig.config, rig.book, rig.kept.append, written
    )
    registry.restore(text)
    expected = {"OH2A": HF_ID} if text and text.startswith("{") else {}
    assert {
        call: registry.choice(call) for call in ("OH2A", "OH2B", "OH2C") if registry.choice(call) is not None
    } == expected and rig.kept == [], "read, not written"
    by_call = {**expected, "OH2GONE": FM_ID} if expected else {}
    assert json.loads(registry.choices_text()) == by_call and registry.choice("OH2GONE") == by_call.get("OH2GONE"), (
        "kept by id: a word of before, an id of a radio there is, nothing else (a radio the settings do not have, a word that is none, true); a call the book does not hold keeps its own (plan rule 3.2)"
    )
    await registry.flush()
    await rig.registry.flush()
    assert waited == ["written"], "the stop waits for a choice being written, where there is something to wait for"


# ---- the daemon: radios 1 and 2 are the registry's, each with the driver of its type


async def test_the_daemons_two_radios_are_the_registrys_with_their_drivers_and_the_lines_the_test_hands_in(
    tmp_path: Path,
) -> None:
    e = Env(tmp_path, radio=False, settings={"hf/enabled": "true", "hf/profile": "dummy-hf"})
    ctl = e.ctl
    # No program: the speaker is a nice-to-have, and the dummy works without it
    e.mercury._finder = lambda: None
    assert isinstance(ctl.radios, RadioRegistry) and [r.id for r in ctl.radios.all()] == [FM_ID, HF_ID], (
        "made with the process, from the defaults"
    )
    fm, hf = ctl.radios.all()
    assert (
        isinstance(fm, LiveRadio)
        and (e.tnc, e.beacon) == (fm.line, fm.beacon)
        and (e.hf, e.mercury, e.beacon_2) == (hf.line, hf.driver.modem, hf.beacon)
    )
    assert e.tnc is fm.line and e.hf is hf.line, "the lines the tests hand in and hold"
    assert (
        isinstance(fm.driver, TncDriver)
        and isinstance(hf.driver, MercuryDriver)
        and fm.driver.modem is None
        and hf.line.modem is e.mercury
    )
    assert fm.driver.search_lock is ctl.radios.search_lock and (
        e.mercury.claims,
        e.mercury.holder,
        e.mercury.folder,
    ) == (ctl.radios.claims, HF_ID, ctl.data_dir / "radios" / "2"), "the registry's lock and table"
    assert e.mercury.claims is ctl.radios.claims
    assert (
        fm.line.claims is ctl.radios.claims and fm.line.search_lock is ctl.radios.search_lock and hf.line.claims is None
    ), "radio 1's line has the station's table and its one search at a time; the modem's line, a socket, claims nothing"
    finder = ctl.radiofinder
    assert (finder.claims, finder.search_lock, finder._hold, finder._release) == (
        ctl.radios.claims,
        ctl.radios.search_lock,
        ctl.hold_radio,
        ctl.release_radio,
    ), (
        "Find my radio lets go of the radio it searches for alone and passes over what the others and the GPS receiver hold"
    )
    assert (fm.line.radio_id, fm.line.label, hf.line.radio_id, hf.line.label) == (FM_ID, "tnc", HF_ID, "hf radio"), (
        "the lines' own log lines begin as they did"
    )
    assert fm.line.interlock is hf.line.interlock is not None and ctl.radios.enabled() == [fm] and not hf.rtype.dummy, (
        "the defaults until the settings are read"
    )
    assert ctl.sender.radios is ctl.radios and ctl.digipeater._radios is ctl.radios, (
        "the sender (and our objects and bulletins through it) and the digipeater take the registry itself"
    )
    assert (
        ctl.messaging._given
        is ctl.queries._given
        is ctl.qru._given
        is ctl.qruask._given
        is ctl.generalask._given
        is ctl.rigstatus._radios
        is ctl.radios
    ), "messaging, the answers, asking and the status report take the registry itself"
    assert ctl.rigstatus.frames is ctl.beacon_frames is fm.beacon.frames is hf.beacon.frames and (
        fm.beacon.radio,
        hf.beacon.radio,
    ) == (fm, hf), "one maker of our frames for the status report and every radio's beacon, each beacon its own radio's"
    assert not hasattr(ctl, "radio_set"), "no service takes the two radios as one any more"
    assert ctl.run == RunOverrides("", str(e.ports / "probe_*"), "", 0.0, None), (
        "(and before the settings are read no Mercury radio of theirs takes --hf-port)"
    )
    ctl.pattern_override = ""
    assert ctl.run.pattern == "", "what the process gave for the run is read each time"
    ctl.pattern_override = str(e.ports / "probe_*")
    await e.start()
    assert (
        ctl.radios.all() == [fm, hf]
        and ctl.radios.enabled() == [fm, hf]
        and hf.rtype.dummy
        and (e.tnc, e.hf, e.mercury) == (fm.line, hf.line, hf.driver.modem)
    ), "the same radios, with the settings that were read"
    assert fm.beacon.running and hf.beacon.running and hf.line.is_dummy and ctl.igate.made_up()
    assert ctl.radios.restart_key(HF_ID, ctl.config)[-1] is True
    await until(lambda: hf.state is Source.State.CONNECTED)
    await ctl.hold_radio(FM_ID)
    assert (
        fm.state is Source.State.STOPPED
        and hf.state is Source.State.CONNECTED
        and "tnc" not in {t.get_name() for t in ctl.tasks}
    ), "one radio lets go of its line (a search), no other"
    ctl.release_radio(FM_ID)
    await until(lambda: fm.state is not Source.State.STOPPED)
    await e.stop()
    assert fm.state is hf.state is Source.State.STOPPED and not fm.beacon.running and not hf.beacon.running


def searching(url: str, finder: RadioFinder, radio: RadioId | None = None) -> "asyncio.Task[Found | None]":
    """A search of the finder over the one port of a fake TNC (tests/support/faketnc.py) that says
    nothing, under way: no device of the machine is listed or opened."""

    async def listed() -> list[str]:
        return [url]

    finder.ports, finder.timing = listed, Timing(listen_sec=30, answer_sec=30)
    return asyncio.create_task(finder.find(lambda step: None, radio))


async def test_find_my_radio_of_the_daemon_lets_go_of_the_fm_radio_alone_and_starts_it_again_while_hf_runs(
    tmp_path: Path,
) -> None:
    """The daemon's own finder, asked as the page asks it with no radio named (the handler gives it
    radio 1: tests/test_radiofinder_wire.py): the FM radio lets go of its line for the search, the
    Mercury radio and its modem keep running, and the FM radio takes its line again after it, with
    its beacon."""
    silent = await FakeTncServer("silent").start()
    e = Env(tmp_path / "data", settings={"hf/enabled": "true", "hf/profile": "dummy-hf"})
    # No program: the Dummy HF radio works without its speaker
    e.mercury._finder = lambda: None
    await e.start()
    fm, hf = e.ctl.radios.all()
    await until(lambda: fm.state is hf.state is Source.State.CONNECTED)
    hf_line = e.hf._generation
    search = searching(silent.url, e.ctl.radiofinder, FM_ID)
    await until(lambda: silent.connections == 1)
    assert fm.state is Source.State.STOPPED and hf.state is Source.State.CONNECTED, (
        "the FM radio let go of its line for the search, the Mercury radio did not"
    )
    assert e.ctl.radiofinder.cancel() and await search is None
    await until(lambda: fm.state is Source.State.CONNECTED)
    assert e.hf._generation == hf_line and fm.beacon.running and hf.beacon.running, (
        "the FM radio started again with its beacon, and the Mercury radio ran all the while"
    )
    await e.stop()
    await silent.aclose()


async def test_a_finder_given_the_hold_of_one_radio_lets_go_of_that_radio_alone_and_takes_the_stations_one_search_at_a_time(
    tmp_path: Path,
) -> None:
    """The finder made as the composition root makes it (the controller's hold_radio and
    release_radio, the registry's table and lock), asked for radio 1: the station's one search at a
    time."""
    silent = await FakeTncServer("silent").start()
    e = Env(tmp_path / "data", settings={"hf/enabled": "true", "hf/profile": "dummy-hf"})
    e.mercury._finder = lambda: None
    await e.start()
    fm, hf = e.ctl.radios.all()
    await until(lambda: fm.state is hf.state is Source.State.CONNECTED)
    hf_line, lock, ctl = e.hf._generation, e.ctl.radios.search_lock, e.ctl
    finder = RadioFinder(
        ctl._radio_ports, ctl.hold_radio, ctl.release_radio, claims=ctl.radios.claims, search_lock=lock
    )
    search = searching(silent.url, finder, FM_ID)
    await until(lambda: silent.connections == 1)
    assert fm.state is Source.State.STOPPED and lock.locked(), (
        "radio 1 let go of its line, and the search has the station's turn"
    )
    assert hf.state is Source.State.CONNECTED and e.hf._generation == hf_line and hf.beacon.running, (
        "the other radio was not touched"
    )
    assert finder.cancel() and await search is None
    await until(lambda: fm.state is Source.State.CONNECTED)
    assert not lock.locked() and hf.state is Source.State.CONNECTED and e.hf._generation == hf_line, (
        "radio 1 took its line again, the turn is free, and radio 2 ran all the while"
    )
    await e.stop()
    await silent.aclose()


async def test_a_third_radio_in_the_daemon_is_started_heard_by_the_parts_and_stopped_alone(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A third radio added (the database gives it its id) and given its port: the daemon's own
    driver, line, beacon and wiring take it. The radios are a field of the settings: a save of
    another setting keeps it, and its removal stops it alone."""
    caplog.set_level(logging.INFO, "neoaprs.controller")
    # Radios 1 and 2, the HF one off: the radio added is the third
    e = Env(tmp_path, settings={"hf/profile": "mercury"})
    await e.start()
    # A KISS server on the loopback: the third radio's
    other = await e.new_radio()
    fm_line = e.tnc._generation
    id = await e.ctl.add_radio("kiss-tcp", enabled=False)
    assert (
        id == 3
        and await e.ctl.save_radio_settings(id, {"port": other.url})
        and await e.ctl.change_radio(id, enabled=True)
    )
    third = e.ctl.radios.get(3)
    assert (
        third is not None
        and isinstance(third.driver, TncDriver)
        and third.line not in (e.tnc, e.hf)
        and (third.name, third.line.radio_id, third.line.interlock) == ("FM 2", 3, e.tnc.interlock)
    )
    await until(lambda: third.state is Source.State.CONNECTED and third.beacon.running)
    assert (
        "the FM 2 radio is restarted because its settings changed: it is new" in caplog.text
        and f"the FM 2 radio is started: Your own Direwolf or soundmodem,{other.url}" in caplog.text
    )
    assert (
        e.tnc.state is Source.State.CONNECTED
        and e.tnc._generation == fm_line
        and [r.id for r in e.ctl.radios.enabled()] == [1, 3]
    ), "radio 1 kept its line"
    other.feed(
        kiss.encode(
            ax25.encode(
                ax25.Frame(
                    ax25.Address("APRS"),
                    ax25.Address.parse("OH2TRD"),
                    (),
                    info=b"!6010.00N/02456.00E>on the third radio",
                )
            )
        )
    )
    await until(lambda: e.ctl.stationbook.get("OH2TRD") is not None)
    assert [p.source for p in await e.packets()] == ["OH2TRD"], (
        "what it hears goes to the parts by the one signal, once"
    )
    assert (
        await e.ctl.save_config(replace(e.ctl.config, station_comment="another comment"))
        and e.ctl.radios.get(3) is third
        and third.state is Source.State.CONNECTED
    ), "a save of another setting keeps the radio"
    assert await e.ctl.remove_radio(3)
    assert e.ctl.radios.get(3) is None and e.ctl.radios.why == {3: "it is removed"}
    await until(lambda: third.state is Source.State.STOPPED and not third.beacon.running)
    assert e.tnc.state is Source.State.CONNECTED and e.tnc._generation == fm_line and e.beacon.running, (
        "radio 1 was not touched"
    )
    await e.stop()


# ---- the doubles of the tests


@pytest.mark.parametrize(("fm_on", "hf_on"), list(itertools.product((True, False), (True, False))))
def test_the_stub_registry_of_the_services_tests_chooses_as_the_stub_radios_do_and_its_radios_are_what_the_services_see(
    fm_on: bool, hf_on: bool
) -> None:
    before, pick = StubRadios(hf_stations=("OH2C",)), StubRegistry(hf_stations=("OH2C",))
    before.enabled = {kind for kind, on in (("fm", fm_on), ("hf", hf_on)) if on}
    pick.on = {id for id, on in ((FM_ID, fm_on), (HF_ID, hf_on)) if on}
    # The stub of the one set and its like in the other
    same = {id(before.fm): pick.fm, id(before.hf): pick.hf}
    on_fm, on_hf = (
        replace(from_internet("OH2C", b">on FM", T0), via="rf", radio_id=FM_ID),
        replace(from_internet("OH2C", b">on HF", T0), via="rf", radio_id=HF_ID),
    )
    assert stub_pick(pick).enabled() == [same[id(radio)] for radio in before.on] and pick.email() is (
        pick.fm if fm_on else pick.hf if hf_on else None
    )
    if not fm_on and not hf_on:
        assert pick.senders() == [] and pick.for_station("OH2C") is None and pick.for_packet(on_hf) is None, (
            "no radio: none"
        )
        return
    assert (pick.senders()[0], pick.for_station("OH2C"), pick.for_station("OH2B")) == tuple(
        same[id(radio)] for radio in (before.default, before.for_station("OH2C"), before.for_station("OH2B"))
    )
    assert (pick.for_packet(on_fm), pick.for_packet(on_hf)) == (
        same[id(before.for_packet(on_fm))] if fm_on else None,
        same[id(before.for_packet(on_hf))] if hf_on else None,
    ), "the radio the packet came on while it is on, else none"
    fm, hf = stub_air(pick.fm), stub_air(pick.hf)
    assert (fm.id, fm.kind, fm.name, fm.limits, fm.allowed, fm.max_frame) == (
        FM_ID,
        "fm",
        "FM",
        type_of("kiss").limits,
        type_of("kiss").allowed,
        None,
    )
    assert (hf.id, hf.kind, hf.name, hf.limits, hf.allowed, hf.max_frame) == (
        HF_ID,
        "hf",
        "Mercury",
        type_of("mercury").limits,
        type_of("mercury").allowed,
        123,
    )
    assert (
        (fm.choice("beacon"), fm.choice("path"), fm.choice("digipeat")) == (True, "", False)
        and fm.stats.packets == 0
        and StubTnc(id=3).id == 3
    )


def test_a_config_of_a_test_with_any_number_of_radios_leaves_the_one_it_was_made_of_alone() -> None:
    made = with_radios(ON_AIR, THREE)
    assert (
        isinstance(made, Config)
        and made != ON_AIR
        and replace(made, radios=ON_AIR.radios) == ON_AIR
        and made.radios == tuple(THREE)
        and [s.id for s in ON_AIR.radios] == [FM_ID, HF_ID]
    ), "the radios are part of what the settings are"
    assert [s.id for s in made.enabled_radios] == [1, 3] and made.unheard_radio == 1 and made.radio(3) is THREE[2]
    assert isinstance(registry_of(made).drivers[1], FakeDriver)
