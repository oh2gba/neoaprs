"""The HF radio's Allow button on the daemon's side (neoaprs/mercuryrule.py, neoaprs/mercuryallow.py, the command `hf_allow_firewall`): the line run as an administrator (the installer's own, and the delete-then-add for a
wrong rule, in one run), what a declined prompt or a failed run leaves, the check asked again after the run and Mercury started after it. The elevated run is replaced by a fake (no UAC prompt in a test) and the
Firewall's answer by scripted verdicts; nothing here is run on Windows."""
import logging
import shlex
import stat
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from neoaprs import mercuryfirewall, mercuryhelper, mercuryrule
from neoaprs.config import DEFAULTS, Config
from neoaprs.mercuryfirewall import RULE_NAME, Verdict
from neoaprs.mercuryhelper import candidate_ports
from neoaprs.mercurymodem import Mercury
from neoaprs.source import Backoff
from neoaprs.web import hfhandlers
from neoaprs.web.tncwire import HfAllowFirewall
from neoaprs.winelevate import Declined
from tests.support import fakemercury
from tests.support.env import until

HF: Config = replace(DEFAULTS, hf_enabled=True, fm_enabled=False, mercury_keying="rts:/dev/ttyUSB0", mercury_sound_card="plughw:1,0", station_call="OH2GBA")
PROGRAM = Path(r"C:\Users\Op Erator\AppData\Local\Programs\NeoAPRS\bin\mercury\mercury.exe")
INSTALLER = Path(__file__).resolve().parent.parent / "packaging" / "windows" / "neoaprs.iss"
MISSING = Verdict("the Windows Firewall does not keep the network from Mercury: the rule 'NeoAPRS Mercury' that blocks it is missing", "firewall", False, "", "not shielded")
WRONG = Verdict("the Windows Firewall does not keep the network from Mercury: the rule 'mercury.exe' lets inbound connections reach it", "firewall", True, "mercury.exe", "not shielded")
OFF = Verdict("Windows Firewall is off for the Private profile", "firewall_off", False, "", "not shielded")
SHIELDED = Verdict()


# ---- the line run

def test_the_rule_is_added_with_the_line_of_the_installer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SystemRoot", r"C:\Windows")
    file, parameters = mercuryrule.command(PROGRAM, replace=False)
    assert file == r"C:\Windows\System32\netsh.exe"
    assert parameters == f'advfirewall firewall add rule name="{RULE_NAME}" dir=in action=block program="{PROGRAM}" description="NeoAPRS: the Mercury HF modem is reached by NeoAPRS on this computer only"'
    text = INSTALLER.read_text(encoding="utf-8")
    assert 'add rule name="NeoAPRS Mercury" dir=in action=block program="' in text and f'description="{mercuryrule.DESCRIPTION}"' in text, "the same name, direction, action and description as the installer's"


def test_a_wrong_rule_is_deleted_and_the_new_one_added_in_one_run_of_cmd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SystemRoot", r"C:\Windows")
    file, parameters = mercuryrule.command(PROGRAM, replace=True)
    netsh = r"C:\Windows\System32\netsh.exe"
    assert file == r"C:\Windows\System32\cmd.exe"
    assert parameters == f'/s /c ""{netsh}" advfirewall firewall delete rule name="{RULE_NAME}" & "{netsh}" {mercuryrule.add_arguments(PROGRAM)}"'
    assert parameters.index("delete rule") < parameters.index("add rule")


@pytest.mark.parametrize("path", [r"C:\100%\mercury.exe", 'C:\\a"b\\mercury.exe'])
def test_a_path_that_cmd_would_read_differently_is_not_run_in_a_replace(path: str) -> None:
    with pytest.raises(ValueError):
        mercuryrule.command(Path(path), replace=True)
    assert mercuryrule.command(Path(path), replace=False)[1].endswith('description="NeoAPRS: the Mercury HF modem is reached by NeoAPRS on this computer only"')


class Elevated:
    """The elevated run, replaced: what it was asked to run, and what happens (an exit code, a declined prompt or a failure)."""

    def __init__(self, outcome: int | BaseException = 0) -> None:
        self.outcome = outcome
        self.runs: list[tuple[str, str, float]] = []
        self.during: list[Any] = []

    async def __call__(self, file: str, parameters: str, timeout_sec: float) -> int:
        self.runs.append((file, parameters, timeout_sec))
        for look in self.during:
            look()
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


@pytest.fixture
def windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mercuryrule, "on_windows", lambda: True)


