"""The FM radio on a KISS server over TCP (a Direwolf on `socket://127.0.0.1:8001`, the setting `serial/port`) and the HF radio ticked with the Mercury type: the address in `serial/port` is the FM radio's and is never
taken for a Mercury that something else runs, so the daemon starts a Mercury of its own for the HF radio (the program that stands in for it, tests/support/fakemercury.py) and the HF Tnc connects to that one's broadcast
port, not to the Direwolf; only a port given for the run (`--hf-port`) is a Mercury something else runs (tests/test_mercury_modem.py)."""
import random
from pathlib import Path

import pytest

from neoaprs import ax25, kiss, mercurymodem
from neoaprs.mercury import BROADCAST_PORT
from neoaprs.mercuryhelper import PORT_TRIES, free_ports
from neoaprs.source import Backoff
from tests.support import fakemercury
from tests.support.env import Env, idle_for, until
from tests.support.fakeradio import FakeRadio


@pytest.fixture(autouse=True)
def _ports_of_this_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test asks the modem for free ports from a base of its own, so that two tests side by side (pytest-xdist) do not both find 8100 free between the probe and the bind."""
    base = random.randrange(20000, 60000, 500)
    monkeypatch.setattr(mercurymodem, "free_ports", lambda first=BROADCAST_PORT, tries=PORT_TRIES: free_ports(base, tries))


async def test_the_fm_radios_kiss_over_tcp_address_is_not_taken_for_a_mercury_something_else_runs(tmp_path: Path) -> None:
    direwolf = FakeRadio()                                                  # the FM radio: a KISS server, as a Direwolf is
    await direwolf.start()
    e = Env(tmp_path, radio=False, settings={"tnc/profile": "kiss-tcp", "serial/port": direwolf.url, "hf/enabled": "true"})
    e.ctl.mercury._finder = fakemercury.program
    e.ctl.mercury.backoff = Backoff([0.1, 0.1])
    e.ctl.mercury._control_backoff = Backoff([0.05, 0.05])
    e.hf.backoff = Backoff([0.05, 0.1])                                   # (the HF Tnc may knock before the program listens: its retry is to come within the test's budget, not after the daemon's 5 s)
    try:
        await e.start()
        await until(lambda: e.ctl.mercury.running and e.hf.usable and e.tnc.usable, 15.0)
        mercury = e.ctl.mercury
        assert mercury.attached == "" and mercury.starts == 1, "a Mercury of ours was started, none was attached to"
        assert e.tnc.port == direwolf.url, "the FM radio is the Direwolf"
        assert e.hf.port != direwolf.url and mercury.broadcast_port != direwolf.port
        assert e.hf.port == f"socket://127.0.0.1:{mercury.broadcast_port}", "the HF radio is the Mercury we started"
        direwolf.feed(kiss.encode(ax25.encode(ax25.Frame(ax25.Address("APRS"), ax25.Address.parse("OH2XYZ-7"), (), info=b"!6010.00N/02456.00E>hello"))))
        await until(lambda: e.ctl.stationbook.get("OH2XYZ-7") is not None)
        await idle_for(0.3)                                                 # (the time a second copy, from the HF Tnc, would have had to arrive)
        station = e.ctl.stationbook.get("OH2XYZ-7")
        assert station is not None and (station.heard_fm, station.heard_hf) == (1, 0), "heard once, on FM"
        assert [(p.source, p.radio) for p in await e.packets()] == [("OH2XYZ-7", "fm")]
    finally:
        await e.stop()
        await direwolf.aclose()
