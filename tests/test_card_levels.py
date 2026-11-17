"""The sound card's own levels of a radio (neoaprs/cardlevels.py) and its drivers (neoaprs/direwolfdriver.py, neoaprs/mercurydriver.py), on a made-up mixer: the radio's values are put on the card at every
start of its modem and never when the operator never set them, a change is set at once and restarts nothing (the starts of the made-up Direwolf are counted), the row says the card's levels and follows the
card, a control with fewer steps than 100 says the percent asked, and the Dummy radio and a Mercury something else runs have no levels. Several presses of the Transmit level's - and + where it is still
Direwolf's own scaling are one start of the program."""
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest

from neoaprs import cardlevels, direwolfmodem, direwolftune
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
from tests.support import fakedirewolf, fakemercury
from tests.support.env import until, until_started
from tests.support.modemports import base_of_this_test
from tests.test_direwolf_modem import modem as direwolf_modem
from tests.test_direwolf_modem import running

CARD = "plughw:1,0"


@dataclass
class FakeMixer:
    """A made-up mixer: the cards' levels by card (a card absent has none), every write written down as (card, tx, rx); `steps` makes a control of fewer steps than 100 (a percent is rounded to them)."""
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
        self.cards[card] = Levels(self._step(tx) if tx is not None and now.tx is not None else now.tx, self._step(rx) if rx is not None and now.rx is not None else now.rx)
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
    assert mixer.writes == [(CARD, 80, None)] and levels.levels == Levels(80, 50), "the playback value put on, the capture one never set is not written"
    mixer.cards[CARD] = Levels(38, 50)                                   # (the card plugged in again: the system's own level)
    modem.starts = 2
    await until(lambda: len(mixer.writes) == 2)
    assert mixer.writes[1] == (CARD, 80, None) and levels.levels == Levels(80, 50)
    await levels.stop()
    assert levels.levels == Levels(80, 50), "a radio stopped keeps the levels on its row: its Transmit level row stays the card's slider"


async def test_the_sliders_come_and_go_only_with_another_card() -> None:
    mixer, modem = FakeMixer({CARD: Levels(38, 50), "plughw:2,0": Levels(70, None)}), Modem()
    levels = CardLevels(lambda: modem.sound_card, lambda: modem.starts, mixer)
    await levels.start(None, None)
    del mixer.cards[CARD]                                                # (unplugged: the card cannot be read)
    await asyncio.sleep(0.2)
    assert levels.levels == Levels(38, 50), "the same card unreadable for a while keeps its sliders"
    modem.sound_card = ""                                                # (the modem waits for a card)
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
    assert levels.levels == Levels(38, 50) and all(tx is None and rx is None for _, tx, rx in mixer.writes), "nothing set on the card"
    mixer.cards[CARD] = Levels(20, 50)                                   # (the desktop's mixer moved it)
    await until(lambda: levels.levels == Levels(20, 50))
    assert told == [Levels(38, 50), Levels(20, 50)], "told once for each change, not at every look"
    await levels.stop()


async def test_a_change_is_set_at_once_and_a_control_of_few_steps_says_the_percent_asked() -> None:
    mixer, modem = FakeMixer({CARD: Levels(38, 50)}, steps=37), Modem()
    levels = CardLevels(lambda: modem.sound_card, lambda: modem.starts, mixer)
    await levels.start(None, None)
    levels.want(None, 61)
    await until(lambda: levels.levels.rx == 61)
    assert mixer.writes[-1] == (CARD, None, 61) and mixer.cards[CARD].rx == 62, "the card holds the step nearest; the row says what was asked"
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
    return RadioSpec(id, "fm", "direwolf", "", True, id, settings={"sound_card": CARD, "keying": "vox", "tx_gain_db": "0", "beacon": "true", **settings})


