"""Classic APRS on HF: the type "Sound card, 300 (HF)" (Direwolf's 300 baud modem, paced as a slow
channel) and the tick On HF of the KISS types, which paces a TNC the same way. The fake Direwolf
of tests/support/fakedirewolf.py says the modem it was configured with.
"""

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from neoaprs import direwolfmodem
from neoaprs.beaconrule import beacon_interval, floor_of
from neoaprs.claims import Claims
from neoaprs.clock import utcnow
from neoaprs.config import DEFAULTS
from neoaprs.crossrule import slow_channel
from neoaprs.direwolf import CONF_FILE, PROFILE_300, conf_text, mode_of, modem_baud
from neoaprs.direwolfdriver import DirewolfDriver, direwolf_settings
from neoaprs.mercury import Keying
from neoaprs.radiodriver import RunOverrides
from neoaprs.radioregistry import make_driver
from neoaprs.radiospec import RadioSpec
from neoaprs.radiotype import type_label
from neoaprs.radiotypes import type_of
from neoaprs.radiotypes.common import FM_ALLOWED, FM_LIMITS, SLOW_PACKET_ALLOWED, SLOW_PACKET_LIMITS
from neoaprs.source import Backoff, Source
from neoaprs.web.radioview import radio_row
from tests.support import fakedirewolf, fakemercury
from tests.support.env import until, until_started
from tests.support.modemports import base_of_this_test
from tests.test_tnc import ui_frame

CARD = "plughw:1,0"
SOUND = {"sound_card": CARD, "keying": "vox", "tx_gain_db": "0"}


@pytest.fixture(autouse=True)
def _ports_of_this_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(direwolfmodem, "FIRST_PORT", base_of_this_test())
    monkeypatch.setattr(direwolfmodem, "_numbers_of", lambda name: (1, 1))


def sound_card(type: str = "direwolf-300", id: int = 3) -> RadioSpec:
    return RadioSpec(id, "fm", type, "", True, id, settings=dict(SOUND))


def tnc(type: str = "kiss", on_hf: str | None = None, id: int = 4) -> RadioSpec:
    own = {"port": "/dev/ttyUSB0"} | ({} if on_hf is None else {"on_hf": on_hf})
    return RadioSpec(id, "fm", type, "", True, id, settings=own)


def test_the_300_type_writes_direwolfs_300_baud_modem_with_seven_decoders_30_hz_apart() -> None:
    """The User Guide's configuration for HF SSB (9.2.4): 1600/1800 Hz, the A demodulator with one
    slicer (`-`, which `@` needs) and seven decoders 30 Hz apart, about 100 Hz of mistuning."""
    keying = Keying("vox")
    assert "MODEM 300 A- 7@30\n" in conf_text(CARD, keying, 8002, 300)
    assert "MODEM 1200\n" in conf_text(CARD, keying, 8002) and "MODEM 300" not in conf_text(CARD, keying, 8002)
    assert (modem_baud("direwolf-300"), modem_baud("direwolf"), modem_baud("kiss")) == (300, 1200, 1200)
    assert (mode_of(300), mode_of(1200)) == ("AFSK300", "AFSK1200")
    assert PROFILE_300.key == "direwolf-300" and type_of("direwolf-300").driver == "direwolf"


def test_the_300_type_and_a_kiss_tnc_ticked_on_hf_are_paced_as_a_slow_channel_and_the_others_are_not() -> None:
    slow = [sound_card(), tnc(on_hf="true"), tnc("kiss-tcp", on_hf="true"), tnc("kenwood-d710", on_hf="true")]
    fast = [sound_card("direwolf"), tnc(), tnc(on_hf="false"), tnc(on_hf="maybe")]
    assert all(s.rtype.limits == SLOW_PACKET_LIMITS and s.rtype.allowed == SLOW_PACKET_ALLOWED for s in slow)
    assert all(s.rtype.limits == FM_LIMITS and s.rtype.allowed == FM_ALLOWED for s in fast)
    assert [slow_channel(s.rtype.limits) for s in slow + fast] == [True] * 4 + [False] * 4
    assert [floor_of(s) for s in (slow[0], slow[1], fast[0])] == [30, 30, 20]
    assert [beacon_interval(20, s) for s in (slow[0], slow[1], fast[1])] == [30, 30, 20], (
        "the station's interval raised to the floor of a slow channel"
    )
    assert (
        SLOW_PACKET_LIMITS.beacon_jitter_sec,
        SLOW_PACKET_LIMITS.retry_jitter_sec,
        SLOW_PACKET_LIMITS.max_frame,
    ) == (
        300,
        20,
        None,
    ), "Mercury's random pause and retry pause; AX.25's own frame"
    assert not (SLOW_PACKET_ALLOWED.digipeat or SLOW_PACKET_ALLOWED.smart_beacon or SLOW_PACKET_ALLOWED.shared_channel)
    assert SLOW_PACKET_ALLOWED.paths and SLOW_PACKET_ALLOWED.gateway_heard
    assert tnc("tnc-text", on_hf="true").rtype.limits == FM_LIMITS, "a type with no On HF field is never slowed"


