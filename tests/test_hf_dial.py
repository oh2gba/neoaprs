"""The HF dial the group meets on comes with the version page (`hf_dial` of its answer, neoaprs/versions.py): the update check keeps the last one it was told in the row HF_DIAL, tells it at the start and when it
changes, and the HF box shows it (the Mercury modem's `dial`, read by the view); a page that names none, or one not of the form, changes nothing, and with none known the built-in dial stands."""
import json
from pathlib import Path

from neoaprs.config import HF_DIAL
from neoaprs.mercury import DIAL_TEXT
from neoaprs.services.updatecheck import UpdateCheck
from neoaprs.versions import parse_update
from tests.support.env import remember_stop, until
from tests.support.storedb import store_at


def answer(**extra: str) -> bytes:
    return json.dumps({"version": "0.1.0", "url": "https://neo.oh2gba.eu/", "message": "", **extra}).encode()


class Page:
    def __init__(self, *answers: bytes) -> None:
        self.answers = list(answers)

    async def __call__(self, address: str, version: str, platform: str, install_id: str) -> bytes | None:
        return self.answers.pop(0) if self.answers else None


def test_the_answer_carries_a_dial_of_the_form_and_drops_any_other() -> None:
    assert (update := parse_update(answer(hf_dial="7.0443 MHz USB"))) is not None and update.hf_dial == "7.0443 MHz USB"
    assert (update := parse_update(answer(hf_dial=" 14.1070 MHz USB "))) is not None and update.hf_dial == "14.1070 MHz USB"
    for bad in ("7.0443", "7.0443 MHz", "7,0443 MHz USB", "7.0443 MHz FM", "<b>7.0443 MHz USB</b>", "1234.5 MHz USB"):
        assert (update := parse_update(answer(hf_dial=bad))) is not None and update.hf_dial == "", bad
    assert (update := parse_update(answer())) is not None and update.hf_dial == "", "a page older than 0.16.1 names none"


async def test_a_dial_is_kept_told_and_survives_a_restart(tmp_path: Path) -> None:
    store = await store_at(tmp_path / "neoaprs.sqlite")
    told: list[str] = []
    service = UpdateCheck(lambda: _config(), "0.1.0", "linux", Page(answer(hf_dial="7.0443 MHz USB"), answer(), answer(hf_dial="7.0443 MHz USB")), environ={}, memory=store)
    remember_stop(service.stop)
    service.dial_changed.connect(told.append)
    await service.check()
    assert service.hf_dial == "7.0443 MHz USB" and told == ["7.0443 MHz USB"] and await store.setting(HF_DIAL) == "7.0443 MHz USB"
    await service.check()
    await service.check()
    assert told == ["7.0443 MHz USB"], "an answer with none, and the same one again, tell nothing"
    again = UpdateCheck(lambda: _config(), "0.1.0", "linux", Page(), environ={}, memory=store, first_sec=3600)
    remember_stop(again.stop)
    kept: list[str] = []
    again.dial_changed.connect(kept.append)
    await again.start()
    await until(lambda: kept == ["7.0443 MHz USB"])
    assert again.hf_dial == "7.0443 MHz USB", "the one kept is told at the start, before the page is asked"


def test_the_hf_box_shows_the_dial_of_the_page_and_the_built_in_one_without(tmp_path: Path) -> None:
    from neoaprs.mercurymodem import Mercury
    modem = Mercury(tmp_path)
    assert (modem.dial or DIAL_TEXT) == DIAL_TEXT
    modem.dial = "7.0443 MHz USB"
    assert (modem.dial or DIAL_TEXT) == "7.0443 MHz USB"


def _config():  # type: ignore[no-untyped-def]
    from neoaprs.config import DEFAULTS
    return DEFAULTS
