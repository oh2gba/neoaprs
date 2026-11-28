"""Two radios in one station (the registry, neoaprs/radioregistry.py) in a world of three daemons on
the fake Mercury HF air and an FM air: OH2A has both radios, OH2B the FM radio alone, OH2C the HF
radio alone.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from neoaprs import ax25
from neoaprs.config import DEFAULTS
from neoaprs.radiospec import FM_ID, HF_ID
from neoaprs.source import Source
from neoaprs.tnc import Tnc
from tests.support.env import Env, until
from tests.support.fakemercury import FakeMercury
from tests.support.fakeradio import FakeRadio
from tests.support.mercuryworld import FmStation, World


async def two_radios(tmp_path: Path) -> World:
    w = World(tmp_path, frame_sec=0.2)
    await w.add("OH2A", 60.17, 24.94, fm=True, hf=True)
    await w.add("OH2B", 60.20, 24.90, fm=True, hf=False)
    await w.add("OH2C", 61.50, 23.80, fm=False, hf=True)
    await w.start()
    return w


def heard_on(e: Env, call: str) -> tuple[int, int]:
    station = e.ctl.stationbook.get(call)
    return (0, 0) if station is None else (station.heard_on(FM_ID).count, station.heard_on(HF_ID).count)


def lines_on(e: Env) -> list[Tnc]:
    """The lines of the radios that are enabled, by the registry."""
    return [radio.line for radio in e.ctl.radios.enabled()]


def line_to(e: Env, call: str) -> Tnc:
    """The line of the radio a message to the station goes out on, by the registry."""
    radio = e.ctl.radios.for_station(call)
    assert radio is not None
    return radio.line


def frames_of(radio: FakeRadio | None) -> list[ax25.Frame]:
    """The frames the daemon gave this fake radio to send."""
    assert isinstance(radio, (FmStation, FakeMercury))
    return [ax25.decode(payload) for payload in radio.frames_in]


async def test_a_beacon_goes_out_on_both_radios_and_each_neighbour_hears_the_station_on_its_own(tmp_path: Path) -> None:
    w = await two_radios(tmp_path)
    a, b, c = w["OH2A"], w["OH2B"], w["OH2C"]
    assert a.beacon.send_now() and a.beacon_2.send_now()
    await w.until(lambda: heard_on(b, "OH2A") == (1, 0) and heard_on(c, "OH2A") == (0, 1))
    assert lines_on(a) == [a.tnc, a.hf] and lines_on(b) == [b.tnc] and lines_on(c) == [c.hf]
    assert [radio.id for radio in a.ctl.radios.all()] == [radio.id for radio in c.ctl.radios.all()] == [FM_ID, HF_ID], (
        "a radio that is off has its place in the registry all the same"
    )
    assert frames_of(a.radio)[0].path and not frames_of(a.hf_radio)[0].path, (
        "the FM beacon by its path, the HF one direct"
    )


async def test_each_beacon_runs_while_its_radio_is_on_and_not_otherwise(tmp_path: Path) -> None:
    """A beacon of a radio that is off would only say, at every due time, that the radio is not
    there."""
    w = await two_radios(tmp_path)
    a, b, c = w["OH2A"], w["OH2B"], w["OH2C"]
    assert a.beacon.running and a.beacon_2.running
    assert b.beacon.running and b.ctl.radios.get(HF_ID) is None
    assert not c.beacon.running and c.beacon_2.running


@pytest.mark.slow("runs a daemon with its radios and services through its loop")
async def test_a_message_goes_out_on_the_radio_the_station_was_heard_on_and_the_ack_comes_back_the_same_way(
    tmp_path: Path,
) -> None:
    w = await two_radios(tmp_path)
    a, b, c = w["OH2A"], w["OH2B"], w["OH2C"]
    assert b.beacon.send_now() and c.beacon_2.send_now()
    await w.until(lambda: heard_on(a, "OH2B") == (1, 0) and heard_on(a, "OH2C") == (0, 1))
    assert line_to(a, "OH2B") is a.tnc and line_to(a, "OH2C") is a.hf and line_to(a, "OH2Z") is a.tnc, (
        "a station never heard goes on the first box that can send"
    )
    await a.ctl.messaging.send("OH2B", "on FM, near")
    await a.ctl.messaging.send("OH2C", "over HF, far")
    await w.until(lambda: {r.state for r in a.ctl.messaging.records() if r.direction == "out"} == {"acked"}, 15.0)
    sent_fm, sent_hf = frames_of(a.radio), frames_of(a.hf_radio)
    assert any(b"on FM, near" in f.info for f in sent_fm) and not any(b":OH2B" in f.info for f in sent_hf), (
        "to OH2B on FM only"
    )
    assert any(b"over HF, far" in f.info for f in sent_hf) and not any(b":OH2C" in f.info for f in sent_fm), (
        "to OH2C over HF only"
    )
    assert any(b":OH2A" in f.info and b":ack" in f.info for f in frames_of(b.radio)), "OH2B's ack went on FM"
    assert any(b":OH2A" in f.info and b":ack" in f.info for f in frames_of(c.hf_radio)), "OH2C's ack went over HF"
    assert heard_on(a, "OH2B")[1] == 0 and heard_on(a, "OH2C")[0] == 0


async def test_a_station_heard_on_both_radios_is_messaged_on_fm_and_a_message_to_us_is_acked_on_the_radio_it_came_on(
    tmp_path: Path,
) -> None:
    w = World(tmp_path, frame_sec=0.2)
    await w.add("OH2A", 60.17, 24.94, fm=True, hf=True)
    await w.add("OH2D", 60.20, 24.90, fm=True, hf=True)
    await w.start()
    a, d = w["OH2A"], w["OH2D"]
    assert d.beacon.send_now() and d.beacon_2.send_now()
    await w.until(lambda: heard_on(a, "OH2D") == (1, 1))
    assert line_to(a, "OH2D") is a.tnc, "heard on both: FM, which is near and costs no HF airtime"
    await d.ctl.messaging.send("OH2A", "over both, answered on FM")
    await w.until(lambda: any(r.state == "acked" for r in d.ctl.messaging.records() if r.direction == "out"), 15.0)
    assert any(b":ack" in f.info for f in frames_of(a.radio)) and not any(
        b":ack" in f.info for f in frames_of(a.hf_radio)
    ), "OH2D sent on FM (it heard OH2A nowhere yet, so the default), and the ack went back on FM"


@pytest.mark.parametrize("set_up", [False, True], ids=["hf never set up", "hf set up and off"])
async def test_with_the_hf_radio_off_every_choice_falls_to_the_fm_radio_and_the_hf_radio_stays_stopped(
    tmp_path: Path, set_up: bool
) -> None:
    """Off, whether it was never set up (the database has no radio 2) or was set up and switched off
    (radio 2 is there, off)."""
    e = Env(tmp_path, settings={"hf/enabled": "false"} if set_up else {})
    await e.start()
    try:
        radios = e.ctl.radios
        assert e.ctl.config.fm_enabled and not e.ctl.config.hf_enabled
        main, hf = next(iter(radios.senders()), None), radios.get(HF_ID)
        assert (
            main is not None
            and main.id == FM_ID
            and main.line is e.tnc
            and line_to(e, "OH2X") is e.tnc
            and lines_on(e) == [e.tnc]
            and radios.email() is main
        )
        if set_up:
            assert hf is not None and not hf.spec.enabled and hf.line is e.hf, (
                "the HF radio is there, off, and is never chosen"
            )
        else:
            assert hf is None and [r.id for r in radios.all()] == [FM_ID], "no HF radio at all"
        assert e.hf.state is Source.State.STOPPED and (
            hf is None
            or (hf.driver.modem is not None and hf.driver.modem.state == "stopped" and hf.beacon.last_sent is None)
        )
        assert (
            main.rtype == e.tnc.rtype
            and main.max_frame is None
            and main.usable == e.tnc.usable
            and (main.kind, main.name) == ("fm", "Packet")
        )
        # The defaults of the station's settings: still the radios it has
        await e.ctl.save_config(replace(DEFAULTS, radios=e.ctl.config.radios))
        await until(lambda: e.hf.state is Source.State.STOPPED)
    finally:
        await e.stop()


# ---- the radio of the frame: with both radios on, what goes over HF neither waits for the FM radio
# nor is built by its rules


@pytest.mark.slow("runs a daemon with its radios and services through its loop")
async def test_with_the_fm_radio_away_a_message_to_a_station_heard_on_hf_goes_over_hf_and_an_ack_held_by_hf_is_flushed_when_hf_is_free(
    tmp_path: Path,
) -> None:
    """The FM radio silent at night (here: its line gone) must hold nothing that goes over HF: the
    retry ticker gates every message on its own radio and flushes the acks whose radio takes frames.
    """
    w = await two_radios(tmp_path)
    a, c = w["OH2A"], w["OH2C"]
    assert c.beacon_2.send_now()
    await w.until(lambda: heard_on(a, "OH2C") == (0, 1))
    a.unplug()
    await w.until(lambda: not a.tnc.usable and a.tnc.state is not Source.State.CONNECTED)
    assert a.hf.usable and line_to(a, "OH2C") is a.hf
    record = await a.ctl.messaging.send("OH2C", "over HF while FM is away")
    await w.until(lambda: a.ctl.messaging.get(record.id).state == "acked", 15.0)  # type: ignore[union-attr]
    assert a.ctl.messaging.get(record.id).attempts == 1 and not frames_of(a.radio), (
        "attempted at once over HF, nothing waited for the FM radio"
    )  # type: ignore[union-attr]
    assert a.hf_radio is not None
    # a's modem says it keyed: a's HF radio is held until PTT OFF, and a's FM radio is still away;
    # the air's own BUSY lines do not touch PTT
    a.hf_radio.say_control("PTT ON")
    await w.until(lambda: a.mercury.keyed)
    incoming = await c.ctl.messaging.send("OH2A", "to a while it is held")
    await w.until(
        lambda: any(r.direction == "in" and r.text == "to a while it is held" for r in a.ctl.messaging.records()), 15.0
    )
    await w.until(lambda: len(a.ctl.messaging.acks.waiting) == 1)
    assert a.ctl.messaging.acks.waiting[0].radio == HF_ID, "the ack waits for the radio it goes back on, by its id"
    a.hf_radio.say_control("PTT OFF")
    await w.until(lambda: c.ctl.messaging.get(incoming.id).state == "acked", 15.0)  # type: ignore[union-attr]
    assert not a.ctl.messaging.acks.waiting and not frames_of(a.radio), (
        "the ack went over HF when HF was free, though the FM radio was still away"
    )


async def test_an_ack_to_a_station_heard_on_both_radios_for_a_message_that_came_over_hf_is_built_for_hf(
    tmp_path: Path,
) -> None:
    """The station is reached on FM (it is near), but this message came over HF and its ack goes
    back over HF: no path, within the frame."""
    w = World(tmp_path, frame_sec=0.2)
    await w.add("OH2A", 60.17, 24.94, fm=True, hf=True)
    await w.add("OH2D", 60.20, 24.90, fm=True, hf=True)
    await w.start()
    a, d = w["OH2A"], w["OH2D"]
    assert d.beacon.send_now() and d.beacon_2.send_now()
    await w.until(lambda: heard_on(a, "OH2D") == (1, 1))
    assert line_to(a, "OH2D") is a.tnc
    assert d.hf_radio is not None
    w.air.transmit(
        d.hf_radio,
        ax25.encode(
            ax25.Frame(
                ax25.Address.parse("APZNEO"), ax25.Address.parse("OH2D"), (), info=b":OH2A     :over HF this time{07}"
            )
        ),
    )
    await w.until(lambda: any(r.direction == "in" and r.msg_id == "07" for r in a.ctl.messaging.records()), 15.0)
    await w.until(lambda: any(b":ack07" in f.info for f in frames_of(a.hf_radio)), 15.0)
    ack = next(f for f in frames_of(a.hf_radio) if b":ack07" in f.info)
    assert ack.path == () and len(ax25.encode(ack)) <= 123, (
        "built for the HF radio it goes back on, not for the FM radio the station is otherwise reached on"
    )
    assert not any(b":ack07" in f.info for f in frames_of(a.radio))
