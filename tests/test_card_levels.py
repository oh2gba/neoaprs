"""Tests for the sound card levels of a radio (neoaprs/cardlevels.py) and its drivers
(neoaprs/direwolfdriver.py, neoaprs/mercurydriver.py) on a made-up mixer: when levels are applied,
that a change restarts nothing, and the radios that have no levels.
"""

import asyncio
import ctypes
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest

from neoaprs import cardlevels, direwolfmodem, direwolftune, nodevices, soundmixer
from neoaprs.cardlevels import CardLevels
from neoaprs.claims import Claim, Claims
from neoaprs.clock import utcnow
from neoaprs.config import DEFAULTS
from neoaprs.direwolfdriver import DirewolfDriver
from neoaprs.mercuryclaims import radio_folder
from neoaprs.mercurydriver import MercuryDriver
from neoaprs.radiodriver import RunOverrides
from neoaprs.radiospec import RadioSpec
from neoaprs.soundmixer import NONE, Levels
from neoaprs.source import Backoff
from neoaprs.web.radioview import radio_row
from neoaprs.winmixer import Windows
from tests.support import fakedirewolf, fakemercury
from tests.support.env import remember_stop, until, until_started
from tests.support.modemports import base_of_this_test
from tests.test_direwolf_modem import modem as direwolf_modem
from tests.test_direwolf_modem import running

CARD = "plughw:1,0"


@dataclass
class FakeMixer:
    """A made-up mixer: the cards' levels by card (a card absent has none), every write written down
    as (card, tx, rx); `steps` makes a control of fewer steps than 100 (a percent is rounded to
    them)."""

    cards: dict[str, Levels]
    writes: list[tuple[str, int | None, int | None]] = field(default_factory=list)
    reads: int = 0
    steps: int = 100

    def _step(self, value: int) -> int:
        return round(round(value * self.steps / 100) * 100 / self.steps)

    def read(self, card: str) -> Levels:
        self.reads += 1
        return self.cards.get(card, NONE)

    def write(self, card: str, tx: int | None, rx: int | None) -> Levels:
        self.writes.append((card, tx, rx))
        now = self.cards.get(card, NONE)
        self.cards[card] = Levels(
            self._step(tx) if tx is not None and now.tx is not None else now.tx,
            self._step(rx) if rx is not None and now.rx is not None else now.rx,
        )
        return self.read(card)


@pytest.fixture(autouse=True)
def _quick(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cardlevels, "POLL_SEC", 0.05)
    monkeypatch.setattr(direwolfmodem, "FIRST_PORT", base_of_this_test())
    monkeypatch.setattr(direwolfmodem, "_numbers_of", lambda name: (1, 1))


class Modem:
    def __init__(self, card: str = CARD) -> None:
        self.sound_card, self.starts = card, 1


async def test_the_values_are_put_on_the_card_at_the_start_and_again_at_every_start_of_the_modem() -> None:
    mixer, modem = FakeMixer({CARD: Levels(38, 50)}), Modem()
    levels = CardLevels(lambda: modem.sound_card, lambda: modem.starts, mixer)
    await levels.start(80, None)
    assert mixer.writes == [(CARD, 80, None)] and levels.levels == Levels(80, 50), (
        "the playback value put on, the capture one never set is not written"
    )
    # (the card plugged in again: the system's own level)
    mixer.cards[CARD] = Levels(38, 50)
    modem.starts = 2
    await until(lambda: len(mixer.writes) == 2)
    assert mixer.writes[1] == (CARD, 80, None) and levels.levels == Levels(80, 50)
    await levels.stop()
    assert levels.levels == Levels(80, 50), (
        "a radio stopped keeps the levels on its row: its Transmit level row stays the card's slider"
    )


