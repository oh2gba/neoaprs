"""Two radios in one station (neoaprs/radios.py), in a world of three daemons on the suite's two airs (tests/support/mercuryworld.py: the fake Mercury's HF air and an FM air): OH2A has both radios, OH2B the FM
radio alone, OH2C the HF radio alone. A beacon of OH2A goes out on both radios and each neighbour hears it on its own; a station is tagged with the radio it was heard on; a message of OH2A goes to OH2B on FM
and to OH2C over HF, and each ack comes back on the radio the message came on; a message to a station heard on both radios goes on FM; with the HF radio off nothing of this is there. The tests of what a radio
does on its own (the frame cap, the hold, the paths) are tests/test_mercury_world.py; the choice is what is tested here."""
from pathlib import Path


from neoaprs import ax25
from neoaprs.config import DEFAULTS
from neoaprs.radios import Radios
from neoaprs.source import Source
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
    return (0, 0) if station is None else (station.heard_fm, station.heard_hf)


def frames_of(radio: FakeRadio | None) -> list[ax25.Frame]:
    """The frames the daemon gave this fake radio to send."""
    assert isinstance(radio, (FmStation, FakeMercury))
    return [ax25.decode(payload) for payload in radio.frames_in]


async def test_a_beacon_goes_out_on_both_radios_and_each_neighbour_hears_the_station_on_its_own(tmp_path: Path) -> None:
    w = await two_radios(tmp_path)
    a, b, c = w["OH2A"], w["OH2B"], w["OH2C"]
    assert a.ctl.beacon.send_now() and a.ctl.hf_beacon.send_now()
    await w.until(lambda: heard_on(b, "OH2A") == (1, 0) and heard_on(c, "OH2A") == (0, 1))
    assert a.ctl.radios.on == [a.tnc, a.hf] and b.ctl.radios.on == [b.tnc] and c.ctl.radios.on == [c.hf]
    assert frames_of(a.radio)[0].path and not frames_of(a.hf_radio)[0].path, "the FM beacon by its path, the HF one direct"


async def test_a_message_goes_out_on_the_radio_the_station_was_heard_on_and_the_ack_comes_back_the_same_way(tmp_path: Path) -> None:
    w = await two_radios(tmp_path)
    a, b, c = w["OH2A"], w["OH2B"], w["OH2C"]
    assert b.ctl.beacon.send_now() and c.ctl.hf_beacon.send_now()
    await w.until(lambda: heard_on(a, "OH2B") == (1, 0) and heard_on(a, "OH2C") == (0, 1))
    assert a.ctl.radios.for_station("OH2B") is a.tnc and a.ctl.radios.for_station("OH2C") is a.hf and a.ctl.radios.for_station("OH2Z") is a.tnc, "a station never heard goes on the default radio"
    await a.ctl.messaging.send("OH2B", "on FM, near")
    await a.ctl.messaging.send("OH2C", "over HF, far")
    await w.until(lambda: {r.state for r in a.ctl.messaging.records() if r.direction == "out"} == {"acked"}, 15.0)
    sent_fm, sent_hf = frames_of(a.radio), frames_of(a.hf_radio)
    assert any(b"on FM, near" in f.info for f in sent_fm) and not any(b":OH2B" in f.info for f in sent_hf), "to OH2B on FM only"
    assert any(b"over HF, far" in f.info for f in sent_hf) and not any(b":OH2C" in f.info for f in sent_fm), "to OH2C over HF only"
    assert any(b":OH2A" in f.info and b":ack" in f.info for f in frames_of(b.radio)), "OH2B's ack went on FM"
    assert any(b":OH2A" in f.info and b":ack" in f.info for f in frames_of(c.hf_radio)), "OH2C's ack went over HF"
    assert heard_on(a, "OH2B")[1] == 0 and heard_on(a, "OH2C")[0] == 0


async def test_a_station_heard_on_both_radios_is_messaged_on_fm_and_a_message_to_us_is_acked_on_the_radio_it_came_on(tmp_path: Path) -> None:
    w = World(tmp_path, frame_sec=0.2)
    await w.add("OH2A", 60.17, 24.94, fm=True, hf=True)
    await w.add("OH2D", 60.20, 24.90, fm=True, hf=True)
    await w.start()
    a, d = w["OH2A"], w["OH2D"]
    assert d.ctl.beacon.send_now() and d.ctl.hf_beacon.send_now()
    await w.until(lambda: heard_on(a, "OH2D") == (1, 1))
    assert a.ctl.radios.for_station("OH2D") is a.tnc, "heard on both: FM, which is near and costs no HF airtime"
    await d.ctl.messaging.send("OH2A", "over both, answered on FM")
    await w.until(lambda: any(r.state == "acked" for r in d.ctl.messaging.records() if r.direction == "out"), 15.0)
    assert any(b":ack" in f.info for f in frames_of(a.radio)) and not any(b":ack" in f.info for f in frames_of(a.hf_radio)), "OH2D sent on FM (it heard OH2A nowhere yet, so the default), and the ack went back on FM"


