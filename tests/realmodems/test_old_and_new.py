"""Tests for the Mercury pinned now against the one pinned before (neoaprs/mercury.py PREVIOUS_*), the two
on one HF cable: operators run other versions beside ours. A, G and B as in test_digipeating.py, once
with B's daemon on the previous Mercury and once with G's; each time a message crosses from A to B by
way of the pair's call and its ack comes back, and the same from B to A."""

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from neoaprs import mercury
from tests.realmodems.stations import A, B, G, World, exchange, programs, read_machine, refusal

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", loop_scope="module", params=[B.call, G.call], ids=["b-old", "g-old"])
async def world(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> AsyncIterator[World]:
    why = refusal(os.environ, read_machine())
    if why:
        pytest.exit(why, returncode=3)
    missing = [str(p) for p in (*programs(), *programs(previous=True)) if not p.is_file()]
    assert not missing, (
        f"the modems are not built: {missing} (scripts/build-mercury --install and --previous --install)"
    )
    old = str(request.param)
    w = World(Path(tmp_path_factory.mktemp(f"old-{old.lower()}")), (A, G, B), frozenset({old}))
    try:
        bases = await asyncio.to_thread(w.start)
        await w.open(bases)
        for call in (G.call, B.call):
            version = mercury.PREVIOUS_VERSION if call == old else mercury.VERSION
            assert f"Mercury {version} (git" in said(w.folder / call.lower()), f"{call} runs Mercury {version}"
        yield w
    finally:
        w.close_pages()
        await asyncio.to_thread(w.stop)


def said(data: Path) -> str:
    """Everything the station's daemon and its Mercury wrote in its folder."""
    return "".join(f.read_text(encoding="utf-8", errors="replace") for f in sorted(data.rglob("*.log")) if f.is_file())


async def test_a_message_from_a_reaches_b_and_its_ack_comes_back_across_the_two_versions(world: World) -> None:
    await exchange(world, A.call, B.call, f"old and new A to B, {sorted(world.previous)[0]} old")


async def test_a_message_from_b_reaches_a_and_its_ack_comes_back_across_the_two_versions(world: World) -> None:
    await exchange(world, B.call, A.call, f"old and new B to A, {sorted(world.previous)[0]} old")