async def test_the_sliders_come_and_go_only_with_another_card() -> None:
    mixer, modem = FakeMixer({CARD: Levels(38, 50), "plughw:2,0": Levels(70, None)}), Modem()
    levels = CardLevels(lambda: modem.sound_card, lambda: modem.starts, mixer)
    await levels.start(None, None)
    del mixer.cards[CARD]  # (unplugged: the card cannot be read)
    await asyncio.sleep(0.2)
    assert levels.levels == Levels(38, 50), "the same card unreadable for a while keeps its sliders"
    modem.sound_card = ""  # (the modem waits for a card)
    await asyncio.sleep(0.2)
    assert levels.levels == Levels(38, 50)
    modem.sound_card = "plughw:2,0"
    await until(lambda: levels.levels == Levels(70, None))
    await levels.stop()


async def test_never_set_nothing_is_written_and_the_row_follows_the_card() -> None:
    mixer, modem = FakeMixer({CARD: Levels(38, 50)}), Modem()
    levels = CardLevels(lambda: modem.sound_card, lambda: modem.starts, mixer)
    told: list[Levels] = []
    levels.changed.connect(lambda: told.append(levels.levels))
    await levels.start(None, None)
    assert levels.levels == Levels(38, 50) and all(tx is None and rx is None for _, tx, rx in mixer.writes), (
        "nothing set on the card"
    )
    mixer.cards[CARD] = Levels(20, 50)  # (the desktop's mixer moved it)
    await until(lambda: levels.levels == Levels(20, 50))
    assert told == [Levels(38, 50), Levels(20, 50)], "told once for each change, not at every look"
    await levels.stop()


async def test_a_change_is_set_at_once_and_a_control_of_few_steps_says_the_percent_asked() -> None:
    mixer, modem = FakeMixer({CARD: Levels(38, 50)}, steps=37), Modem()
    levels = CardLevels(lambda: modem.sound_card, lambda: modem.starts, mixer)
    await levels.start(None, None)
    levels.want(None, 61)
    await until(lambda: levels.levels.rx == 61)
    assert mixer.writes[-1] == (CARD, None, 61) and mixer.cards[CARD].rx == 62, (
        "the card holds the step nearest; the row says what was asked"
    )
    await asyncio.sleep(0.2)
    assert levels.levels == Levels(38, 61), "and keeps saying it while the card holds that step"
    levels.want(None, 61)
    await asyncio.sleep(0.1)
    assert [w for w in mixer.writes if w[2] is not None] == [(CARD, None, 61)], "the same value again writes nothing"
    await levels.stop()


async def test_a_card_without_controls_and_no_card_have_no_levels() -> None:
    mixer = FakeMixer({})
    levels = CardLevels(lambda: "", lambda: 1, mixer)
    await levels.start(50, 50)
    assert levels.levels == NONE and mixer.writes == [] and mixer.reads == 0, "no card: the mixer is not asked"
    await levels.stop()


def spec(id: int = 3, **settings: str) -> RadioSpec:
    return RadioSpec(
        id,
        "fm",
        "direwolf",
        "",
        True,
        id,
        settings={"sound_card": CARD, "keying": "vox", "tx_gain_db": "0", "beacon": "true", **settings},
    )


def direwolf_driver(tmp_path: Path, mixer: FakeMixer, radio: RadioSpec) -> DirewolfDriver:
    driver = DirewolfDriver(radio, Claims(), radio_folder(tmp_path, radio.id), utcnow, mixer=mixer)
    driver.modem._finder, driver.modem._lister, driver.modem.backoff = (
        fakedirewolf.program,
        fakemercury.program,
        Backoff([0.1, 0.1]),
    )
    driver.modem.ports = lambda: []
    driver.configure(radio, DEFAULTS, RunOverrides(check_sec=0.0))
    remember_stop(driver.stop)  # (stopped at the test's end, also when it fails before its own stop)
    return driver


