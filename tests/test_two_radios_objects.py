"""Our own objects and the email gateway with two radios (neoaprs/radios.py, services/sender.py, services/ownobjects.py): the sender sees the daemon's radios by id (radio 1 the FM radio, radio 2 the HF radio,
the main one the FM radio while it is on, else the HF one); an object goes out on the radios its choice names by id (fm 1, hf 2, both) while they are on and on the main radio otherwise; a message to the email
gateway goes on the FM radio and is refused while the FM radio is off. Then the rules of plan rule 3.5 on stub lines: an object none of whose radios is on goes on the main radio and has its own again once
one is on, a new object is ticked for the main radio, the pause between our frames is each radio's, a kill goes where the object went, and a removed radio leaves the objects."""
from pathlib import Path

import pytest

from neoaprs import ax25
from neoaprs.message import EMAIL_GATEWAY, MessagingError
from neoaprs.ownlog import OwnLog
from neoaprs.ownobject import OwnObject
from neoaprs.radiotype import FM_ID, HF_ID
from neoaprs.services.ownobjects import OwnObjects
from neoaprs.services.sender import Sender
from tests.support.clock import FixedClock
from tests.support.env import remember_stop
from tests.support.mercuryworld import World
from tests.support.rig import OwnRig
from tests.support.seamshapes import LiveShape, RegistryShape
from tests.support.storedb import log_at
from tests.support.stubtnc import StubTnc


def frames_of(radio: object) -> list[ax25.Frame]:
    return [ax25.decode(payload) for payload in getattr(radio, "frames_in")]  # noqa: B009


async def test_an_object_goes_out_on_the_radio_it_was_given_and_on_both_when_asked(tmp_path: Path) -> None:
    w = World(tmp_path, frame_sec=0.2)
    a = await w.add("OH2A", 60.17, 24.94, fm=True, hf=True)
    await w.start()
    radios = a.ctl.sender.radios
    assert [r.id for r in radios.enabled()] == [FM_ID, HF_ID] and radios.main is not None and radios.main.id == FM_ID
    assert [r.id for r in a.ctl.sender.radios_for((HF_ID,))] == [HF_ID] and [r.id for r in a.ctl.sender.radios_for((FM_ID, HF_ID))] == [FM_ID, HF_ID]
    a.ctl.ownobjects.set("FMONLY", "object", 60.2, 24.9, "/", ">", "on FM", radio="fm")
    a.ctl.ownobjects.set("HFONLY", "object", 60.3, 24.8, "/", "-", "over HF", radio="hf")
    a.ctl.ownobjects.set("BOTH", "object", 60.4, 24.7, "/", "r", "on both", radio="both")
    await w.until(lambda: len([f for f in frames_of(a.radio) if b";" in f.info]) >= 2 and len([f for f in frames_of(a.hf_radio) if b";" in f.info]) >= 2, 10.0)
    fm_names = {f.info[1:10].rstrip() for f in frames_of(a.radio) if f.info.startswith(b";")}
    hf_names = {f.info[1:10].rstrip() for f in frames_of(a.hf_radio) if f.info.startswith(b";")}
    assert fm_names == {b"FMONLY", b"BOTH"} and hf_names == {b"HFONLY", b"BOTH"}
    assert all(f.path == () for f in frames_of(a.hf_radio)), "over HF every frame is direct, the object's path too"
    assert a.ctl.ownobjects.get("HFONLY") is not None and a.ctl.ownobjects.get("HFONLY").radio == "hf"       # type: ignore[union-attr]
    assert [a.ctl.ownobjects.get(name).radios for name in ("FMONLY", "HFONLY", "BOTH")] == [(FM_ID,), (HF_ID,), (FM_ID, HF_ID)]       # type: ignore[union-attr]
    with pytest.raises(Exception, match="not a radio"):
        a.ctl.ownobjects.set("BAD", "object", 60.4, 24.7, "/", "r", "x", radio="vhf")


async def test_with_one_radio_on_an_object_goes_on_that_radio_whatever_it_was_given(tmp_path: Path) -> None:
    w = World(tmp_path, frame_sec=0.2)
    c = await w.add("OH2C", 61.5, 23.8, fm=False, hf=True)
    await w.start()
    radios = c.ctl.sender.radios
    assert [r.id for r in radios.enabled()] == [HF_ID] and radios.main is not None and radios.main.id == HF_ID
    assert [r.id for r in c.ctl.sender.radios_for((FM_ID,))] == [HF_ID], "radio 1 is off: the main radio takes what was meant for it"
    c.ctl.ownobjects.set("FMSAID", "object", 61.5, 23.9, "/", ">", "said fm", radio="fm")
    await w.until(lambda: any(f.info.startswith(b";FMSAID") for f in frames_of(c.hf_radio)), 10.0)
    assert c.ctl.ownobjects.get("FMSAID").radio == "fm", "the choice is kept for the day the FM radio is on"       # type: ignore[union-attr]


