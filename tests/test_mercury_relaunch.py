"""The HF radio after its Mercury dies, through the daemon: the program is started again on the
ports it had and the radio comes back; if something else took the pair meanwhile, the modem gets
another pair.
"""

import socket
import sys
from pathlib import Path

import pytest

from neoaprs.claims import Claim, Claims
from neoaprs.source import Backoff, Source
from tests.support import fakemercury
from tests.support.env import Env, until_started
from tests.support.modemports import own_ports


@pytest.fixture(autouse=True)
def _ports_of_this_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test asks the modem for free ports from a base of its own (tests/support/modemports.py):
    no other test running beside it is handed its ports."""
    own_ports(monkeypatch)


async def hf_station(tmp_path: Path, backoff: Backoff) -> Env:
    e = Env(tmp_path, settings={"hf/enabled": "true"})
    e.mercury._finder = fakemercury.program
    e.mercury.claims = Claims()
    e.mercury.backoff = backoff
    e.mercury._control_backoff = Backoff([0.05, 0.05])
    e.hf.backoff = Backoff([0.05, 0.1])
    await e.start()
    await until_started(lambda: e.mercury.running and e.hf.usable)
    return e


def pairs(e: Env) -> list[Claim]:
    claims = e.mercury.claims
    assert claims is not None
    return [c for c in claims.all() if c.kind == "modem_ports"]


def kill(e: Env) -> None:
    process = e.mercury._program._process
    assert process is not None
    process.kill()


async def test_after_mercury_dies_the_hf_radio_comes_back_on_the_same_ports_by_itself(tmp_path: Path) -> None:
    # (on Windows a second, not a tenth: it keeps the port of a process that was killed for a
    # moment, and a modem started into that moment ends on "address in use" and comes back on a
    # later start than the one counted here)
    e = await hf_station(tmp_path, Backoff([1.0, 1.0] if sys.platform == "win32" else [0.1, 0.1]))
    try:
        port, pid = e.hf.port, e.mercury.pid
        held = pairs(e)
        assert held == [Claim("modem_ports", str(e.mercury.broadcast_port), e.mercury.holder)]
        kill(e)
        await until_started(lambda: e.mercury.state == "waiting" and e.hf.state is not Source.State.CONNECTED)
        assert not e.hf.usable, "while the modem is down the radio does not say it listens"
        assert pairs(e) == held, "the pair stays the radio's while its program is down"
        await until_started(lambda: e.mercury.starts == 2 and e.mercury.running and e.hf.usable)
        assert (
            e.hf.port == port == f"socket://127.0.0.1:{e.mercury.broadcast_port}"
            and e.mercury.pid != pid
            and pairs(e) == held
        )
    finally:
        await e.stop()


async def test_when_the_pair_was_taken_meanwhile_the_hf_radio_is_pointed_at_the_new_one(tmp_path: Path) -> None:
    # The back-off is the time the test has to take the port: a machine that stalls for a second
    # does not end it
    e = await hf_station(tmp_path, Backoff([4.0, 4.0]))
    try:
        old = e.mercury.broadcast_port
        kill(e)
        await until_started(lambda: e.mercury.state == "waiting")
        with socket.socket() as holder:
            holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            holder.bind(("127.0.0.1", old))
            holder.listen()
            await until_started(lambda: e.mercury.starts == 2 and e.mercury.running)
            new = e.mercury.broadcast_port
            assert new != old and pairs(e) == [Claim("modem_ports", str(new), e.mercury.holder)], (
                "the new pair is held in the place of the old"
            )
            await until_started(lambda: e.hf.port == f"socket://127.0.0.1:{new}" and e.hf.usable)
    finally:
        await e.stop()


async def test_a_start_refused_before_its_ports_were_chosen_gives_the_hf_radio_no_port_and_the_start_tried_again_points_it_at_them(
    tmp_path: Path,
) -> None:
    """The card the HF radio is set to is another radio's: its start is refused before it chose its
    ports, and the port it stood on (8100) may be another radio's modem or another program's, so its
    line has none and says why. Once the card is let go, the start tried again chooses its pair and
    the line is pointed at it (`ports_changed`)."""
    card = "plughw:CARD=CODEC,DEV=0"
    e = Env(tmp_path, settings={"hf/enabled": "true", "mercury/sound_card": card, "mercury/keying": "vox"})
    e.mercury._finder = fakemercury.program
    claims = e.mercury.claims = Claims()
    claims.hold(Claim("sound_card", card, 5))
    e.mercury.backoff = Backoff([0.3, 0.3])
    e.mercury._control_backoff = Backoff([0.05, 0.05])
    e.hf.backoff = Backoff([0.05, 0.1])
    await e.start(connected=False)
    try:
        await until_started(lambda: e.mercury.state == "waiting" and "is held by" in e.mercury.problem)
        assert e.hf.port == "" and e.hf.stats.opens == 0 and not e.mercury.ports_chosen, (
            "no port before the modem chose its pair"
        )
        claims.release(5, "sound_card")
        await until_started(
            lambda: e.mercury.running and e.hf.port == f"socket://127.0.0.1:{e.mercury.broadcast_port}" and e.hf.usable
        )
    finally:
        await e.stop()
