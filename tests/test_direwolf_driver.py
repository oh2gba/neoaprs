"""A radio of the Sound card type in the daemon (neoaprs/direwolfdriver.py, the registry's "direwolf" driver), against the made-up Direwolf of tests/support/fakedirewolf.py: the driver starts Direwolf and then the
line to its KISS port, a frame of ours goes out keyed and the frame heard comes back as a packet, with its level in the radio's row; a change of the card or the keying restarts the radio and the transmit level does
not; the radio's row says the Mercury modem holds its card, with the holder's name; on the wire the type is offered, added and refused where its program is not carried, and Tune on it is refused while it is not
running; and under the no-devices switch no Direwolf is started and its line has no port."""
import asyncio
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import TypeAdapter

from neoaprs import direwolfmodem, nodevices, radioregistry, radiotypes
from neoaprs.claims import Claim, Claims
from neoaprs.clock import utcnow
from neoaprs.config import DEFAULTS
from neoaprs.direwolf import CONF_FILE, PID_FILE, PROFILE, adevice
from neoaprs.direwolfdriver import DirewolfDriver
from neoaprs.mercury import Keying, SerialPort
from neoaprs.mercuryclaims import radio_folder
from neoaprs.radiodriver import RunOverrides
from neoaprs.radioregistry import make_driver
from neoaprs.radiospec import RadioSpec
from neoaprs.source import Backoff, Source
from neoaprs.tnc import Tnc
from neoaprs.web.radioview import radio_row
from neoaprs.web.tncwire import RadioRow
from tests.support import fakedirewolf, fakemercury
from tests.support.fakedriver import with_radios
from tests.support.env import until, until_started
from tests.support.modemports import base_of_this_test
from tests.test_no_devices import under_the_switch  # noqa: F401  (the fixture)
from tests.test_radios_wire import added, refused, started
from tests.test_tnc import ui_frame

CARD = "plughw:1,0"
SETTINGS = {"sound_card": CARD, "keying": "vox", "tx_gain_db": "0", "beacon": "true", "path": "", "digipeat": "false"}
ROW = TypeAdapter(RadioRow)


@pytest.fixture(autouse=True)
def _ports_of_this_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(direwolfmodem, "FIRST_PORT", base_of_this_test())
    monkeypatch.setattr(direwolfmodem, "_numbers_of", lambda name: (1, 1))    # (Windows: the made-up cards are the second input and output of the made-up Direwolf's WinMM lists, test_direwolf_modem.py)


def spec(id: int = 3, **settings: str) -> RadioSpec:
    return RadioSpec(id, "fm", "direwolf", "", True, id, settings={**SETTINGS, **settings})


def driver_of(tmp_path: Path, claims: Claims | None = None, radio: RadioSpec | None = None) -> DirewolfDriver:
    radio = radio if radio is not None else spec()
    driver = make_driver(radio, claims if claims is not None else Claims(), utcnow, tmp_path)
    assert isinstance(driver, DirewolfDriver)
    driver.modem._finder, driver.modem._lister, driver.modem.backoff = fakedirewolf.program, fakemercury.program, Backoff([0.1, 0.1])     # (the made-up programs in the place of the shipped ones)
    driver.modem.ports = lambda: []
    driver.line.backoff = Backoff([0.05, 0.05])
    driver.configure(radio, DEFAULTS, RunOverrides(check_sec=0.0))
    return driver


async def test_the_driver_starts_direwolf_then_its_line_and_a_frame_of_ours_goes_out_and_the_frame_heard_comes_back_with_its_level(tmp_path: Path) -> None:
    claims = Claims()
    driver = driver_of(tmp_path, claims)
    assert driver.line.profile is PROFILE and driver.line.modem is driver.modem and driver.line.radio_id == 3
    await driver.start()
    await until_started(lambda: driver.line.state is Source.State.CONNECTED)
    assert driver.line.path == f"socket://127.0.0.1:{driver.modem.kiss_port}" and driver.line.describe().startswith("Direwolf AFSK1200, listening")
    heard: list[str] = []
    driver.line.packet.connect(lambda packet: heard.append(packet.direction))
    assert driver.line.send_frame(ui_frame())
    await until(lambda: "in" in heard and driver.modem.rx_level == 48)
    row = radio_row(spec(), (spec(),), SimpleNamespace(line=driver.line, beacon=None), claims)
    assert row is not None and ROW.validate_python(row)
    assert (row["modem"]["mode"], row["modem"]["rx_level"], row["modem"]["frames_keyed"], row["can"]["rx_level"], row["problem"]) == ("AFSK1200", 48, 1, True, None)
    assert {h["resource"] for h in row["holds"]} == {"sound_card", "modem_ports"} and driver.held() == [c for c in claims.all() if c.holder == 3]
    await driver.stop()
    assert driver.line.state is Source.State.STOPPED and driver.modem.state == "stopped" and claims.all() == ()


