"""The code beside the Mercury modem's problem (`Mercury.reason`): the English `problem` is the log's and the doctor's, the page puts the reason in its own words in the viewer's language; the code is empty
unless the modem is waiting, and it is what the hf topic's `modem.reason` tells."""
import random
from pathlib import Path

import pytest

from neoaprs import mercurymodem
from neoaprs.mercury import BROADCAST_PORT
from neoaprs.mercuryhelper import PORT_TRIES, free_ports
from neoaprs.mercurymodem import NOT_INSTALLED, OPEN_TO_NETWORK, REASONS, Mercury
from neoaprs.source import Backoff
from neoaprs.web.tncwire import ModemState
from tests.support import fakemercury
from tests.support.env import until_started
from tests.test_mercury_modem import HF, QUICK, modem, stopped


@pytest.fixture(autouse=True)
def _ports_of_this_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test asks for free ports from a base of its own (two tests side by side do not both find 8100 free)."""
    base = random.randrange(20000, 40000, 500)             # (every port of the pair, and the UI port 2000 above, stays under 49152: Windows hands out and reserves the ports above it, and a base there found no free pair on CI's Windows runner)
    monkeypatch.setattr(mercurymodem, "free_ports", lambda first=BROADCAST_PORT, tries=PORT_TRIES: free_ports(base, tries))


def test_the_codes_of_the_modem_are_the_codes_of_the_wire() -> None:
    assert set(REASONS) == set(ModemState.model_fields["reason"].annotation.__args__)    # type: ignore[union-attr]
    assert Mercury(Path("."), finder=lambda: None).reason == ""


async def test_a_program_that_is_not_installed_is_not_installed(tmp_path: Path) -> None:
    m = modem(tmp_path, program=False)
    await m.start(HF)
    assert (m.state, m.problem, m.reason) == ("waiting", NOT_INSTALLED, "not_installed")
    await stopped(m)
    assert (m.state, m.reason) == ("stopped", "")


async def test_a_program_that_dies_is_stopped_while_it_waits_and_nothing_once_it_runs_again(tmp_path: Path) -> None:
    m = Mercury(tmp_path, finder=lambda: fakemercury.program(die_after_sec=1.5), backoff=QUICK, control_backoff=Backoff([0.05, 0.05]))
    seen: list[tuple[str, str]] = []
    m.changed.connect(lambda: seen.append((m.state, m.reason)))
    await m.start(HF)
    try:
        await until_started(lambda: m.state == "waiting")
        assert m.problem.startswith("Mercury stopped") and m.reason == "stopped"
        await until_started(lambda: m.state == "running")
        assert m.reason == ""
        assert ("waiting", "stopped") in seen and all(reason == "" for state, reason in seen if state != "waiting")
    finally:
        await stopped(m)


async def test_a_program_that_listens_on_the_network_is_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mercurymodem, "foreign_listeners", lambda ports: ["00000000:8100"])
    m = modem(tmp_path)
    await m.start(HF)
    try:
        await until_started(lambda: m.state == "waiting")
        assert (m.problem, m.reason) == (OPEN_TO_NETWORK, "network")
    finally:
        await stopped(m)


async def test_no_free_port_is_no_port(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def none_free(first: int = BROADCAST_PORT, tries: int = PORT_TRIES) -> list[int]:
        raise OSError("no pair of ports is free")

    monkeypatch.setattr(mercurymodem, "free_ports", none_free)
    m = modem(tmp_path)
    await m.start(HF)
    assert (m.state, m.reason) == ("waiting", "no_port") and m.problem.startswith("no free port for Mercury")
    await stopped(m)


async def test_a_program_that_cannot_be_started_is_not_started(tmp_path: Path) -> None:
    m = Mercury(tmp_path, finder=lambda: [str(tmp_path / "no-such-mercury")], backoff=QUICK, control_backoff=Backoff([0.05, 0.05]))
    m.ports = lambda: []                                                  # (never the operator's serial ports)
    await m.start(HF)
    try:
        await until_started(lambda: m.state == "waiting")
        assert m.reason == "not_started" and m.problem.startswith("Mercury could not be started")
    finally:
        await stopped(m)
