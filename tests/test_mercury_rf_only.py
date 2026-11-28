"""RF only on Mercury: two stations on the made-up HF air (tests/support/mercuryworld.py), each with Send
what I hear on and one APRS-IS stand-in. A message to a station ticked RF only goes with RFONLY as its
only path entry and its ack comes back with RFONLY too, so neither gateway puts them on APRS-IS;
without the tick both do."""

from pathlib import Path

import pytest

from neoaprs import ax25
from neoaprs.igaterules import NOGATE
from tests.support.env import Env, until
from tests.support.fakeaprsis import FakeAprsIs
from tests.support.mercuryworld import World

TEXT = "Moi HF"


def on_air(w: World, call: str) -> list[ax25.Frame]:
    """The frames the air carried from this station."""
    return [ax25.decode(payload) for sender, _, payload in w.air.delivered if sender is w[call].hf_radio]


def gated_message(server: FakeAprsIs) -> list[str]:
    return [line for line in server.packets if line.startswith("OH2A>") and f":OH2B     :{TEXT}" in line]


def gated_ack(server: FakeAprsIs) -> list[str]:
    return [line for line in server.packets if line.startswith("OH2B>") and ":OH2A     :ack" in line]


async def exchange(tmp_path: Path, server: FakeAprsIs, rf_only: bool) -> tuple[World, Env, Env]:
    gating = {"igate/enabled": "true", "igate/server": server.address, "igate/gate": "true"}
    w = World(tmp_path, frame_sec=0.1)
    a = await w.add("OH2A", **gating)
    b = await w.add("OH2B", lat=61.5, lon=23.8, **gating)
    await w.start()
    for e in (a, b):
        await until(lambda e=e: e.ctl.igate.state in ("connected", "listening"))  # type: ignore[misc]
    if rf_only:
        await a.ctl.prefbook.set_rf_only("OH2B", True)
    record = await a.ctl.messaging.send("OH2B", TEXT)
    await w.until(lambda: a.ctl.messaging.get(record.id).state == "acked")  # type: ignore[union-attr]
    return w, a, b


@pytest.mark.slow("runs made-up Mercury modems on the loopback with real time on the air")
async def test_a_message_to_a_station_ticked_rf_only_and_its_ack_go_with_rfonly_alone_and_neither_reaches_aprs_is(
    tmp_path: Path,
) -> None:
    server = FakeAprsIs()
    await server.start()
    try:
        w, a, b = await exchange(tmp_path, server, rf_only=True)
        [message] = [f for f in on_air(w, "OH2A") if b"{" in f.info]
        [ack] = [f for f in on_air(w, "OH2B") if b":ack" in f.info]
        assert message.path_text == "RFONLY" and ack.path_text == "RFONLY"
        await until(lambda: b.ctl.igate.dropped[NOGATE] >= 1 and a.ctl.igate.dropped[NOGATE] >= 1)
        assert gated_message(server) == [] and gated_ack(server) == []
        assert w.air.truncated == []
    finally:
        await server.stop()


@pytest.mark.slow("runs made-up Mercury modems on the loopback with real time on the air")
async def test_without_rf_only_the_message_and_its_ack_go_with_no_path_and_both_reach_aprs_is(tmp_path: Path) -> None:
    server = FakeAprsIs()
    await server.start()
    try:
        w, a, b = await exchange(tmp_path, server, rf_only=False)
        await until(lambda: gated_message(server) and gated_ack(server))
        assert [f.path for f in on_air(w, "OH2A") if b"{" in f.info] == [()]
        assert b.ctl.igate.dropped[NOGATE] == 0 and a.ctl.igate.dropped[NOGATE] == 0
    finally:
        await server.stop()