async def test_two_sound_card_radios_side_by_side_each_run_their_own_direwolf_from_their_own_folder_and_neither_ends_the_other(tmp_path: Path) -> None:
    claims = Claims()
    attic, shack = driver_of(tmp_path, claims, spec(3)), driver_of(tmp_path, claims, spec(4, sound_card="plughw:2,0"))
    assert (attic.modem.home, shack.modem.home) == (radio_folder(tmp_path, 3), radio_folder(tmp_path, 4)), "each radio's configuration and process id in its own folder, radios/<id>"
    try:
        await attic.start()
        await until_started(lambda: attic.line.state is Source.State.CONNECTED)
        first = attic.modem.pid
        await shack.start()
        await until_started(lambda: shack.line.state is Source.State.CONNECTED)
        await asyncio.sleep(0.5)                                     # (the time a Direwolf ended by the other's start would take to be started again after its back-off)
        assert (attic.modem.state, attic.modem.pid, shack.modem.state) == ("running", first, "running"), "the second radio's start ended no Direwolf of the first"
        assert attic.modem.kiss_port != shack.modem.kiss_port
        for driver, card in ((attic, CARD), (shack, "plughw:2,0")):
            assert f"ADEVICE {adevice(card, driver.modem._numbers)}\n" in (driver.modem.home / CONF_FILE).read_text(encoding="utf-8") and (driver.modem.home / PID_FILE).read_text(encoding="ascii").strip() == str(driver.modem.pid)
        assert not (tmp_path / CONF_FILE).exists() and not (tmp_path / PID_FILE).exists(), "nothing of a Direwolf in the data folder itself"
    finally:
        await attic.stop()
        await shack.stop()


def test_a_change_of_the_card_or_the_keying_restarts_the_radio_and_the_transmit_level_does_not(tmp_path: Path) -> None:
    driver = driver_of(tmp_path)
    key = driver.restart_key(spec(), DEFAULTS, RunOverrides())
    assert driver.restart_key(spec(tx_gain_db="-6"), DEFAULTS, RunOverrides()) == key
    assert driver.restart_key(spec(sound_card="plughw:CARD=Device,DEV=0"), DEFAULTS, RunOverrides()) != key and driver.restart_key(spec(keying="cm108"), DEFAULTS, RunOverrides()) != key
    assert "Direwolf on the sound card plughw:1,0, keyed by vox" in driver.words(spec(), DEFAULTS, RunOverrides())
    driver.modem.state, driver.modem.sound_card = "running", CARD
    chose = replace(spec(), settings={**SETTINGS, "sound_card": ""})
    assert driver.made_explicit(chose, spec()).value("sound_card") == CARD, "storing the card the running modem chose is no reason to restart it"


def test_the_row_of_a_sound_card_radio_on_the_card_the_hf_modem_holds_says_so_with_the_holder(tmp_path: Path) -> None:
    claims = Claims()
    claims.hold(Claim("sound_card", CARD, 2))
    hf = RadioSpec(2, "hf", "mercury", "", True, 2, settings={"sound_card": CARD, "keying": "vox", "tx_gain_db": "0", "beacon": "true"})
    row = radio_row(spec(), (hf, spec()), SimpleNamespace(line=Tnc(profile=PROFILE), beacon=None), claims)
    assert row is not None and row["problem"] == {"code": "radio.resource_held", "params": {"resource": "sound_card", "holder": "Mercury", "held_by": 2}}


def test_under_the_no_devices_switch_the_line_of_a_sound_card_radio_has_no_port(tmp_path: Path, under_the_switch: None) -> None:  # noqa: F811
    driver = make_driver(spec(), Claims(), utcnow, tmp_path)
    driver.configure(spec(), DEFAULTS, RunOverrides())
    assert nodevices.on() and driver.line.port == "" and "which is not started" in driver.words(spec(), DEFAULTS, RunOverrides())