async def test_a_sound_card_radio_puts_its_levels_on_the_card_and_a_change_of_them_restarts_nothing(
    tmp_path: Path,
) -> None:
    mixer = FakeMixer({CARD: Levels(38, 50)})
    radio = spec(tx_card="70")
    driver = direwolf_driver(tmp_path, mixer, radio)
    await driver.start()
    await running(driver.modem)
    assert mixer.writes[0] == (CARD, 70, None)
    row = radio_row(
        radio,
        (radio,),
        SimpleNamespace(line=driver.line, beacon=None, driver=driver, driver_key=radio.rtype.driver),
        Claims(),
    )
    assert row is not None and row["card"] == {"tx": 70, "rx": 50, "read": True}, (
        "the row says the card's levels: the page draws both sliders"
    )
    assert driver.restart_key(spec(tx_card="30", rx_card="20"), DEFAULTS, RunOverrides()) == driver.restart_key(
        radio, DEFAULTS, RunOverrides()
    ), "no restart of the radio"
    for value in (60, 50, 40):
        driver.card.want(value, 45)
        await until(lambda value=value: mixer.cards[CARD].tx == value)
    await asyncio.sleep(0.3)
    assert len(fakedirewolf.runs(radio_folder(tmp_path, 3))) == 1 and driver.modem.starts == 1, (
        "Direwolf was started once: a change of the card's level is set on the card alone"
    )
    await driver.stop()


async def test_a_sound_card_radio_set_to_the_card_another_radio_holds_never_reads_or_sets_its_levels(
    tmp_path: Path,
) -> None:
    """Two radios set to one card: the second's start is refused, and its values are not written on
    the card the first transmits on, nor is that card read for its row."""
    mixer = FakeMixer({CARD: Levels(38, 50)})
    radio = spec(tx_card="70", rx_card="20")
    driver = direwolf_driver(tmp_path, mixer, radio)
    driver.claims.hold(Claim("sound_card", CARD, 2))
    await driver.start()
    try:
        await until(lambda: driver.modem.state == "waiting")
        assert driver.modem.sound_card == CARD and "is held by" in driver.modem.problem
        await asyncio.sleep(0.3)
        driver.card.want(90, 90)
        await asyncio.sleep(0.1)
        assert (
            mixer.writes == []
            and mixer.reads == 0
            and driver.card.levels == NONE
            and mixer.cards[CARD] == Levels(38, 50)
        )
    finally:
        await driver.stop()


async def test_the_mercury_radios_card_has_levels_and_the_dummy_and_an_attached_mercury_have_none(
    tmp_path: Path,
) -> None:
    mixer = FakeMixer({CARD: Levels(38, 50)})
    hf = RadioSpec(
        2,
        "hf",
        "mercury",
        "",
        True,
        2,
        settings={"sound_card": CARD, "keying": "vox", "tx_gain_db": "0", "beacon": "true", "rx_card": "30"},
    )
    claims = Claims()
    driver = MercuryDriver(hf, claims, radio_folder(tmp_path, 2), utcnow, mixer=mixer)
    driver.modem.sound_card = CARD
    driver.configure(hf, DEFAULTS, RunOverrides())
    assert driver._own_card() == "", (
        "a card the radio does not hold (its start was refused, the card let go) is not its to set"
    )
    claims.hold(Claim("sound_card", CARD, 2))
    assert driver._own_card() == CARD
    driver.configure(hf, DEFAULTS, RunOverrides(hf_port="socket://127.0.0.1:9", attach_to=2))
    assert driver._own_card() == "", "a Mercury something else runs: its card is not ours to set"
    dummy = RadioSpec(4, "hf", "dummy-hf", "", True, 4, settings={"beacon": "true"})
    assert MercuryDriver(dummy, Claims(), radio_folder(tmp_path, 4), utcnow, mixer=mixer)._own_card() == "", (
        "the Dummy radio's sound is the computer's own"
    )


async def test_several_presses_of_the_transmit_level_are_one_start_of_direwolf_and_keying_still_restarts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(direwolftune, "SETTLE_SEC", 0.3)
    m = direwolf_modem(tmp_path)
    await m.start(CARD, "vox", 0)
    await running(m)
    for gain in (-1, -2, -3, -4):
        m.set_tx_gain(gain)
        await asyncio.sleep(0.05)
    await until_started(lambda: fakedirewolf.runs(radio_folder(tmp_path, 3))[-1][-2:] == ["-G", "63"])
    await running(m)
    await asyncio.sleep(0.5)
    runs = fakedirewolf.runs(radio_folder(tmp_path, 3))
    assert len(runs) == 2, "four presses, one start again with the last level"
    driver = direwolf_driver(tmp_path, FakeMixer({}), spec())
    assert driver.restart_key(spec(keying="rts:/dev/ttyUSB7"), DEFAULTS, RunOverrides()) != driver.restart_key(
        spec(), DEFAULTS, RunOverrides()
    ), "a change of the keying restarts the radio"
    await m.stop()


