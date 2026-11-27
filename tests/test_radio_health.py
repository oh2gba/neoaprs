"""A radio's state and problem are decided in one place (neoaprs/radiohealth.py, neoaprs/tnchealth.py), and the
row of the topic `radios` only formats them: the cases where the row said something stale."""

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from neoaprs.claims import Claims
from neoaprs.radiohealth import radio_health
from neoaprs.radiospec import RadioSpec
from neoaprs.radiotype import FM_ID, HF_ID
from neoaprs.source import Source
from neoaprs.tnc import Tnc
from neoaprs.tncprofile import KISS, MERCURY
from neoaprs.tnchealth import RadioHealth
from neoaprs.web.radioview import radio_row

FM = RadioSpec(FM_ID, "fm", "kiss", "Mobile", True, 1)
HF = RadioSpec(HF_ID, "hf", "mercury", "", True, 2)


def at_work(line: Tnc, driver_key: str = "tnc") -> Any:
    return SimpleNamespace(
        line=line,
        driver_key=driver_key,
        beacon=SimpleNamespace(last_sent=None, next_due=None, interval_min=0, problem=""),
        driver=SimpleNamespace(card=None),
    )


def connected(profile: Any = KISS) -> Tnc:
    line = Tnc("/dev/ttyUSB0", profile=profile)
    line.state = Source.State.CONNECTED
    return line


def test_a_radio_just_unticked_or_removed_whose_line_has_not_stopped_yet_is_shown_stopped() -> None:
    radio = at_work(connected())
    assert radio_health(FM, (FM,), radio, Claims()) == RadioHealth(Source.State.CONNECTED)
    off = replace(FM, enabled=False)
    assert radio_health(off, (off,), radio, Claims()) == RadioHealth(Source.State.STOPPED)
    row = radio_row(off, (off,), radio, Claims())
    assert row is not None and (row["state"], row["problem"]) == ("stopped", None)
    gone = replace(FM, removed_at=datetime(2026, 11, 1, tzinfo=UTC))
    row = radio_row(gone, (gone,), radio, Claims())
    assert row is not None and (row["state"], row["problem"], row["modem"]) == ("stopped", None, None)


def test_a_radio_whose_type_has_another_driver_shows_neither_the_old_line_nor_its_modem_before_its_restart() -> None:
    line = connected(MERCURY)
    line.modem = SimpleNamespace(state="running", reason="", test="", deaf=False, hold=lambda: "")  # type: ignore[assignment]
    now_fm = replace(HF, kind="fm", type="kiss")
    row = radio_row(now_fm, (now_fm,), at_work(line, driver_key="mercury"), Claims())
    assert row is not None and (row["state"], row["problem"], row["modem"], row["lines"]) == ("stopped", None, None, [])


def test_a_connected_line_whose_modem_waits_with_a_reason_shows_the_modems_problem() -> None:
    line = connected(MERCURY)
    line.modem = SimpleNamespace(state="waiting", reason="receive_stalled", test="", deaf=False, hold=lambda: "")  # type: ignore[assignment]
    assert radio_health(HF, (HF,), at_work(line, "mercury"), Claims()) == RadioHealth(
        Source.State.CONNECTED, "modem.receive_stalled"
    )
    line.modem = SimpleNamespace(state="running", reason="", test="", deaf=False, hold=lambda: "")  # type: ignore[assignment]
    assert radio_health(HF, (HF,), at_work(line, "mercury"), Claims()) == RadioHealth(Source.State.CONNECTED)