async def test_under_the_no_devices_switch_no_daemon_starts_a_direwolf(tmp_path: Path, under_the_switch: None, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    started_programs: list[list[str]] = []
    monkeypatch.setattr("neoaprs.direwolfprogram.find", lambda tools=None: started_programs.append(["asked"]) or fakedirewolf.program())
    driver = make_driver(spec(), Claims(), utcnow, tmp_path)
    driver.configure(spec(), DEFAULTS, RunOverrides())
    await driver.start()
    assert driver.modem is not None and (driver.modem.state, driver.modem.reason, driver.modem.pid) == ("waiting", "not_installed", None) and started_programs == [], "the program is not even looked for"
    assert driver.modem.sound_cards() == []
    await driver.stop()


async def test_the_type_is_offered_and_added_on_the_wire_and_tune_on_it_waits_for_its_modem(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(radioregistry.CARRIED, "direwolf", lambda: True)             # (an installation that carries Direwolf; the radio's modem finds none all the same, as this checkout has none)
    e, page = await started(tmp_path)
    id = await added(page, "direwolf", "Shack")
    await page.until(lambda: bool(page.of("status")), timeout=12)
    assert page.of("status")[-1]["unavailable_types"] == []
    row = page.topics["radios"][str(id)]
    assert ROW.validate_python(row) and (row["type"], row["kind"], row["can"]["tune"], row["can"]["rx_level"], row["can"]["scope"]) == ("direwolf", "fm", True, True, False)
    await page.until(lambda: (page.topics["radios"][str(id)]["modem"] or {}).get("reason") == "not_installed")
    assert page.topics["radios"][str(id)]["problem"] == {"code": "modem.not_installed", "params": {}}, "this checkout has no Direwolf for the modem to find"
    assert (await refused(page, {"cmd": "radio_tune", "radio": id, "on": True}))["code"] == "radio.no_modem"
    assert (await refused(page, {"cmd": "radio_scope", "radio": id, "on": True}))["code"] == "radio.no_scope"
    assert {f"radio/{id}/sound_card", f"radio/{id}/keying", f"radio/{id}/tx_gain_db"} <= set(page.topics["config"]["radio_values"])
    await e.stop()


async def test_where_direwolf_is_not_carried_the_type_is_not_offered_and_not_added(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(radiotypes, "sys", SimpleNamespace(platform="darwin"))     # (a Mac, to the types alone: the daemon itself runs as this system does)
    e, page = await started(tmp_path)
    try:
        await page.until(lambda: bool(page.of("status")) and page.of("status")[-1]["unavailable_types"] == ["direwolf"], timeout=12)
        error = await refused(page, {"cmd": "radio_add", "type": "direwolf"})
        assert (error["code"], error["params"]) == ("radio.unknown_type", {"type": "direwolf"})
        id = await added(page, "kiss")
        error = await refused(page, {"cmd": "radio_change", "radio": id, "type": "direwolf"})
        assert (error["code"], error["params"]) == ("radio.unknown_type", {"type": "direwolf"}), "nor is a radio changed to it"
    finally:
        await e.stop()


def test_a_type_whose_program_this_installation_does_not_carry_is_not_offered_but_on_a_bench_it_is(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("neoaprs.direwolfprogram.find", lambda tools=None: None)
    assert radioregistry.unavailable_types() == ("direwolf",), "a wheel installed with pip, a checkout: no Direwolf, so no radio that would only wait for it"
    monkeypatch.setattr("neoaprs.direwolfprogram.find", lambda tools=None: ["direwolf"])
    assert radioregistry.unavailable_types() == ()
    monkeypatch.setattr(radiotypes, "sys", SimpleNamespace(platform="darwin"))
    assert radioregistry.unavailable_types() == ("direwolf",), "nor on a system whose installations carry none"
    monkeypatch.setattr(radiotypes, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr("neoaprs.direwolfprogram.find", lambda tools=None: None)
    monkeypatch.setattr("neoaprs.nodevices.on", lambda: True)
    assert radioregistry.unavailable_types() == (), "under the no-devices switch the system alone counts: a bench shows the box and starts no Direwolf"


def test_while_tune_or_the_keying_test_has_the_radio_its_row_shows_the_test_and_no_problem(tmp_path: Path) -> None:
    driver = driver_of(tmp_path)
    driver.modem.state, driver.modem.test = "running", "tune"                 # (the radio's Direwolf is stopped for the calibration run: its line is down meanwhile)
    row = radio_row(spec(), (spec(),), SimpleNamespace(line=driver.line, beacon=None), Claims())
    assert row is not None and row["problem"] is None and (row["modem"]["test"], row["modem"]["keyed"]) == ("tune", True)
    driver.modem.test = ""
    row = radio_row(spec(), (spec(),), SimpleNamespace(line=driver.line, beacon=None), Claims())
    assert row is not None and row["problem"] == {"code": "radio.not_connected", "params": {"name": "FM"}}


async def test_a_sound_card_radios_own_choice_of_keying_never_takes_a_port_another_radio_is_set_to_though_none_has_opened_it(tmp_path: Path) -> None:
    """The card's interface has one CP2102 (a Digirig): it keys by its RTS, unless another radio is set to that port (radio 1's TNC, not started yet: not held, only named), when it keys by VOX."""
    digirig = SerialPort("/dev/ttyUSB0", 0x10C4, 0xEA60)
    for other_port, keyed in (("/dev/ttyUSB7", Keying("rts", "/dev/ttyUSB0")), ("/dev/ttyUSB0", Keying("vox"))):
        tnc = RadioSpec(1, "fm", "kiss", "", True, 1, settings={"port": other_port})
        radio = spec(3, keying="")
        station = with_radios(DEFAULTS, (tnc, radio))
        driver = driver_of(tmp_path / other_port.rsplit("/", 1)[1], Claims(), radio)
        driver.configure(radio, station, RunOverrides(check_sec=0.0))
        driver.modem.ports = lambda: [digirig]
        driver.modem.beside = lambda card, devices: [d for d in devices if d == digirig.device]
        try:
            await driver.start()
            await until_started(lambda d=driver: d.modem.state == "running")
            assert driver.modem.keying == keyed, (other_port, driver.modem.keying)
        finally:
            await driver.stop()
