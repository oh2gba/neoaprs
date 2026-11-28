"""A message to a station never heard, with the path typed for its call (tests/support/mercuryworld.py):
on Packet through a NeoAPRS digipeater named in the path, and from a Packet-only station through a
gateway's pair to a station on Mercury; the ack comes back the same way."""

from pathlib import Path

import pytest

from neoaprs import ax25
from neoaprs.radiospec import FM_ID
from tests.support.mercuryworld import World

PAIR = {"pair/1/2/enabled": "true", "pair/1/2/ssid": "12"}


def fm_from(w: World, call: str) -> list[ax25.Frame]:
    """The FM frames this station's radio sent, as the others heard them, once each."""
    sent = [payload for sender, _, payload in w.fm_air.delivered if sender is w[call].radio]
    return [ax25.decode(payload) for payload in dict.fromkeys(sent)]


def hf_from(w: World, call: str) -> list[ax25.Frame]:
    return [ax25.decode(payload) for sender, _, payload in w.air.delivered if sender is w[call].hf_radio]


async def test_a_message_to_a_call_never_heard_goes_by_the_digipeater_typed_for_it_and_its_ack_comes_back(
    tmp_path: Path,
) -> None:
    w = World(tmp_path, frame_sec=0.1)
    a = await w.add("OH2DPN", fm=True, hf=False)
    await w.add("OH2GBA", 60.30, 24.60, fm=True, hf=False, **{"digi/enabled": "true"})
    c = await w.add("OH3XYZ", 61.00, 24.10, fm=True, hf=False)
    w.out_of_reach("OH2DPN", "OH3XYZ")
    await w.start()
    assert a.ctl.stationbook.get("OH3XYZ") is None
    await a.ctl.prefbook.set_path("OH3XYZ", "OH2GBA", FM_ID)
    record = await a.ctl.messaging.send("OH3XYZ", "Moi via OH2GBA")
    await w.until(lambda: a.ctl.messaging.get(record.id).state == "acked")  # type: ignore[union-attr]
    [sent] = [f for f in fm_from(w, "OH2DPN") if b"{" in f.info]
    assert sent.path_text == "OH2GBA", "the path typed for the call, alone"
    repeated = [f for f in fm_from(w, "OH2GBA") if f.source.call == "OH2DPN" and b"{" in f.info]
    assert [f.path_text for f in repeated] == ["OH2GBA*"], "the digipeater named repeated it, once"
    acks = [f for f in fm_from(w, "OH2GBA") if f.source.call == "OH3XYZ" and b":ack" in f.info]
    assert [f.path_text for f in acks] == ["OH2GBA*,WIDE2-1"], "the ack came back through it, as a fill-in"
    await w.until(lambda: [m.text for m in c.ctl.messaging.records() if m.direction == "in"] == ["Moi via OH2GBA"])


@pytest.mark.slow("runs made-up Mercury modems on the loopback with real time on the air")
async def test_a_packet_station_writes_to_a_mercury_station_it_never_heard_through_the_gateways_pair_call(
    tmp_path: Path,
) -> None:
    w = World(tmp_path, frame_sec=0.2)
    await w.add("OH2GBA", fm=True, hf=True, **PAIR)
    nick = await w.add("OH2DPN", 60.20, 24.90, fm=True, hf=False)
    far = await w.add("EA8EE-2", 28.10, -15.40, fm=False, hf=True)
    await w.start()
    assert nick.ctl.stationbook.get("EA8EE-2") is None
    await nick.ctl.prefbook.set_path("EA8EE-2", "OH2GBA-12", FM_ID)
    record = await nick.ctl.messaging.send("EA8EE-2", "Hola via HF")
    await w.until(lambda: nick.ctl.messaging.get(record.id).state == "acked")  # type: ignore[union-attr]
    [crossing] = [f for f in hf_from(w, "OH2GBA") if f.source.call == "OH2DPN" and b"{" in f.info]
    assert crossing.path_text == "OH2GBA-12*", "the pair passed it to HF, its call marked used"
    [ack] = [f for f in hf_from(w, "EA8EE-2") if b":ack" in f.info]
    assert ack.path_text == "OH2GBA-12", "the ack goes back by the gateway it came through"
    await w.until(lambda: [m.text for m in far.ctl.messaging.records() if m.direction == "in"] == ["Hola via HF"])