class FailingMixer:
    """A mixer whose every call fails with a fault that is no OSError (a wrong argument of a ctypes
    call)."""

    calls = 0

    def read(self, card: str) -> Levels:
        self.calls += 1
        raise ctypes.ArgumentError("argument 2: wrong type")

    def write(self, card: str, tx: int | None, rx: int | None) -> Levels:
        return self.read(card)


async def test_a_mixer_that_fails_starts_the_radio_without_sliders_and_says_it_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    mixer, radio = FailingMixer(), spec(tx_card="70")
    driver = direwolf_driver(tmp_path, mixer, radio)
    caplog.set_level(logging.INFO, "neoaprs.soundmixer")
    await driver.start()
    try:
        await running(driver.modem)
        # (the card is looked at again and again: every look fails)
        await until(lambda: mixer.calls >= 4)
        said = [r for r in caplog.records if r.name == "neoaprs.soundmixer" and "could not be had" in r.getMessage()]
        assert len(said) == 1 and said[0].levelno == logging.INFO, "said once for the card, never as an error"
        row = radio_row(
            radio,
            (radio,),
            SimpleNamespace(line=driver.line, beacon=None, driver=driver, driver_key=radio.rtype.driver),
            Claims(),
        )
        assert row is not None and row["card"] == {"tx": None, "rx": None, "read": True}, (
            "no sliders: the row has the modem's - and +"
        )
        assert driver.modem.state == "running"
    finally:
        await driver.stop()


async def test_a_card_whose_mixer_fails_after_a_start_keeps_the_radio_running() -> None:
    """The fault comes from the system's mixer on Windows (a Core Audio call that raises something
    else than OSError): the same end, no levels."""

    class Raising:
        def get(self, device: str) -> float | None:
            raise ValueError("a COM call answered nonsense")

        def put(self, device: str, scalar: float) -> None:
            raise ValueError("a COM call answered nonsense")

    levels = CardLevels(lambda: "{0.0.1.00000000}.{2301}|{0.0.0.00000000}.{ca03}", lambda: 1, Windows(Raising()))
    await levels.start(50, 50)
    assert levels.levels == NONE and levels.known
    await asyncio.sleep(0.2)
    await levels.stop()


async def test_the_levels_are_known_once_the_radios_card_was_read_or_where_there_is_nothing_to_wait_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    modem = Modem("")
    modem.starts = 0
    levels = CardLevels(lambda: modem.sound_card, lambda: modem.starts, FakeMixer({CARD: Levels(38, 50)}))
    assert not levels.known, "a radio off, never read in this run"
    await levels.start(None, None)
    assert not levels.known, "enabled, the modem not on its card yet"
    modem.sound_card, modem.starts = CARD, 1
    await until(lambda: levels.known)
    assert levels.levels == Levels(38, 50)
    await levels.stop()
    assert levels.known, "stopped: still the card's levels as read last"
    assert CardLevels(lambda: CARD, lambda: 1, FakeMixer({}), own=lambda: False).known, (
        "no card of the radio's own by its kind"
    )
    # (the switch is lifted in a test's own process: this is a daemon under it, on any system)
    monkeypatch.setattr(nodevices, "on", lambda: True)
    assert CardLevels(lambda: CARD, lambda: 1).known, "the no-devices switch: no mixer at all"
    monkeypatch.setattr(nodevices, "on", lambda: False)
    monkeypatch.setattr(sys, "platform", "darwin")
    assert CardLevels(lambda: CARD, lambda: 1).known, "macOS: no mixer"
    monkeypatch.setattr(sys, "platform", "linux")
    assert CardLevels(lambda: CARD, lambda: 1).known, "Linux without the ALSA library (the guards' load finds none)"
    monkeypatch.setattr(soundmixer, "load_alsa", lambda: object())
    assert not CardLevels(lambda: CARD, lambda: 1).known, "Linux with the library: the card is to be read first"
    hf = RadioSpec(
        2,
        "hf",
        "mercury",
        "",
        True,
        2,
        settings={"sound_card": CARD, "keying": "vox", "tx_gain_db": "0", "beacon": "true"},
    )
    driver = MercuryDriver(hf, Claims(), radio_folder(tmp_path, 2), utcnow, mixer=FakeMixer({}))
    driver.configure(hf, DEFAULTS, RunOverrides())
    assert not driver.card.known
    driver.configure(hf, DEFAULTS, RunOverrides(hf_port="socket://127.0.0.1:9", attach_to=2))
    assert driver.card.known, "a Mercury something else runs"
    dummy = RadioSpec(4, "hf", "dummy-hf", "", True, 4, settings={"beacon": "true"})
    assert MercuryDriver(dummy, Claims(), radio_folder(tmp_path, 4), utcnow, mixer=FakeMixer({})).card.known, (
        "the Dummy radio"
    )