def direwolf_driver(tmp_path: Path, mixer: FakeMixer, radio: RadioSpec) -> DirewolfDriver:
    driver = DirewolfDriver(radio, Claims(), radio_folder(tmp_path, radio.id), utcnow, mixer=mixer)
    driver.modem._finder, driver.modem._lister, driver.modem.backoff = fakedirewolf.program, fakemercury.program, Backoff([0.1, 0.1])
    driver.modem.ports = lambda: []
    driver.configure(radio, DEFAULTS, RunOverrides(check_sec=0.0))
    return driver


async def test_a_sound_card_radio_puts_its_levels_on_the_card_and_a_change_of_them_restarts_nothing(tmp_path: Path) -> None:
    mixer = FakeMixer({CARD: Levels(38, 50)})
    radio = spec(tx_card="70")
    driver = direwolf_driver(tmp_path, mixer, radio)
    await driver.start()
    await running(driver.modem)
    assert mixer.writes[0] == (CARD, 70, None)
    row = radio_row(radio, (radio,), SimpleNamespace(line=driver.line, beacon=None, driver=driver), Claims())
    assert row is not None and row["card"] == {"tx": 70, "rx": 50}, "the row says the card's levels: the page draws both sliders"
    assert driver.restart_key(spec(tx_card="30", rx_card="20"), DEFAULTS, RunOverrides()) == driver.restart_key(radio, DEFAULTS, RunOverrides()), "no restart of the radio"
    for value in (60, 50, 40):
        driver.card.want(value, 45)
        await until(lambda value=value: mixer.cards[CARD].tx == value)
    await asyncio.sleep(0.3)
    assert len(fakedirewolf.runs(radio_folder(tmp_path, 3))) == 1 and driver.modem.starts == 1, "Direwolf was started once: a change of the card's level is set on the card alone"
    await driver.stop()


async def test_a_sound_card_radio_set_to_the_card_another_radio_holds_never_reads_or_sets_its_levels(tmp_path: Path) -> None:
    """Two radios set to one card: the second's start is refused, and its values are not written on the card the first transmits on, nor is that card read for its row."""
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
        assert mixer.writes == [] and mixer.reads == 0 and driver.card.levels == NONE and mixer.cards[CARD] == Levels(38, 50)
    finally:
        await driver.stop()


async def test_the_mercury_radios_card_has_levels_and_the_dummy_and_an_attached_mercury_have_none(tmp_path: Path) -> None:
    mixer = FakeMixer({CARD: Levels(38, 50)})
    hf = RadioSpec(2, "hf", "mercury", "", True, 2, settings={"sound_card": CARD, "keying": "vox", "tx_gain_db": "0", "beacon": "true", "rx_card": "30"})
    claims = Claims()
    driver = MercuryDriver(hf, claims, radio_folder(tmp_path, 2), utcnow, mixer=mixer)
    driver.modem.sound_card = CARD
    driver.configure(hf, DEFAULTS, RunOverrides())
    assert driver._own_card() == "", "a card the radio does not hold (its start was refused, the card let go) is not its to set"
    claims.hold(Claim("sound_card", CARD, 2))
    assert driver._own_card() == CARD
    driver.configure(hf, DEFAULTS, RunOverrides(hf_port="socket://127.0.0.1:9", attach_to=2))
    assert driver._own_card() == "", "a Mercury something else runs: its card is not ours to set"
    dummy = RadioSpec(4, "hf", "dummy-hf", "", True, 4, settings={"beacon": "true"})
    assert MercuryDriver(dummy, Claims(), radio_folder(tmp_path, 4), utcnow, mixer=mixer)._own_card() == "", "the Dummy radio's sound is the computer's own"


async def test_several_presses_of_the_transmit_level_are_one_start_of_direwolf_and_keying_still_restarts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    assert driver.restart_key(spec(keying="rts:/dev/ttyUSB7"), DEFAULTS, RunOverrides()) != driver.restart_key(spec(), DEFAULTS, RunOverrides()), "a change of the keying restarts the radio"
    await m.stop()
