"""Tests for a gateway with an FM and an HF radio and its pair switched on, between an FM-only and
an HF-only station (tests/support/mercuryworld.py): messages and acks cross in each direction, and a
WIDE path alone puts nothing on HF."""

from pathlib import Path

import pytest

from neoaprs import ax25
from neoaprs.radiospec import FM_ID, HF_ID
from tests.support.env import Env, idle_for
from tests.support.mercuryworld import World

PAIR_CALL = "OH2GBA-12"
PAIR = {"pair/1/2/enabled": "true", "pair/1/2/ssid": "12"}


def sent(radio: object) -> list[ax25.Frame]:
    """The frames the daemon gave this fake radio to send."""
    return [ax25.decode(payload) for payload in radio.frames_in]  # type: ignore[attr-defined]


def hf_frames(w: World, call: str) -> list[ax25.Frame]:
    """The frames the HF air carried from this station."""
    return [ax25.decode(payload) for sender, _, payload in w.air.delivered if sender is w[call].hf_radio]


def messages(frames: list[ax25.Frame]) -> list[ax25.Frame]:
    return [f for f in frames if f.info.startswith(b":") and b"{" in f.info and b":ack" not in f.info]


def acks(frames: list[ax25.Frame]) -> list[ax25.Frame]:
    return [f for f in frames if b":ack" in f.info]


async def three(tmp_path: Path, path: str = PAIR_CALL) -> tuple[World, Env, Env, Env]:
    w = World(tmp_path, frame_sec=0.2)
    gateway = await w.add("OH2GBA", fm=True, hf=True, **PAIR)
    fm = await w.add("OH2F", 60.20, 24.90, fm=True, hf=False, **{"beacon/path": path})
    hf = await w.add("OH2H", 61.50, 23.80, fm=False, hf=True)
    await w.start()
    return w, gateway, fm, hf


@pytest.mark.slow("runs made-up Mercury modems on the loopback with real time on the air")
async def test_a_message_with_the_pair_call_as_its_path_reaches_the_hf_station_in_one_hf_frame_and_its_ack_comes_back_through_the_gateway(
    tmp_path: Path,
) -> None:
    w, gateway, fm, hf = await three(tmp_path)
    record = await fm.ctl.messaging.send("OH2H", "Moi HF")
    await w.until(lambda: fm.ctl.messaging.get(record.id).state == "acked")  # type: ignore[union-attr]
    assert len(messages(hf_frames(w, "OH2GBA"))) == 1, "one HF frame carried the message across"
    crossing = messages(hf_frames(w, "OH2GBA"))[0]
    assert (
        crossing.source.call == "OH2F"
        and [a.call for a in crossing.path] == ["OH2GBA"]
        and crossing.path[0].ssid == 12
        and crossing.path[0].repeated
    )
    assert len(acks(hf_frames(w, "OH2H"))) == 1, "one HF frame carried the ack back to the gateway"
    ack = acks(hf_frames(w, "OH2H"))[0]
    assert [(a.call, a.ssid) for a in ack.path] == [("OH2GBA", 12)] and not ack.path[0].repeated, (
        "the reply path names the gateway's pair call"
    )
    assert len(acks(sent(gateway.radio))) == 1 and len(messages(sent(gateway.radio))) == 0, (
        "one FM frame carried the ack on to the station"
    )
    assert len(hf_frames(w, "OH2GBA")) == 1 and len(hf_frames(w, "OH2H")) == 1, "nothing else went on HF"
    stats = gateway.ctl.radios.get(HF_ID).stats.passed[FM_ID]  # type: ignore[union-attr]
    assert stats.sent == 1 and stats.held == 0


@pytest.mark.slow("runs made-up Mercury modems on the loopback with real time on the air")
async def test_the_reply_message_goes_back_through_the_gateway_the_same_way_and_its_ack_follows(tmp_path: Path) -> None:
    w, gateway, fm, hf = await three(tmp_path)
    first = await fm.ctl.messaging.send("OH2H", "Moi HF")
    await w.until(lambda: fm.ctl.messaging.get(first.id).state == "acked")  # type: ignore[union-attr]
    w.pass_time(30)
    await w.settled("OH2H")
    reply = await hf.ctl.messaging.send("OH2F", "Moi FM")
    await w.until(lambda: hf.ctl.messaging.get(reply.id).state == "acked")  # type: ignore[union-attr]
    on_hf = hf_frames(w, "OH2H")
    assert len(messages(on_hf)) == 1 and [(a.call, a.ssid) for a in messages(on_hf)[0].path] == [("OH2GBA", 12)], (
        "the reply goes on HF with the pair call as its path"
    )
    crossed = [f for f in messages(sent(gateway.radio)) if f.source.call == "OH2H"]
    assert len(crossed) == 1 and crossed[0].path[0].repeated, "one FM frame carried the reply across"
    assert len(acks(hf_frames(w, "OH2GBA"))) == 1, "the ack of the reply crossed to HF in one frame"
    await w.until(lambda: [m for m in fm.ctl.messaging.records() if m.direction == "in"])
    got = [m for m in fm.ctl.messaging.records() if m.direction == "in"]
    assert len(got) == 1 and got[0].text == "Moi FM"


@pytest.mark.slow("runs made-up Mercury modems on the loopback with real time on the air")
async def test_a_wide_path_alone_puts_nothing_on_hf(tmp_path: Path) -> None:
    w, gateway, fm, hf = await three(tmp_path, path="WIDE1-1,WIDE2-1")
    await fm.ctl.messaging.send("OH2H", "Moi HF")
    await w.until(
        lambda: (
            gateway.ctl.stationbook.get("OH2F") is not None
            and gateway.ctl.stationbook.get("OH2F").heard_on(FM_ID).count == 1
        )
    )  # type: ignore[union-attr]
    await idle_for(0.3)
    assert w.air.delivered == [] and hf_frames(w, "OH2GBA") == []
    assert gateway.ctl.radios.get(HF_ID).stats.passed == {}  # type: ignore[union-attr]