async def test_a_mercury_radio_on_the_systems_default_device_keeps_its_transmit_levels_buttons(tmp_path: Path) -> None:
    """Mercury left to its own choice of card runs on the system's default device ("") where it
    finds none to choose: no card of its own name to read, so its row has the modem's - and + once
    it runs."""
    mixer = FakeMixer({CARD: Levels(38, 50)})
    hf = RadioSpec(
        2,
        "hf",
        "mercury",
        "",
        True,
        2,
        settings={"sound_card": "", "keying": "vox", "tx_gain_db": "0", "beacon": "true"},
    )
    driver = MercuryDriver(hf, Claims(), radio_folder(tmp_path, 2), utcnow, mixer=mixer)
    driver.configure(hf, DEFAULTS, RunOverrides())
    assert not driver.card.known, "not started yet: the card it will run on is not known"
    driver.modem.sound_card, driver.modem.starts = "", 1  # (its program started on the default device)
    await driver.card.start(None, None)
    try:
        await asyncio.sleep(0.2)
        row = radio_row(
            hf,
            (hf,),
            SimpleNamespace(line=driver.line, beacon=None, driver=driver, driver_key=hf.rtype.driver),
            Claims(),
        )
        assert row is not None and row["card"] == {"tx": None, "rx": None, "read": True}, (
            "the row has the modem's - and +"
        )
        assert mixer.reads == 0 and mixer.writes == [], "and the mixer is not asked"
    finally:
        await driver.card.stop()


@pytest.mark.parametrize(
    ("gain", "card", "written", "levels"),
    [
        # the card's slider is the transmit level: both values are put on the card
        ("0", Levels(38, 50), (70, 20), Levels(70, 20)),
        # the modem's - and + are: the card's playback level stays as the system has it, the capture one
        # is set
        ("-12", Levels(38, 50), (None, 20), Levels(38, 20)),
        # no playback control: nothing of it to set, the - and + are the transmit level
        ("0", Levels(None, 50), (70, 20), Levels(None, 20)),
    ],
)
async def test_the_playback_value_is_put_on_the_card_only_while_the_modems_gain_is_zero(
    tmp_path: Path, gain: str, card: Levels, written: tuple[int | None, int | None], levels: Levels
) -> None:
    mixer = FakeMixer({CARD: card})
    radio = spec(tx_gain_db=gain, tx_card="70", rx_card="20")
    driver = direwolf_driver(tmp_path, mixer, radio)
    await driver.start()
    try:
        await running(driver.modem)
        assert mixer.writes[0] == (CARD, *written) and driver.card.levels == levels
        driver.card.want(*cardlevels.wanted(spec(tx_gain_db=gain, tx_card="90", rx_card="20")))
        if gain == "0":
            await until(lambda: mixer.writes[-1][1] == 90)
        await asyncio.sleep(0.2)
        assert (mixer.writes[-1][1] == 90) is (gain == "0"), (
            "a change of the value is set at once only where it is the transmit level"
        )
    finally:
        await driver.stop()
