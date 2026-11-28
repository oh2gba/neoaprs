"""A radio's state and problem are decided in one place (neoaprs/radiohealth.py, neoaprs/tnchealth.py), and the
row of the topic `radios` only formats them: the cases where the row said something stale."""

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, get_args

import pytest

from neoaprs.claims import Claims
from neoaprs.radiohealth import radio_health
from neoaprs.radiospec import RadioSpec
from neoaprs.radiotype import FM_ID, HF_ID
from neoaprs.source import Source
from neoaprs.tnc import Tnc
from neoaprs.tncprofile import KISS, MERCURY
from neoaprs.tnchealth import RadioHealth, line_health
from neoaprs.web.tncwire import ModemState
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
    line.modem = SimpleNamespace(
        state="running", reason="", test="", deaf=False, rig_problem="", hold=lambda: "", frame_hold=lambda: ""
    )  # type: ignore[assignment]
    now_fm = replace(HF, kind="fm", type="kiss")
    row = radio_row(now_fm, (now_fm,), at_work(line, driver_key="mercury"), Claims())
    assert row is not None and (row["state"], row["problem"], row["modem"], row["lines"]) == ("stopped", None, None, [])


def test_a_connected_line_whose_modem_waits_with_a_reason_shows_the_modems_problem() -> None:
    line = connected(MERCURY)
    line.modem = SimpleNamespace(
        state="waiting",
        reason="receive_stalled",
        test="",
        deaf=False,
        rig_problem="",
        hold=lambda: "",
        frame_hold=lambda: "",
    )  # type: ignore[assignment]
    assert radio_health(HF, (HF,), at_work(line, "mercury"), Claims()) == RadioHealth(
        Source.State.CONNECTED, "modem.receive_stalled"
    )
    line.modem = SimpleNamespace(
        state="running", reason="", test="", deaf=False, rig_problem="", hold=lambda: "", frame_hold=lambda: ""
    )  # type: ignore[assignment]
    assert radio_health(HF, (HF,), at_work(line, "mercury"), Claims()) == RadioHealth(Source.State.CONNECTED)


REASONS = get_args(ModemState.model_fields["reason"].annotation)
STATES = (
    Source.State.CONNECTED,
    Source.State.CONNECTING,
    Source.State.WAITING,
    Source.State.SILENT,
    Source.State.STOPPED,
)


def expected(state: Source.State, reason: str) -> str | None:
    """The problem as 0.24.0 showed it, but for a stalled modem behind a connected line."""
    if state is Source.State.CONNECTED:
        return "modem.receive_stalled" if reason == "receive_stalled" else None
    if reason:
        return f"modem.{reason}"
    return "radio.silent" if state is Source.State.SILENT else "radio.not_connected"


@pytest.mark.parametrize("state", STATES, ids=lambda s: s.value)
@pytest.mark.parametrize("reason", REASONS, ids=lambda r: r or "none")
def test_every_line_state_with_every_modem_reason_shows_the_problem_of_before_and_a_stalled_modem_also_while_connected(
    state: Source.State, reason: str
) -> None:
    assert "receive_stalled" in REASONS and len(REASONS) >= 9
    line = SimpleNamespace(
        state=state,
        problem="",
        write_stuck=None,
        entering_kiss=False,
        usable=state is Source.State.CONNECTED,
        searching=[],
        silent_since=None,
        sends_text=False,
        modem_in_use=SimpleNamespace(
            state="waiting" if reason else "running", reason=reason, test="", deaf=False, rig_problem=""
        ),
        why_unusable=lambda: "",
    )
    assert line_health(line).code == expected(state, reason)  # type: ignore[arg-type]


def test_a_test_tone_hides_the_modems_problem_and_a_deaf_modem_shows_only_while_connected() -> None:
    def code(line_state: Source.State, **modem: object) -> str | None:
        values: dict[str, object] = {
            "state": "running",
            "reason": "",
            "test": "",
            "deaf": False,
            "rig_problem": "",
            **modem,
        }
        line = SimpleNamespace(
            state=line_state, problem="", write_stuck=None, entering_kiss=False, usable=True, searching=[],
            silent_since=None, sends_text=False, modem_in_use=SimpleNamespace(**values), why_unusable=lambda: "",
        )  # fmt: skip
        return line_health(line).code  # type: ignore[arg-type]

    assert code(Source.State.CONNECTED, deaf=True) == "modem.receive_deaf"
    assert code(Source.State.CONNECTED, deaf=True, test="tune") is None
    assert code(Source.State.WAITING, state="waiting", reason="sound_card", test="tune") is None
    assert code(Source.State.CONNECTED, rig_problem="rig_silent") == "modem.rig_silent"
    assert code(Source.State.CONNECTED, rig_problem="rig_keyed_long") == "modem.rig_keyed_long"
    assert code(Source.State.CONNECTED, rig_problem="rig_silent", test="key") is None, "the test's own outcome shows"


def test_the_wire_row_of_a_connected_line_with_a_deaf_modem_carries_the_problem_the_page_reads() -> None:
    line = connected(MERCURY)
    line.modem = SimpleNamespace(
        state="running", reason="", test="", deaf=True, rig_problem="", hold=lambda: "", frame_hold=lambda: ""
    )  # type: ignore[assignment]
    row = radio_row(HF, (HF,), at_work(line, "mercury"), Claims())
    assert row is not None
    assert (row["state"], row["problem"]) == ("connected", {"code": "modem.receive_deaf", "params": {}})
