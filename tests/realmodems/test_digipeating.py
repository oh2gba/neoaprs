"""Tests for a gateway's pair through the real modems: A (Direwolf) and G share the VHF cable, G (Direwolf
and Mercury, its pair on) and B (Mercury) the HF cable. Messages and acks cross both ways, a WIDE path
alone and a message to G itself stay off HF, and a beacon by way of the pair's call reaches B. H1 and H2
(Direwolf at 300 baud) share a cable of their own: a message and its ack."""

# The cases are one story told in order on one set of stations (tests/realmodems/conftest.py).

import asyncio
import os
import re
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from tests.realmodems.stations import (
    A,
    B,
    CROSS_SEC,
    G,
    H1,
    H2,
    PAIR_CALL,
    World,
    crossed,
    exchange,
    heard_over_the_pair,
    programs,
    read_machine,
    refusal,
)

pytestmark = pytest.mark.asyncio(loop_scope="module")

HEARD_SEC = 120.0
QUIET_SEC = 40.0  # long enough for a frame G would have passed on to be on HF and heard by B


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def world(tmp_path_factory: pytest.TempPathFactory) -> AsyncIterator[World]:
    why = refusal(os.environ, read_machine())
    if why:
        pytest.exit(why, returncode=3)
    missing = [str(p) for p in programs() if not p.is_file()]
    assert not missing, (
        f"the modems are not built: {missing} (scripts/build-mercury --install, scripts/build-direwolf --install)"
    )
    w = World(Path(tmp_path_factory.mktemp("stations")))
    try:
        bases = await asyncio.to_thread(w.start)
        await w.open(bases)
        yield w
    finally:
        w.close_pages()
        await asyncio.to_thread(w.stop)


async def test_a_message_from_a_reaches_b_over_mercury_and_bs_ack_comes_back(world: World) -> None:
    await exchange(world, A.call, B.call, "realmodems A to B")
    acks = [p for p in world[A.call].packets(direction="in", sender=B.call) if ":ack" in str(p["tnc2"])]
    assert acks and f"{PAIR_CALL}*" in acks[-1]["path"], "B's ack came back by way of the pair's call"


async def test_a_message_from_b_reaches_a_over_the_gateway_and_as_ack_comes_back(world: World) -> None:
    await heard_over_the_pair(world, A.call, B.call)  # (B answers by the way it heard A, whatever ran before)
    await exchange(world, B.call, A.call, "realmodems B to A")


async def quiet_on_hf(world: World, g_after: int, b_after: int) -> None:
    """Nothing of A's went out on G's Mercury, nor reached B, while QUIET_SEC passed."""
    g, b = world[G.call], world[B.call]
    hf = g.radio_id("hf")
    await asyncio.sleep(QUIET_SEC)
    assert g.packets(g_after, direction="out", sender=A.call, radio_id=hf) == []
    assert b.packets(b_after, sender=A.call) == []


async def test_a_beacon_with_wide1_1_alone_is_heard_by_g_and_does_not_cross_onto_hf(world: World) -> None:
    a, g, b = world[A.call], world[G.call], world[B.call]
    await a.set_config({"radio/1/path": "WIDE1-1"})
    g_after, b_after = g.last_packet(), b.last_packet()
    await a.send({"cmd": "beacon_now"})
    await g.until(
        "G hearing A's beacon",
        lambda: any(
            "WIDE1-1" in "".join(p["path"]) for p in g.packets(g_after, direction="in", sender=A.call, kind="position")
        ),
        HEARD_SEC,
    )
    await quiet_on_hf(world, g_after, b_after)


async def test_a_message_to_g_itself_is_acked_by_g_and_not_passed_on(world: World) -> None:
    a, g, b = world[A.call], world[G.call], world[B.call]
    text = "realmodems A to G"
    await a.set_path(G.call, PAIR_CALL)
    g_after, b_after = g.last_packet(), b.last_packet()
    await a.send({"cmd": "send_message", "to": G.call, "text": text})
    await g.until("G receiving the message", lambda: g.message("in", text) is not None, HEARD_SEC)
    await a.until("G's ack at A", lambda: a.state_of(text) == "acked", CROSS_SEC)
    await quiet_on_hf(world, g_after, b_after)


async def test_a_beacon_from_a_with_the_pair_call_in_its_path_is_heard_by_b(world: World) -> None:
    a, b = world[A.call], world[B.call]
    await a.set_config({"radio/1/path": PAIR_CALL})
    after = b.last_packet()
    await a.send({"cmd": "beacon_now"})
    await b.until("B hearing A's beacon over HF", lambda: bool(crossed(b, after, A.call, "position")), CROSS_SEC)


async def test_a_message_at_300_baud_on_hf_reaches_the_other_station_and_its_ack_comes_back(world: World) -> None:
    h1, h2 = world[H1.call], world[H2.call]
    text = "realmodems H1 to H2"
    await h1.send({"cmd": "send_message", "to": H2.call, "text": text})
    await h2.until("H2 receiving the message", lambda: h2.message("in", text) is not None, CROSS_SEC)
    await h1.until("H2's ack at H1", lambda: h1.state_of(text) == "acked", CROSS_SEC)
    assert h2.packets(direction="in", sender=H1.call, kind="message"), "heard on H2's own radio"
    for station in (H1, H2):
        said = (world.folder / station.call.lower() / "neoaprs.log").read_text(encoding="utf-8")
        assert "Channel 0: 300 baud" in said, f"{station.call}'s Direwolf runs its 300 baud modem"
        assert not re.search(r"Line \d+: ", said), f"{station.call}'s Direwolf took the configuration without a word"
