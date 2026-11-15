"""The FM radio on a KISS server over TCP (a Direwolf on `socket://127.0.0.1:8001`, the setting `serial/port`) and the HF radio ticked with the Mercury type: the address in `serial/port` is the FM radio's and is never
taken for a Mercury that something else runs, so the daemon starts a Mercury of its own for the HF radio (the program that stands in for it, tests/support/fakemercury.py) and the HF Tnc connects to that one's broadcast
port, not to the Direwolf; only a port given for the run (`--hf-port`) is a Mercury something else runs (tests/test_mercury_modem.py)."""
from pathlib import Path

import pytest

from neoaprs import ax25, kiss
from neoaprs.mercurydriver import MercuryDriver
from neoaprs.radiospec import FM_ID, HF_ID
from neoaprs.source import Backoff
from neoaprs.tncdriver import TncDriver
from tests.support import fakemercury
from tests.support.env import Env, idle_for, until
from tests.support.fakeradio import FakeRadio
from tests.support.modemports import own_ports


@pytest.fixture(autouse=True)
def _ports_of_this_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test asks the modem for free ports from a base of its own (tests/support/modemports.py): no other test running beside it is handed its ports."""
    own_ports(monkeypatch)


async def test_the_fm_radios_kiss_over_tcp_address_is_not_taken_for_a_mercury_something_else_runs(tmp_path: Path) -> None:
    direwolf = FakeRadio()                                                  # the FM radio: a KISS server, as a Direwolf is
    await direwolf.start()
    e = Env(tmp_path, radio=False, settings={"tnc/profile": "kiss-tcp", "serial/port": direwolf.url, "hf/enabled": "true"})
    e.mercury._finder = fakemercury.program
    e.mercury.backoff = Backoff([0.1, 0.1])
    e.mercury._control_backoff = Backoff([0.05, 0.05])
    e.hf.backoff = Backoff([0.05, 0.1])                                   # (the HF Tnc may knock before the program listens: its retry is to come within the test's budget, not after the daemon's 5 s)
    try:
        await e.start()
        await until(lambda: e.mercury.running and e.hf.usable and e.tnc.usable, 15.0)
        mercury = e.mercury
        assert mercury.attached == "" and mercury.starts == 1, "a Mercury of ours was started, none was attached to"
        assert e.tnc.port == direwolf.url, "the FM radio is the Direwolf"
        assert e.hf.port != direwolf.url and mercury.broadcast_port != direwolf.port
        assert e.hf.port == f"socket://127.0.0.1:{mercury.broadcast_port}", "the HF radio is the Mercury we started"
        fm, hf = e.ctl.radios.all()
        assert (fm.rtype.key, fm.rtype.transport, type(fm.driver), fm.line.port) == ("kiss-tcp", "tcp", TncDriver, direwolf.url), "radio 1: its driver gave its line the address of its own setting"
        assert (hf.rtype.key, type(hf.driver), hf.driver.modem, hf.line.port) == ("mercury", MercuryDriver, mercury, e.hf.port), "radio 2: its driver started its own modem and pointed its line at it"
        assert e.ctl.run.hf_port == "" and e.ctl.run.port == "", "nothing was given for the run: the address is the setting of radio 1"
        direwolf.feed(kiss.encode(ax25.encode(ax25.Frame(ax25.Address("APRS"), ax25.Address.parse("OH2XYZ-7"), (), info=b"!6010.00N/02456.00E>hello"))))
        await until(lambda: e.ctl.stationbook.get("OH2XYZ-7") is not None)
        await idle_for(0.3)                                                 # (the time a second copy, from the HF Tnc, would have had to arrive)
        station = e.ctl.stationbook.get("OH2XYZ-7")
        assert station is not None and (station.heard_on(FM_ID).count, station.heard_on(HF_ID).count) == (1, 0), "heard once, on FM"
        assert [(p.source, p.radio_id) for p in await e.packets()] == [("OH2XYZ-7", FM_ID)]
    finally:
        await e.stop()
        await direwolf.aclose()
