"""Our own objects and the email gateway with two radios (neoaprs/radios.py, services/sender.py, services/ownobjects.py): the sender sees the daemon's radios by id (radio 1 the FM radio, radio 2 the HF radio,
the main one the FM radio while it is on, else the HF one); an object goes out on the radios its choice names by id (fm 1, hf 2, both) while they are on and on the main radio otherwise; a message to the email
gateway goes on the FM radio and is refused while the FM radio is off."""
from pathlib import Path

import pytest

from neoaprs import ax25
from neoaprs.message import EMAIL_GATEWAY, MessagingError
from neoaprs.radiotype import FM_ID, HF_ID
from tests.support.mercuryworld import World


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
    with pytest.raises(MessagingError, match="FM radio, which is off") as refused:
        await c.ctl.messaging.send(EMAIL_GATEWAY, "john@example.org hello")
    assert refused.value.code == "message.email_fm_off"