async def test_with_the_hf_radio_off_every_choice_falls_to_the_fm_radio_and_the_hf_radio_stays_stopped(tmp_path: Path) -> None:
    e = Env(tmp_path)
    await e.start()
    try:
        radios: Radios = e.ctl.radios
        assert e.ctl.config.fm_enabled and not e.ctl.config.hf_enabled
        assert radios.default is e.tnc and radios.for_station("OH2X") is e.tnc and radios.on == [e.tnc] and radios.of("hf") is None
        assert e.hf.state is Source.State.STOPPED and e.ctl.mercury.state == "stopped" and e.ctl.hf_beacon.last_sent is None
        assert radios.rules is e.tnc.rules and radios.max_frame is None and radios.usable == e.tnc.usable
        await e.ctl.save_config(DEFAULTS)         # (the defaults: still one radio)
        await until(lambda: e.hf.state is Source.State.STOPPED)
    finally:
        await e.stop()


# ---- the radio of the frame: with both radios on, what goes over HF neither waits for the FM radio nor is built by its rules

async def test_with_the_fm_radio_away_a_message_to_a_station_heard_on_hf_goes_over_hf_and_an_ack_held_by_hf_is_flushed_when_hf_is_free(tmp_path: Path) -> None:
    """The FM radio silent at night (here: its line gone) must hold nothing that goes over HF: the retry ticker gates every message on its own radio and flushes the acks whose radio takes frames."""
    w = await two_radios(tmp_path)
    a, c = w["OH2A"], w["OH2C"]
    assert c.ctl.hf_beacon.send_now()
    await w.until(lambda: heard_on(a, "OH2C") == (0, 1))
    a.unplug()
    await w.until(lambda: not a.tnc.usable and a.tnc.state is not Source.State.CONNECTED)
    assert a.hf.usable and a.ctl.radios.for_station("OH2C") is a.hf
    record = await a.ctl.messaging.send("OH2C", "over HF while FM is away")
    await w.until(lambda: a.ctl.messaging.get(record.id).state == "acked", 15.0)      # type: ignore[union-attr]
    assert a.ctl.messaging.get(record.id).attempts == 1 and not frames_of(a.radio), "attempted at once over HF, nothing waited for the FM radio"       # type: ignore[union-attr]
    assert a.hf_radio is not None
    a.hf_radio.say_control("PTT ON")                                       # (a's modem says it keyed: a's HF radio is held until PTT OFF, and a's FM radio is still away; the air's own BUSY lines do not touch PTT)
    await w.until(lambda: a.ctl.mercury.keyed)
    incoming = await c.ctl.messaging.send("OH2A", "to a while it is held")
    await w.until(lambda: any(r.direction == "in" and r.text == "to a while it is held" for r in a.ctl.messaging.records()), 15.0)
    await w.until(lambda: len(a.ctl.messaging.acks.waiting) == 1)
    assert a.ctl.messaging.acks.waiting[0].radio is a.hf
    a.hf_radio.say_control("PTT OFF")
    await w.until(lambda: c.ctl.messaging.get(incoming.id).state == "acked", 15.0)     # type: ignore[union-attr]
    assert not a.ctl.messaging.acks.waiting and not frames_of(a.radio), "the ack went over HF when HF was free, though the FM radio was still away"


async def test_an_ack_to_a_station_heard_on_both_radios_for_a_message_that_came_over_hf_is_built_for_hf(tmp_path: Path) -> None:
    """The station is reached on FM (it is near), but this message came over HF and its ack goes back over HF: no path, within the frame."""
    w = World(tmp_path, frame_sec=0.2)
    await w.add("OH2A", 60.17, 24.94, fm=True, hf=True)
    await w.add("OH2D", 60.20, 24.90, fm=True, hf=True)
    await w.start()
    a, d = w["OH2A"], w["OH2D"]
    assert d.ctl.beacon.send_now() and d.ctl.hf_beacon.send_now()
    await w.until(lambda: heard_on(a, "OH2D") == (1, 1))
    assert a.ctl.radios.for_station("OH2D") is a.tnc
    assert d.hf_radio is not None
    w.air.transmit(d.hf_radio, ax25.encode(ax25.Frame(ax25.Address.parse("APZNEO"), ax25.Address.parse("OH2D"), (), info=b":OH2A     :over HF this time{07}")))
    await w.until(lambda: any(r.direction == "in" and r.msg_id == "07" for r in a.ctl.messaging.records()), 15.0)
    await w.until(lambda: any(b":ack07" in f.info for f in frames_of(a.hf_radio)), 15.0)
    ack = next(f for f in frames_of(a.hf_radio) if b":ack07" in f.info)
    assert ack.path == () and len(ax25.encode(ack)) <= 123, "built for the HF radio it goes back on, not for the FM radio the station is otherwise reached on"
    assert not any(b":ack07" in f.info for f in frames_of(a.radio))
