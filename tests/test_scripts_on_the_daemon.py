"""The scripts that talk to a daemon's page against a real daemon over its page socket:
scripts/smoke.py's readers and tests/support/realmercury.Page find the radios wire the hello names
and read the radios and rows.
"""
import asyncio
import importlib.machinery
import importlib.util
from dataclasses import replace
from pathlib import Path
from typing import Any

from neoaprs.radiospec import FM_ID, HF_ID
from neoaprs.source import Source
from neoaprs.web.protocol import TOPIC_NAMES
from tests.support.air import on_air
from tests.support.env import Env, until
from tests.support.realmercury import Page
from tests.support.wireworld import heard
from tests.test_scripts import ROOT, load_script


async def closed(connection: Any) -> None:
    """A client socket closed and read to its end, so that its reading loop is over before the test
    ends."""
    connection.close()
    while await asyncio.wait_for(connection.read_message(), 5) is not None:
        pass


async def test_the_scripts_read_the_radios_of_the_daemon_and_give_it_the_hf_radio_by_the_radio_commands(tmp_path: Path) -> None:
    smoke = load_script("smoke.py")
    e = Env(tmp_path, web=True)
    # No program: the Dummy HF radio works without its speaker
    e.mercury._finder = lambda: None
    await e.start()
    base = f"http://127.0.0.1:{e.port}/"
    page = await smoke.PageSocket.open(base)
    try:
        assert page.wire == "radios", "the hello names the topic radios"
        await page.until("the FM radio connected", lambda p: smoke.radio_state(p.topics, "fm") == "connected", 10)
        assert smoke.radio_of(page.topics, "fm")["id"] == FM_ID and smoke.radio_of(page.topics, "hf") is None, "radio 1 on, the HF radio off as the defaults have it"
        e.ctl.stationbook.take(replace(heard("!6010.00N/02456.00E>near", "OH2XYZ", at=e.ctl.clock()), radio_id=FM_ID))
        await page.until("the station told", lambda p: "OH2XYZ" in (p.topics.get("stations") or {}), 10)
        row = page.topics["stations"]["OH2XYZ"]
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


def sim_radios() -> Any:
    loader = importlib.machinery.SourceFileLoader("sim_radios", str(ROOT / "scripts" / "sim-radios"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    sim = importlib.util.module_from_spec(spec)
    loader.exec_module(sim)
    return sim


def told_radios(page: Any) -> list[tuple[int, str, str, bool]]:
    return sorted((int(id), row["kind"], row["type"], bool(row["enabled"])) for id, row in (page.topics.get("radios") or {}).items() if not row.get("removed"))


async def test_on_a_new_installations_daemon_the_install_probe_and_sim_radios_add_each_radio_they_need_the_first_as_radio_1(tmp_path: Path) -> None:
    probe, sim = load_script("install-probe.py"), sim_radios()
    for name, give, expected in (
            ("probe", lambda page: probe.give_radios(page, 20), [(1, "fm", probe.FM_TYPE, True), (2, "hf", probe.HF_TYPE, True)]),
            ("sim", lambda page: sim.make_six(page, 20), [(id, kind, type, True) for id, (kind, type) in enumerate(sim.SIX, 1)])):
        # A new installation: no settings row and no radio
        e = Env(tmp_path / name, radio=False, web=True, operator=False, first_radio=False)
        e.mercury._finder = lambda: None
        await e.start(connected=False)
        page = await sim.smoke.PageSocket.open(f"http://127.0.0.1:{e.port}/")
        try:
            await page.until("every topic told", lambda p: set(TOPIC_NAMES) <= set(p.topics), 10)
            assert told_radios(page) == [] and e.ctl.config.radios == (), "a new installation has no radio"
            ids = await give(page)
            if name == "sim":
                assert ids == [1, 2, 3, 4, 5, 6], "each of the six added, numbered by the database in the order of their boxes"
            await page.until("the radios told", lambda p, expected=expected: told_radios(p) == expected, 10)
            assert [(s.id, s.kind, s.type, s.enabled) for s in e.ctl.config.radios] == expected, name
        finally:
            await closed(page.connection)
            await e.stop()


async def test_the_smoke_test_gives_a_new_installation_its_first_radio_which_takes_the_port_of_the_run_and_hears_the_fake_tnc(tmp_path: Path) -> None:
    smoke = load_script("smoke.py")
    # A new installation, started with --port: the fake TNC, which no radio takes yet
    e = Env(tmp_path, web=True, operator=False, first_radio=False)
    await e.start(connected=False)
    try:
        assert e.ctl.config.radios == ()
        opened: list[Any] = []
        real_open = smoke.PageSocket.open

        async def open_and_keep(base: str) -> Any:
            opened.append(await real_open(base))
            return opened[-1]

        # The socket the smoke test opens, read to its end after it
        smoke.PageSocket.open = open_and_keep
        watch = asyncio.create_task(smoke.watch_the_socket(f"http://127.0.0.1:{e.port}/", 20))
        await until(lambda: e.ctl.radios.get(FM_ID) is not None and e.tnc.state is Source.State.CONNECTED, 20)
        e.feed(on_air("OH2RDG", b"!6010.00N/02456.00E>heard by the smoke test"))
        state, packets = await watch
        await closed(opened[0].connection)
        assert (state, packets) == ("connected", 1)
        spec = e.ctl.config.radio(FM_ID)
        assert spec is not None and (spec.kind, spec.type, spec.enabled) == ("fm", smoke.FIRST_RADIO, True), "radio 1, the type the setup guide gives first, on the port of the run"
    finally:
        await e.stop()
