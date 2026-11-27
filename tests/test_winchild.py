"""The Windows calls for the child programs (neoaprs/winchild.py) against a fake kernel32: the Ctrl-C
that asks a program to end, the job that ends the children with the daemon, the keying line lowered
after a Windows end, and the Mercury end that uses them. Needs no Windows; test_windows_child_end.py
makes the real calls.
"""

import ctypes
import subprocess
import threading
import time
from typing import Any

import pytest

from neoaprs import mercuryhelper, winchild
from neoaprs.mercuryhelper import Program


class Kernel:
    """kernel32 as far as winchild calls it: each call is recorded, and answers as set."""

    def __init__(self, **answers: Any) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.answers = {"AttachConsole": 1, "GenerateConsoleCtrlEvent": 1}
        self.answers |= {"CreateJobObjectW": 7, "SetInformationJobObject": 1, "OpenProcess": 9}
        self.answers |= {"AssignProcessToJobObject": 1}
        self.answers |= answers
        self.flags: list[int] = []

    def __getattr__(self, name: str) -> Any:
        def call(*args: Any) -> Any:
            self.calls.append((name, *args))
            if name == "SetInformationJobObject":
                self.flags.append(args[2]._obj.basic.limit_flags)
            return self.answers.get(name, 1)

        return call

    def names(self) -> list[str]:
        return [c[0] for c in self.calls]


@pytest.fixture(autouse=True)
def _fresh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(winchild, "_job", None)


class Asker:
    """subprocess.run as ask_to_end starts the asker: what it was given, and the exit it answers with."""

    def __init__(self, code: int = winchild.SENT, hangs: bool = False) -> None:
        self.code, self.hangs = code, hangs
        self.argv: list[str] = []
        self.options: dict[str, Any] = {}

    def __call__(self, argv: list[str], **options: Any) -> Any:
        self.argv, self.options = argv, options
        if self.hangs:
            raise subprocess.TimeoutExpired(argv, options["timeout"])
        return subprocess.CompletedProcess(argv, self.code, stdout=b"[]")