async def test_make_rule_logs_the_line_and_the_exit_code(windows: None, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    elevated = Elevated(0)
    monkeypatch.setattr(mercuryrule, "elevated", elevated)
    with caplog.at_level(logging.INFO, logger="neoaprs.mercury"):
        assert await mercuryrule.make_rule(PROGRAM, replace=False) == "ran"
    assert len(elevated.runs) == 1 and elevated.runs[0][1] == mercuryrule.add_arguments(PROGRAM)
    assert "running as administrator" in caplog.text and mercuryrule.add_arguments(PROGRAM) in caplog.text and "exit code 0" in caplog.text


@pytest.mark.parametrize("outcome,said", [(Declined(), "declined"), (OSError(5, "Access is denied"), "did not happen"), (TimeoutError("the program did not end in 60 s"), "did not end")])
async def test_a_prompt_that_is_declined_or_a_run_that_cannot_be_made_is_a_line_in_the_log_and_nothing_else(windows: None, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, outcome: BaseException, said: str) -> None:
    monkeypatch.setattr(mercuryrule, "elevated", Elevated(outcome))
    with caplog.at_level(logging.INFO, logger="neoaprs.mercury"):
        assert await mercuryrule.make_rule(PROGRAM, replace=True) == "not_run"
    assert said in caplog.text


async def test_nothing_is_run_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    elevated = Elevated(0)
    monkeypatch.setattr(mercuryrule, "elevated", elevated)
    monkeypatch.setattr(mercuryrule, "on_windows", lambda: False)
    assert await mercuryrule.make_rule(PROGRAM, replace=False) == "not_run" and elevated.runs == []


# ---- the modem part

def shipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runnable: bool = False) -> Path:
    """A Mercury that is the shipped one: the file `find` gives. With `runnable` it is a script that runs the fake Mercury."""
    program = tmp_path / "tools" / "mercury" / mercuryhelper.program_file()
    program.parent.mkdir(parents=True)
    program.write_text("#!/bin/sh\nexec " + " ".join(shlex.quote(a) for a in fakemercury.program()) + ' "$@"\n' if runnable else "")
    program.chmod(program.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr(mercuryhelper, "tools_dir", lambda: tmp_path / "tools")
    return program


class Firewall:
    """The Firewall's answers, one after the other (the last is kept), and what it was asked."""

    def __init__(self, *answers: Verdict) -> None:
        self.answers = list(answers)
        self.asked: list[tuple[Path, tuple[int, ...]]] = []

    def __call__(self, program: Path, ports: Any = ()) -> Verdict:
        self.asked.append((program, tuple(ports)))
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]


async def waiting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *answers: Verdict, runnable: bool = False) -> tuple[Mercury, Firewall, Elevated]:
    """A modem that has started on a Firewall that does not shield Mercury (the first answer), with the elevated run replaced."""
    program = shipped(tmp_path, monkeypatch, runnable)
    firewall = Firewall(*answers)
    elevated = Elevated(0)
    monkeypatch.setattr(mercuryfirewall, "check", firewall)
    monkeypatch.setattr(mercuryrule, "elevated", elevated)
    monkeypatch.setattr(mercuryrule, "on_windows", lambda: True)
    m = Mercury(tmp_path, finder=lambda: [str(program)], backoff=Backoff([0.1, 0.1]))
    m.ports = lambda: []
    await m.start(HF)
    return m, firewall, elevated


async def test_the_missing_rule_is_added_the_firewall_is_asked_again_and_the_owner_may_start_the_radio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    m, firewall, elevated = await waiting(tmp_path, monkeypatch, MISSING, MISSING, SHIELDED)
    try:
        assert m.state == "waiting" and m.reason == "firewall" and m.starts == 0 and len(firewall.asked) == 1
        seen: list[bool] = []
        elevated.during.append(lambda: seen.append(m.allowing))
        with caplog.at_level(logging.INFO, logger="neoaprs.mercury"):
            assert await m.allow_firewall() is True
        assert len(firewall.asked) == 3, "asked at the start, before the run (what to do) and after it (whether it is in force)"
        assert all(ports == tuple(candidate_ports()) for _, ports in firewall.asked), "with the ports Mercury may be given"
        assert len(elevated.runs) == 1 and elevated.runs[0][1].startswith(f'advfirewall firewall add rule name="{RULE_NAME}"') and elevated.runs[0][0].endswith("netsh.exe")
        assert seen == [True] and m.allowing is False, "the page's button waits while it runs"
        assert "exit code 0" in caplog.text
    finally:
        await m.stop()


async def test_a_wrong_rule_is_replaced_in_one_elevated_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    m, firewall, elevated = await waiting(tmp_path, monkeypatch, WRONG, WRONG, SHIELDED)
    try:
        assert await m.allow_firewall() is True
        assert len(elevated.runs) == 1 and elevated.runs[0][0].endswith("cmd.exe") and "delete rule" in elevated.runs[0][1] and "add rule" in elevated.runs[0][1]
    finally:
        await m.stop()