async def test_the_email_gateway_is_the_fm_radios_and_is_refused_while_it_is_off(tmp_path: Path) -> None:
    w = World(tmp_path, frame_sec=0.2)
    a = await w.add("OH2A", 60.17, 24.94, fm=True, hf=True)
    c = await w.add("OH2C", 61.5, 23.8, fm=False, hf=True)
    await w.start()
    await a.ctl.messaging.send(EMAIL_GATEWAY, "john@example.org hello")
    await w.until(lambda: any(b":EMAIL-2" in f.info for f in frames_of(a.radio)), 10.0)
    assert not any(b":EMAIL-2" in f.info for f in frames_of(a.hf_radio)), "a mail never goes over HF"
    with pytest.raises(MessagingError, match="no radio that internet gateways hear is on") as refused:
        await c.ctl.messaging.send(EMAIL_GATEWAY, "john@example.org hello")
    assert refused.value.code == "message.email_fm_off"


# ---- the rules of our objects with two radios (plan rule 3.5), on the station's radios as the registry gives them over stub lines

class Two(OwnRig):
    """Our objects on two radios, radio 1's line `tnc` and radio 2's `hf`; `switch` turns one on or off as the settings would, and the radios have it at once."""

    def __init__(self, log: OwnLog, clock: FixedClock, **changes: object) -> None:
        super().__init__(log, clock, **changes)
        self.hf = StubTnc()
        lines = {FM_ID: self.tnc, HF_ID: self.hf}
        self.shapes = [LiveShape(spec, self.config.radios, lines[spec.id]) for spec in self.config.radios]      # type: ignore[arg-type]
        self.sender = Sender(RegistryShape(self.shapes), lambda: self.config, clock, spacing_sec=10.0)
        self.objects = OwnObjects(self.sender, lambda: self.config, log, clock=clock, tick_sec=3600.0)

    async def start(self) -> "Two":
        await self.objects.start()
        remember_stop(self.objects.stop)
        return self

    def switch(self, **on: bool) -> None:
        self.set(**on)
        for shape in self.shapes:
            shape.spec, shape.specs = self.config.radio(shape.id) or shape.spec, self.config.radios

    def make(self, name: str, **values: object) -> OwnObject:
        return self.objects.set(name, "object", 60.2, 24.9, "/", ">", **{"comment": name.lower(), **values})          # type: ignore[arg-type]

    def run(self, seconds: int, step: int = 1) -> None:
        self.look(self.objects.tick, seconds, step)

    def timed(self, seconds: int) -> list[tuple[int, str, str]]:
        """Ticks once a second for this long, the first now: what went out, as (seconds from now, the line `fm` or `hf`, the object's name)."""
        out: list[tuple[int, str, str]] = []
        for t in range(seconds + 1):
            before = {"fm": len(self.tnc.sent), "hf": len(self.hf.sent)}
            self.objects.tick()
            for word, line in (("fm", self.tnc), ("hf", self.hf)):
                out += [(t, word, f.info[1:10].rstrip().decode()) for f in line.sent[before[word]:]]
            self.clock.advance(1)
        return out


async def two_at(tmp_path: Path, **changes: object) -> Two:
    log, _, clock = await log_at(tmp_path, OwnLog)
    return await Two(log, clock, **changes).start()


def names(line: StubTnc) -> list[str]:
    return [f.info[1:10].rstrip().decode() for f in line.sent if f.info.startswith(b";")]


@pytest.mark.parametrize(("fm", "hf"), [(False, True), (True, False)])
async def test_an_object_none_of_whose_radios_is_on_goes_on_the_main_radio_and_has_its_own_again_once_one_is_on(tmp_path: Path, fm: bool, hf: bool) -> None:
    rig = await two_at(tmp_path, fm_enabled=fm, hf_enabled=hf)
    on, off = (rig.tnc, rig.hf) if fm else (rig.hf, rig.tnc)
    for name, word in (("FMOBJ", "fm"), ("HFOBJ", "hf"), ("BOTHOBJ", "both")):
        rig.make(name, radio=word)
    rig.run(30)
    assert sorted(names(on)) == ["BOTHOBJ", "FMOBJ", "HFOBJ"] and names(off) == [], "one radio on: every object goes on it, as before the radios were by id"
    assert [rig.objects.get(name).radios for name in ("FMOBJ", "HFOBJ", "BOTHOBJ")] == [(FM_ID,), (HF_ID,), (FM_ID, HF_ID)], "each keeps its own radios"      # type: ignore[union-attr]
    rig.switch(fm_enabled=True, hf_enabled=True)
    assert [[r.id for r in rig.sender.radios_for(rig.objects.get(name).radios)] for name in ("FMOBJ", "HFOBJ", "BOTHOBJ")] == [[FM_ID], [HF_ID], [FM_ID, HF_ID]]      # type: ignore[union-attr]
    rig.tnc.sent.clear()
    rig.hf.sent.clear()
    rig.run(120)
    assert set(names(rig.tnc)) == {"FMOBJ", "BOTHOBJ"} and set(names(rig.hf)) == {"HFOBJ", "BOTHOBJ"}, "with both on, each goes on its own radios again"