def test_the_daemon_asks_through_a_disposable_hidden_asker_and_never_touches_a_console() -> None:
    """A daemon alone on a console that shows (a runner's session, a console program started by a
    double click) may not let go of it; the asker's console is its own."""
    asker = Asker()
    assert winchild.ask_to_end(4321, asker)
    assert asker.argv[-3:] == ["-m", "neoaprs.winask", "4321"] or asker.argv[-2:] == [winchild.ASKER_FLAG, "4321"]
    assert asker.options["timeout"] == winchild.ASKER_SEC and asker.options["stdin"] == subprocess.DEVNULL
    assert asker.options["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)
    assert not winchild.ask_to_end(4321, Asker(winchild.ATTACH_FAILED)), "not sent: the hard end follows"
    assert not winchild.ask_to_end(4321, Asker(hangs=True)), "an asker that does not answer is no ask"


def test_the_frozen_build_starts_its_own_program_with_the_asker_flag() -> None:
    assert winchild.asker_argv(55, frozen=True, executable="C:/NeoAPRS/neoaprsw.exe") == [
        "C:/NeoAPRS/neoaprsw.exe",
        "--winask",
        "55",
    ]
    assert winchild.asker_argv(55, frozen=False, executable="python") == ["python", "-m", "neoaprs.winask", "55"]


def test_the_asker_lets_go_of_its_own_console_attaches_and_sends_ctrl_break_to_the_group() -> None:
    k = Kernel()
    steps: winchild.Steps = []
    assert winchild.send_event(77, winchild.CTRL_BREAK_EVENT, 77, k, steps) == winchild.SENT
    assert k.names() == ["FreeConsole", "AttachConsole", "GenerateConsoleCtrlEvent", "FreeConsole"]
    assert ("GenerateConsoleCtrlEvent", 1, 77) in k.calls and [s["call"] for s in steps] == k.names()
    assert winchild.send_event(77, 1, 77, Kernel(AttachConsole=0)) == winchild.ATTACH_FAILED
    assert winchild.send_event(77, 1, 77, Kernel(GenerateConsoleCtrlEvent=0)) == winchild.EVENT_FAILED


def test_the_asker_says_a_bad_argument_and_prints_its_calls(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from neoaprs import winask

    assert winask.main([]) == winchild.BAD_ARGUMENT and winask.main(["x"]) == winchild.BAD_ARGUMENT
    monkeypatch.setattr(winchild, "kernel32", lambda: Kernel())
    assert winask.main(["77"]) == winchild.SENT
    assert '"call": "GenerateConsoleCtrlEvent"' in capsys.readouterr().out


def test_each_child_goes_into_one_job_that_kills_on_close() -> None:
    k = Kernel()
    assert winchild.tie_to_daemon(41, k) and winchild.tie_to_daemon(42, k)
    assert k.names().count("CreateJobObjectW") == 1 and k.flags == [winchild.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE]
    assert ("AssignProcessToJobObject", 7, 9) in k.calls and k.names().count("CloseHandle") == 2, (
        "the job's handle stays open for the daemon's life; each process handle is closed"
    )
    assert ctypes.sizeof(winchild.ExtendedLimits) == (144 if ctypes.sizeof(ctypes.c_void_p) == 8 else 112)


def test_a_child_is_not_tied_when_the_job_cannot_be_made_or_the_process_opened() -> None:
    k = Kernel(SetInformationJobObject=0)
    assert not winchild.tie_to_daemon(41, k) and "CloseHandle" in k.names() and "OpenProcess" not in k.names()
    assert not winchild.tie_to_daemon(41, Kernel(OpenProcess=0))


class FakePort:
    """pyserial's Serial as drop_line uses it: what the lines were at the moment of the open."""

    def __init__(self, hangs: threading.Event | None = None) -> None:
        self.rts = self.dtr = True  # pyserial's own defaults
        self.port: str | None = None
        self.opened_with: list[tuple[str | None, bool, bool]] = []
        self.closed = False
        self.hangs = hangs

    def open(self) -> None:
        self.opened_with.append((self.port, self.rts, self.dtr))
        if self.hangs is not None:
            self.hangs.wait(30)

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize("keying", ["rts:COM10", "dtr:com3"])
def test_the_keying_line_is_opened_with_both_lines_low_from_the_first_moment(keying: str) -> None:
    port = FakePort()
    assert winchild.drop_line(keying, lambda: port)
    assert port.opened_with == [(keying.split(":")[1].upper(), False, False)] and port.closed


@pytest.mark.parametrize("keying", ["vox", "cm108", "rts:/dev/ttyUSB0", "rts:COM3 x"])
def test_no_port_is_opened_for_a_keying_that_is_no_com_line(keying: str) -> None:
    port = FakePort()
    assert not winchild.drop_line(keying, lambda: port) and port.opened_with == []


def test_a_port_whose_open_hangs_does_not_hold_the_stop() -> None:
    hangs = threading.Event()
    port = FakePort(hangs)
    started = time.monotonic()
    try:
        assert not winchild.drop_line("rts:COM10", lambda: port, wait_sec=0.2)
        assert time.monotonic() - started < 10.0
    finally:
        hangs.set()


class Process:
    pid = 77

    def __init__(self, ends: bool) -> None:
        self.ends = ends

    def wait(self, timeout: float | None = None) -> int:
        if not self.ends:
            raise subprocess.TimeoutExpired("mercury", timeout or 0)
        return 0


def test_mercury_on_windows_that_ends_when_asked_has_no_port_opened_and_a_killed_one_has_its_line_lowered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ended: list[int] = []
    monkeypatch.setattr(mercuryhelper, "_end_tree", lambda process: ended.append(process.pid))
    monkeypatch.setattr(mercuryhelper.nodevices, "on", lambda: False)
    program = Program(lambda code, lines: None)
    program.keying = "rts:COM10"
    port = FakePort()
    program._end_windows(Process(ends=True), Asker(), lambda: port)  # type: ignore[arg-type]
    assert ended == [] and port.opened_with == [], "it unkeyed itself: opening the port could only key it"
    program._end_windows(Process(ends=False), Asker(), lambda: port)  # type: ignore[arg-type]
    assert ended == [77] and port.opened_with == [("COM10", False, False)], "asked, not gone: killed, then the line"
    program._end_windows(Process(ends=True), Asker(winchild.ATTACH_FAILED), lambda: port)  # type: ignore[arg-type]
    assert ended == [77, 77] and len(port.opened_with) == 2, "not asked: the hard end at once"


def test_under_the_no_devices_switch_the_keying_line_is_not_opened(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mercuryhelper, "_end_tree", lambda process: None)
    monkeypatch.setattr(mercuryhelper.nodevices, "on", lambda: True)
    program = Program(lambda code, lines: None)
    program.keying = "rts:COM10"
    port = FakePort()
    program._end_windows(Process(ends=False), Asker(), lambda: port)  # type: ignore[arg-type]
    assert port.opened_with == []


def test_mercury_is_started_in_a_group_of_its_own_to_be_asked_and_direwolf_keeps_its_stop() -> None:
    """Direwolf ends when its input closes (-Q) and cleans up on SIGINT only: a Ctrl-Break would only kill it."""
    from neoaprs import direwolfprogram

    assert Program.asked_by_break and not direwolfprogram.Program.asked_by_break
    assert winchild.CTRL_BREAK_EVENT == 1