@pytest.mark.skipif(sys.platform == "win32", reason="the stand-in Mercury is a shell script (`shipped(runnable=True)`), which Windows cannot run; the flow is the same everywhere")
async def test_the_start_that_follows_the_run_asks_again_and_starts_mercury(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    m, firewall, elevated = await waiting(tmp_path, monkeypatch, MISSING, MISSING, SHIELDED, SHIELDED, runnable=True)
    try:
        assert m.starts == 0
        assert await m.allow_firewall() is True
        asked = len(firewall.asked)
        await m.start(HF)                                  # (what the controller does for the command: the HF radio is started the usual way)
        assert len(firewall.asked) == asked + 1, "the check is asked again by the start itself"
        await until(lambda: m.running, 10.0)
        assert m.starts == 1 and m.reason == ""
    finally:
        await m.stop()


async def test_a_declined_prompt_leaves_the_status_as_it_was_and_logs_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    m, firewall, elevated = await waiting(tmp_path, monkeypatch, MISSING)
    try:
        elevated.outcome = Declined()
        before = (m.state, m.problem, m.reason, m.lets_in)
        with caplog.at_level(logging.INFO, logger="neoaprs.mercury"):
            assert await m.allow_firewall() is False
        assert (m.state, m.problem, m.reason, m.lets_in) == before and m.allowing is False and len(elevated.runs) == 1 and len(firewall.asked) == 2
        assert "declined" in caplog.text
        assert await m.allow_firewall() is False and len(elevated.runs) == 2, "it can be tried again"
    finally:
        await m.stop()


async def test_a_run_that_cannot_be_made_leaves_the_status_as_it_was(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    m, firewall, elevated = await waiting(tmp_path, monkeypatch, WRONG)
    try:
        elevated.outcome = OSError(740, "The requested operation requires elevation")
        before = (m.state, m.problem, m.reason, m.lets_in)
        assert await m.allow_firewall() is False
        assert (m.state, m.problem, m.reason, m.lets_in) == before and before[3] == "mercury.exe", "the rule that lets Mercury in stays named"
    finally:
        await m.stop()


async def test_a_run_after_which_the_firewall_still_lets_mercury_in_says_what_it_says_now(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    m, firewall, elevated = await waiting(tmp_path, monkeypatch, MISSING, MISSING, OFF)
    try:
        assert await m.allow_firewall() is False
        assert m.state == "waiting" and m.reason == "firewall_off" and "Private" in m.problem and m.allowing is False
    finally:
        await m.stop()


async def test_a_firewall_that_turned_out_to_be_off_is_not_made_a_rule_for(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    m, firewall, elevated = await waiting(tmp_path, monkeypatch, MISSING, OFF)
    try:
        assert await m.allow_firewall() is False
        assert elevated.runs == [] and m.reason == "firewall_off"
    finally:
        await m.stop()


async def test_a_firewall_that_shields_mercury_by_now_needs_no_prompt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    m, firewall, elevated = await waiting(tmp_path, monkeypatch, MISSING, SHIELDED)
    try:
        assert await m.allow_firewall() is True and elevated.runs == []
    finally:
        await m.stop()


async def test_the_button_does_nothing_for_any_other_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    m, firewall, elevated = await waiting(tmp_path, monkeypatch, OFF)
    try:
        assert m.reason == "firewall_off" and await m.allow_firewall() is False and elevated.runs == [] and len(firewall.asked) == 1
    finally:
        await m.stop()


async def test_a_second_press_while_the_first_waits_for_the_prompt_does_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    m, firewall, elevated = await waiting(tmp_path, monkeypatch, MISSING, MISSING, SHIELDED)
    try:
        again: list[bool] = []
        first = elevated.__call__

        async def with_a_second_press(file: str, parameters: str, timeout_sec: float) -> int:
            again.append(await m.allow_firewall())
            return await first(file, parameters, timeout_sec)

        monkeypatch.setattr(mercuryrule, "elevated", with_a_second_press)
        assert await m.allow_firewall() is True
        assert again == [False] and len(elevated.runs) == 1, "the second press was refused"
    finally:
        await m.stop()


# ---- the command

async def test_the_command_starts_the_hf_radio_when_the_firewall_keeps_the_network_from_mercury_and_otherwise_does_nothing() -> None:
    started: list[str] = []
    answers = iter([True, False])

    async def allow_firewall() -> bool:
        return next(answers)

    ctl = SimpleNamespace(mercury=SimpleNamespace(allow_firewall=allow_firewall), start_hf=lambda: started.append("hf"))
    ctx: Any = SimpleNamespace(ctl=ctl)
    await hfhandlers.hf_allow_firewall(ctx, HfAllowFirewall(cmd="hf_allow_firewall"))
    assert started == ["hf"]
    await hfhandlers.hf_allow_firewall(ctx, HfAllowFirewall(cmd="hf_allow_firewall"))
    assert started == ["hf"], "no start when the rule is not in force; and no error either"

