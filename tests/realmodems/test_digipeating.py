"""Tests for a gateway's pair through the real modems: A (Direwolf) and G share the VHF cable, G (Direwolf
and Mercury, its pair on) and B (Mercury) the HF cable. Messages and acks cross both ways, a WIDE path
alone and a message to G itself stay off HF, and a beacon by way of the pair's call reaches B."""

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from tests.realmodems.stations import A, B, G, PAIR_CALL, StationPage, World, programs, read_machine, refusal

pytestmark = pytest.mark.asyncio(loop_scope="module")

CROSS_SEC = 240.0  # a message and its ack: two Mercury frames of about 4 s each, and the retries' pauses
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


def crossed(page: StationPage, after: int, sender: str, kind: str) -> list[dict[str, object]]:
    """The packets of `sender` this station heard after `after` that came by way of the pair's call."""
    return [p for p in page.packets(after, direction="in", sender=sender, kind=kind) if f"{PAIR_CALL}*" in p["path"]]


async def exchange(world: World, sender: str, addressee: str, text: str) -> None:
    """`sender` sends `text` to `addressee` by way of the pair's call; it arrives and its ack comes back."""
    page, far = world[sender], world[addressee]
    await page.set_path(addressee, PAIR_CALL)
    after = far.last_packet()
    await page.send({"cmd": "send_message", "to": addressee, "text": text})
    await far.until(f"{addressee} receiving {text!r}", lambda: far.message("in", text) is not None, CROSS_SEC)
    await page.until(f"the ack of {text!r} at {sender}", lambda: page.state_of(text) == "acked", CROSS_SEC)
    assert crossed(far, after, sender, "message"), "the message came over the gateway's pair"


async def test_a_message_from_a_reaches_b_over_mercury_and_bs_ack_comes_back(world: World) -> None:
    await exchange(world, A.call, B.call, "realmodems A to B")
    acks = [p for p in world[A.call].packets(direction="in", sender=B.call) if ":ack" in str(p["tnc2"])]
    assert acks and f"{PAIR_CALL}*" in acks[-1]["path"], "B's ack came back by way of the pair's call"


async def test_a_message_from_b_reaches_a_over_the_gateway_and_as_ack_comes_back(world: World) -> None:
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
