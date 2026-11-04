"""The HF radio after its Mercury dies, through the daemon (neoaprs/controller.py, neoaprs/wiring.py, neoaprs/mercurymodem.py): the program is started again on the ports it had, so the HF Tnc, which was told its port when
the radios started, finds the modem where it left it and the radio comes back by itself; and when something else took that pair while the modem was down, the modem takes another and the controller points the HF Tnc at
it (`Mercury.ports_changed`, wired to `repoint_hf`). Before this the relaunch took the next free pair every time (the old one looked busy with its connections in TIME_WAIT) and the Tnc waited on the dead port for ever."""
import random
import socket
from pathlib import Path

import pytest

from neoaprs import mercurymodem
from neoaprs.mercury import BROADCAST_PORT
from neoaprs.mercuryhelper import PORT_TRIES, free_ports
from neoaprs.source import Backoff, Source
from tests.support import fakemercury
from tests.support.env import Env, until


@pytest.fixture(autouse=True)
def _ports_of_this_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test asks the modem for free ports from a base of its own, so that two tests side by side (pytest-xdist) do not both find 8100 free between the probe and the bind."""
    base = random.randrange(20000, 40000, 500)             # (every port of the pair, and the UI port 2000 above, stays under 49152: Windows hands out and reserves the ports above it, and a base there found no free pair on CI's Windows runner)
    monkeypatch.setattr(mercurymodem, "free_ports", lambda first=BROADCAST_PORT, tries=PORT_TRIES: free_ports(base, tries))


async def hf_station(tmp_path: Path, backoff: Backoff) -> Env:
    e = Env(tmp_path, settings={"hf/enabled": "true"})
    e.ctl.mercury._finder = fakemercury.program
    e.ctl.mercury.backoff = backoff
    e.ctl.mercury._control_backoff = Backoff([0.05, 0.05])
    e.hf.backoff = Backoff([0.05, 0.1])
    await e.start()
    await until(lambda: e.ctl.mercury.running and e.hf.usable, 5.0)
    return e


def kill(e: Env) -> None:
    process = e.ctl.mercury._program._process
    assert process is not None
    process.kill()


async def test_after_mercury_dies_the_hf_radio_comes_back_on_the_same_ports_by_itself(tmp_path: Path) -> None:
    e = await hf_station(tmp_path, Backoff([0.1, 0.1]))
    try:
        port, pid = e.hf.port, e.ctl.mercury.pid
        kill(e)
        await until(lambda: e.ctl.mercury.state == "waiting" and e.hf.state is not Source.State.CONNECTED, 5.0)
        assert not e.hf.usable, "while the modem is down the radio does not say it listens"
        await until(lambda: e.ctl.mercury.starts == 2 and e.ctl.mercury.running and e.hf.usable, 5.0)
        assert e.hf.port == port == f"socket://127.0.0.1:{e.ctl.mercury.broadcast_port}" and e.ctl.mercury.pid != pid
    finally:
        await e.stop()


async def test_when_the_pair_was_taken_meanwhile_the_hf_radio_is_pointed_at_the_new_one(tmp_path: Path) -> None:
    e = await hf_station(tmp_path, Backoff([1.0, 1.0]))
    try:
        old = e.ctl.mercury.broadcast_port
        kill(e)
        await until(lambda: e.ctl.mercury.state == "waiting", 5.0)
        with socket.socket() as holder:
            holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            holder.bind(("127.0.0.1", old))
            holder.listen()
            await until(lambda: e.ctl.mercury.starts == 2 and e.ctl.mercury.running, 5.0)
            new = e.ctl.mercury.broadcast_port
            assert new != old
            await until(lambda: e.hf.port == f"socket://127.0.0.1:{new}" and e.hf.usable, 5.0)
    finally:
        await e.stop()