def test_a_bad_stored_on_hf_is_read_as_unticked_without_a_warning_on_each_reading(
    caplog: pytest.LogCaptureFixture,
) -> None:
    radio = tnc(on_hf="maybe")
    with caplog.at_level(logging.WARNING):
        assert [radio.rtype.limits for _ in range(3)] == [FM_LIMITS] * 3
    assert caplog.records == []


def test_a_radio_row_tells_the_page_the_limits_and_rules_in_force() -> None:
    for radio, slow in ((tnc(on_hf="true"), True), (tnc(), False), (sound_card(), True)):
        row = radio_row(radio, (radio,), None, Claims())
        assert row is not None
        assert (row["limits"]["slow"], row["limits"]["beacon_min_min"], row["allowed"]["digipeat"]) == (
            (True, 30, False) if slow else (False, 20, True)
        ), radio.type


def test_a_type_is_named_clear_alone_for_the_log_and_the_support_summary() -> None:
    from neoaprs.cli.radiosettings import type_words

    assert type_label(type_of("direwolf-300")) == "Packet, sound card, 300"
    assert type_words(sound_card()) == "Packet, sound card, 300 (direwolf-300)"
    assert type_words(RadioSpec(9, "fm", "pigeon", "", True, 9)) == "pigeon"


def test_moving_between_the_1200_and_the_300_type_restarts_direwolf_with_the_other_modem() -> None:
    assert direwolf_settings(sound_card("direwolf")) != direwolf_settings(sound_card())
    assert direwolf_settings(sound_card()).baud == 300


def driver_of(tmp_path: Path, radio: RadioSpec) -> DirewolfDriver:
    driver = make_driver(radio, Claims(), utcnow, tmp_path)
    assert isinstance(driver, DirewolfDriver)
    driver.modem._finder, driver.modem._lister, driver.modem.backoff = (
        fakedirewolf.program,
        fakemercury.program,
        Backoff([0.1, 0.1]),
    )
    driver.modem.ports = lambda: []
    driver.line.backoff = Backoff([0.05, 0.05])
    driver.configure(radio, DEFAULTS, RunOverrides(check_sec=0.0))
    return driver


async def test_a_300_radio_runs_direwolf_at_300_baud_and_its_status_line_says_so(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, "neoaprs.direwolf")
    radio = sound_card()
    driver = driver_of(tmp_path, radio)
    assert driver.line.profile is PROFILE_300
    await driver.start()
    try:
        await until_started(lambda: driver.line.state is Source.State.CONNECTED)
        assert "MODEM 300 A- 7@30\n" in (driver.modem.home / CONF_FILE).read_text(encoding="utf-8")
        assert driver.line.describe().startswith("Direwolf AFSK300, listening")
        assert "Channel 0: 300 baud, AFSK 1600 & 1800 Hz, A-" in caplog.text and "0.6: A 1690 & 1890" in caplog.text
        heard: list[str] = []
        driver.line.packet.connect(lambda packet: heard.append(packet.direction))
        assert driver.line.send_frame(ui_frame())
        await until(lambda: "in" in heard)
        row = radio_row(
            radio,
            (radio,),
            SimpleNamespace(line=driver.line, beacon=None, driver=driver, driver_key="direwolf"),
            Claims(),
        )
        assert row is not None and row["modem"]["mode"] == "AFSK300" and row["limits"]["slow"] is True
    finally:
        await driver.stop()
