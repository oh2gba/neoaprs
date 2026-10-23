"""The runner of the message alert (neoaprs/services/alerts.py) where a real command does not reach: the Windows way (PowerShell, started by a thread) on a fake `subprocess`, the ways a run goes wrong (it cannot start,
runs out of time, the wait for it fails), ending a process and what it started, and the answer of the test button when there is nothing to run. The runs of real commands through the shell are tests/test_alerts.py."""

import base64
import logging
import subprocess
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

from neoaprs.services import alerts as alerts_module
from neoaprs.services.alerts import (
    POWERSHELL,
    POWERSHELL_POSTLUDE,
    POWERSHELL_PRELUDE,
    Alerts,
    Outcome,
    _Running,
)
from tests.support.clock import FixedClock
from tests.support.ptyline import posix_only
from tests.support.env import ON_AIR


class FakeProc:
    """A process the fake Popen made: what `communicate` answers (an exception is raised, once, then the next answer comes) and whether it has ended."""

    def __init__(
        self, answers: list[Any], returncode: int = 0, ended: bool = False
    ) -> None:
        self.answers, self.returncode, self.ended = list(answers), returncode, ended
        self.pid = 4242
        self.killed = 0
        self.timeouts: list[float | None] = []

    def communicate(self, timeout: float | None = None) -> tuple[bytes, bytes]:
        self.timeouts.append(timeout)
        answer = self.answers.pop(0) if self.answers else (b"", b"")
        if isinstance(answer, BaseException):
            raise answer
        self.ended = True
        return answer

    def poll(self) -> int | None:
        return self.returncode if self.ended else None

    def kill(self) -> None:
        self.killed += 1
        self.ended = True


class FakeSubprocess:
    """The part of `subprocess` the runner uses: Popen makes the processes of the test (or fails), run is the `taskkill`."""

    DEVNULL, PIPE, TimeoutExpired = (
        subprocess.DEVNULL,
        subprocess.PIPE,
        subprocess.TimeoutExpired,
    )

    def __init__(
        self,
        procs: list[FakeProc] | None = None,
        popen_error: Exception | None = None,
        taskkill_error: Exception | None = None,
    ) -> None:
        self.procs = list(procs or [])
        self.popen_error, self.taskkill_error = popen_error, taskkill_error
        self.started: list[tuple[list[str], dict[str, Any]]] = []
        self.taskkills: list[list[str]] = []

    def Popen(self, argv: list[str], **kwargs: Any) -> FakeProc:  # noqa: N802
        if self.popen_error is not None:
            raise self.popen_error
        self.started.append((argv, kwargs))
        return self.procs.pop(0)

    def run(self, argv: list[str], **kwargs: Any) -> None:
        self.taskkills.append(argv)
        if self.taskkill_error is not None:
            raise self.taskkill_error


def windows(monkeypatch: pytest.MonkeyPatch, fake: FakeSubprocess) -> Alerts:
    """Alerts that think they run on Windows, on a fake subprocess."""
    monkeypatch.setattr(alerts_module, "subprocess", fake)
    monkeypatch.setattr(alerts_module, "sys", SimpleNamespace(platform="win32"))
    config = replace(ON_AIR, messages_alert_command="Write-Host hi")
    return Alerts(lambda: config, FixedClock(), timeout_sec=7.0)


async def test_the_windows_run_gives_powershell_the_line_as_an_encoded_script_and_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proc = FakeProc([(b"hello\n", b"")])
    fake = FakeSubprocess([proc])
    alerts = windows(monkeypatch, fake)
    assert await alerts.test() == (True, "ran")
    [(argv, kwargs)] = fake.started
    assert (
        tuple(argv[:-1]) == POWERSHELL
        and base64.b64decode(argv[-1]).decode("utf-16-le")
        == POWERSHELL_PRELUDE + "Write-Host hi" + POWERSHELL_POSTLUDE
    )
    assert (
        kwargs["env"]["NEOAPRS_FROM"] == "NEOAPRS"
        and kwargs["stdin"] == subprocess.DEVNULL
    )
    assert proc.timeouts == [7.0] and proc.killed == 0 and fake.taskkills == [], (
        "a run that ended is not killed"
    )


async def test_the_windows_run_tells_the_status_and_the_first_line_of_what_the_command_said_on_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alerts = windows(
        monkeypatch,
        FakeSubprocess([FakeProc([(b"", b"\nno display\nmore\n")], returncode=3)]),
    )
    assert await alerts.test() == (False, "exit code 3: no display")


