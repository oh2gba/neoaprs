"""The scripts that talk to a daemon's page against a real daemon of this tree, over its page's socket: scripts/smoke.py's readers (which update-e2e, install-probe, mercury-sim and the screenshots take) and
tests/support/realmercury.Page (the Mercury bench's and the simulation's page) find the wire of the radios that the hello names, read the radios, what a station's row says each kind heard and a radio's own
settings in `radio_values`, and give the HF radio by the radio commands. tests/test_scripts.py holds the same pieces on stand-ins of both wires; this file holds them to the daemon they are run against."""
import asyncio
from dataclasses import replace
from pathlib import Path
from typing import Any

from neoaprs.radiospec import FM_ID, HF_ID
from tests.support.env import Env
from tests.support.realmercury import Page
from tests.support.wireworld import heard
from tests.test_scripts import load_script


async def closed(connection: Any) -> None:
    """A client socket closed and read to its end, so that its reading loop is over before the test ends."""
    connection.close()
    while await asyncio.wait_for(connection.read_message(), 5) is not None:
        pass


async def test_the_scripts_read_the_radios_of_the_daemon_and_give_it_the_hf_radio_by_the_radio_commands(tmp_path: Path) -> None:
    smoke = load_script("smoke.py")
    e = Env(tmp_path, web=True)
    e.ctl.mercury._finder = lambda: None                                         # (no program: the Dummy HF radio works without its speaker)
    await e.start()
    base = f"http://127.0.0.1:{e.port}/"
    page = await smoke.PageSocket.open(base)
    try:
        assert page.wire == "radios", "the hello names the topic radios"
        await page.until("the FM radio connected", lambda p: smoke.radio_state(p.topics, "fm") == "connected", 10)
        assert smoke.radio_of(page.topics, "fm")["id"] == FM_ID and smoke.radio_of(page.topics, "hf") is None, "radio 1 on, the HF radio off as the defaults have it"
        e.ctl.stationbook.take(replace(heard("!6010.00N/02456.00E>near", "OH2XYZ", at=e.ctl.clock()), radio_id=FM_ID))
        await page.until("the station told", lambda p: "OH2XYZ" in (p.topics.get("stations") or {}), 10)
        row = {k: v for k, v in page.topics["stations"]["OH2XYZ"].items() if k not in ("heard_fm", "heard_hf")}       # (the old fields, equal to the new until W3, would hide a reader that ignored `heard`)
        assert (smoke.heard_on(page.topics, row, "fm"), smoke.heard_on(page.topics, row, "hf")) == (1, 0), "the row's heard by radio, counted by the kinds of the topic radios"
        assert await smoke.give_radio(page, "hf", "dummy-hf", {"beacon": "false"}, 20) == HF_ID, "radio 2, changed to the Dummy HF radio and switched on"
        await page.until("the HF radio connected", lambda p: smoke.radio_state(p.topics, "hf") == "connected", 20)
        assert page.config()["radio/2/beacon"] == "false" and "radio/2/beacon" not in page.topics["config"]["values"], "its own key told in radio_values, not in the form's values"
        spec = e.ctl.config.radio(HF_ID)
        assert spec is not None and (spec.type, spec.enabled) == ("dummy-hf", True)
        assert smoke.modem_state(page.topics, "hf", HF_ID) is None, "the Dummy HF radio has no modem"
    finally:
        await closed(page.connection)
    bench = Page("bench")
    await bench.open(base)
    try:
        await bench.until("the radios told", lambda: bench.fm_connected() and bench.radio("hf").get("state") == "connected", 10)
        assert (bench.radio("fm")["id"], bench.radio("hf")["id"], bench.modem(), bench.ready()) == (FM_ID, HF_ID, {}, False), "the bench's page reads the same radios; no modem, so not ready for a Mercury test"
    finally:
        bench.close()
        await closed(bench._connection)
    await e.stop()