async def test_a_new_object_is_ticked_for_the_main_radio_and_a_changed_one_keeps_its_own(tmp_path: Path) -> None:
    rig = await two_at(tmp_path, fm_enabled=False, hf_enabled=True)
    assert rig.make("NEW").radios == (HF_ID,), "no radio named: the main radio, here the HF one"
    assert rig.make("SAID", radio="fm").radios == (FM_ID,), "a radio named (the page names one) is kept as named"
    assert rig.make("IDS", radios=(FM_ID, HF_ID)).radios == (FM_ID, HF_ID)
    rig.switch(fm_enabled=True, hf_enabled=True)
    assert rig.make("NEW", comment="moved").radios == (HF_ID,), "a change that names no radio keeps the object's"
    assert rig.make("NEWER").radios == (FM_ID,), "the main radio is now the first on by position, the FM one"


async def test_the_pause_between_our_frames_is_each_radios_own(tmp_path: Path) -> None:
    rig = await two_at(tmp_path, fm_enabled=True, hf_enabled=True)
    rig.make("FMONE", radio="fm")
    rig.make("FMTWO", radio="fm")
    rig.make("HFONE", radio="hf")
    sent = rig.timed(12)
    assert [(t, line) for t, line, _ in sent] == [(0, "fm"), (1, "hf"), (10, "fm")], "two objects on one radio go ten seconds apart; one due on the other radio does not wait for that pause"
    assert {name for _, line, name in sent if line == "fm"} == {"FMONE", "FMTWO"} and [name for _, line, name in sent if line == "hf"] == ["HFONE"]


async def test_an_object_on_both_goes_on_both_in_one_tick_and_its_kill_goes_where_it_went(tmp_path: Path) -> None:
    rig = await two_at(tmp_path, fm_enabled=True, hf_enabled=True)
    rig.make("BOTH", radio="both")
    rig.make("HFONLY", radio="hf")
    rig.run(1)
    assert (names(rig.tnc), names(rig.hf)) == (["BOTH"], ["BOTH"]), "the round of an object on both radios goes on each at once"
    rig.run(12)
    rig.tnc.sent.clear()
    rig.hf.sent.clear()
    rig.objects.kill("HFONLY")
    rig.run(240)
    killed = [f for f in rig.hf.sent if f.info.startswith(b";HFONLY   _")]
    assert len(killed) == 3 and not any(f.info.startswith(b";HFONLY") for f in rig.tnc.sent), "the kill goes three times on the radio the object went on"


async def test_the_kill_also_goes_on_a_radio_that_carried_the_object_while_its_own_was_off(tmp_path: Path) -> None:
    rig = await two_at(tmp_path, fm_enabled=False, hf_enabled=True)
    rig.make("AAA", radio="fm")
    rig.run(30)
    assert names(rig.hf) == ["AAA"] and names(rig.tnc) == [], "FM off: the object on FM went on the HF radio"
    rig.switch(fm_enabled=True, hf_enabled=True)
    rig.run(120)
    assert "AAA" in names(rig.tnc) and names(rig.hf) == ["AAA"], "FM on again: it goes on its own radio alone"
    rig.tnc.sent.clear()
    rig.hf.sent.clear()
    rig.objects.kill("AAA")
    rig.run(240)
    for line in (rig.tnc, rig.hf):
        assert [f.info[:11] for f in line.sent] == [b";AAA      _"] * 3, "the stations that heard it on HF are told it is gone too, three times, and nothing else goes"
    assert rig.objects.get("AAA") is None


async def test_a_removed_radio_leaves_the_objects_in_memory_and_an_object_on_it_alone_keeps_it(tmp_path: Path) -> None:
    rig = await two_at(tmp_path, fm_enabled=True, hf_enabled=True)
    rig.make("BOTH", radio="both")
    rig.make("HFONLY", radio="hf")
    rig.objects.forget_radio(HF_ID)
    assert (rig.objects.get("BOTH").radios, rig.objects.get("HFONLY").radios) == ((FM_ID,), (HF_ID,)), "as the removal's transaction leaves their rows"      # type: ignore[union-attr]
    rig.objects.forget_radio(7)
    assert rig.objects.get("BOTH").radios == (FM_ID,), "a radio no object is on changes nothing"      # type: ignore[union-attr]