async def test_a_windows_run_that_cannot_start_is_a_failure_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alerts = windows(
        monkeypatch, FakeSubprocess(popen_error=FileNotFoundError("powershell.exe"))
    )
    ok, text = await alerts.test()
    assert not ok and text == "the alert command could not run: powershell.exe"


async def test_a_windows_run_that_runs_out_of_time_is_killed_with_what_it_started(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proc = FakeProc([subprocess.TimeoutExpired("powershell", 7.0), (b"", b"")])
    fake = FakeSubprocess([proc])
    alerts = windows(monkeypatch, fake)
    assert await alerts.test() == (
        False,
        "the alert command did not end within 7 s: killed",
    )
    assert (
        fake.taskkills == [["taskkill", "/T", "/F", "/PID", "4242"]]
        and proc.killed == 1
    ), "the tree is ended, then the process itself"
    assert len(proc.timeouts) == 2, (
        "and what it wrote is collected, so that nothing is left to wait for"
    )


async def test_a_windows_run_whose_wait_fails_is_killed_and_told(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proc = FakeProc([OSError("the pipe broke")])
    fake = FakeSubprocess([proc])
    alerts = windows(monkeypatch, fake)
    assert await alerts.test() == (
        False,
        "the alert command could not run: the pipe broke",
    )
    assert proc.killed == 1 and len(fake.taskkills) == 1


async def test_a_failed_run_is_logged_through_the_hourly_warning_on_windows_too(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, "neoaprs.alerts")
    alerts = windows(monkeypatch, FakeSubprocess(popen_error=OSError("gone")))
    await alerts._run("Write-Host hi", {}, "OH2RDG")
    assert [r.getMessage() for r in caplog.records] == [
        "the alert command could not run: gone (told once an hour)"
    ]


def test_a_process_that_has_ended_or_was_never_made_is_not_killed() -> None:
    running = _Running()
    running.kill()  # (nothing was started)
    done = FakeProc([], ended=True)
    running.set(done)  # type: ignore[arg-type]
    running.kill()
    assert done.killed == 0


def test_taskkill_that_fails_does_not_keep_the_process_from_being_killed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeSubprocess(taskkill_error=TimeoutError("taskkill hangs"))
    monkeypatch.setattr(alerts_module, "subprocess", fake)
    proc = FakeProc([])
    running = _Running()
    running.set(proc)  # type: ignore[arg-type]
    running.kill()
    assert len(fake.taskkills) == 1 and proc.killed == 1


def test_a_process_that_ends_while_it_is_killed_is_no_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(alerts_module, "subprocess", FakeSubprocess())
    proc = FakeProc([])

    def gone() -> None:
        raise OSError("already ended")

    proc.kill = gone  # type: ignore[method-assign]
    running = _Running()
    running.set(proc)  # type: ignore[arg-type]
    running.kill()


@posix_only                                                  # (the POSIX shell runner; Windows runs PowerShell, tested above)
def test_the_process_of_the_shell_is_killed_by_itself_where_its_session_is_gone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proc = FakeProc([])

    def no_group(pid: int, sig: int) -> None:
        raise ProcessLookupError(pid)

    monkeypatch.setattr(alerts_module.os, "killpg", no_group)
    Alerts._kill(proc)  # type: ignore[arg-type]
    assert proc.killed == 1


def test_on_windows_the_process_is_killed_by_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(alerts_module, "sys", SimpleNamespace(platform="win32"))
    proc = FakeProc([])
    Alerts._kill(proc)  # type: ignore[arg-type]
    assert proc.killed == 1


@posix_only                                                  # (the POSIX shell runner; Windows runs PowerShell, tested above)
async def test_a_shell_that_cannot_be_started_is_a_failure_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def refuse(*args: object, **kwargs: object) -> None:
        raise OSError("no fork")

    monkeypatch.setattr(alerts_module.asyncio, "create_subprocess_shell", refuse)
    alerts = Alerts(
        lambda: replace(ON_AIR, messages_alert_command="true"), FixedClock()
    )
    assert await alerts.test() == (False, "the alert command could not run: no fork")


async def test_the_test_button_with_no_command_is_an_error_the_page_shows() -> None:
    alerts = Alerts(lambda: replace(ON_AIR, messages_alert_command="  "), FixedClock())
    with pytest.raises(ValueError, match="no alert command"):
        await alerts.test()


def test_an_outcome_tells_what_the_page_is_shown() -> None:
    assert Outcome(problem="could not run").short == "could not run"
    assert (
        Outcome(status=2).short == "exit code 2"
        and Outcome(status=2, err="\n  bad  \n").short == "exit code 2: bad"
    )
    assert (
        Outcome(out="a", err="b").output == "ab"
        and not Outcome(status=1).ok
        and Outcome().ok
    )
