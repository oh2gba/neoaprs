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
        self.answers = {"AttachConsole": 1, "SetConsoleCtrlHandler": 1, "GenerateConsoleCtrlEvent": 1}
        self.answers |= {"CreateJobObjectW": 7, "SetInformationJobObject": 1, "OpenProcess": 9}
        self.answers |= {"AssignProcessToJobObject": 1, "GetConsoleProcessList": 1, "GetConsoleWindow": 0}
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
    monkeypatch.setattr(winchild, "_handler", None)
    monkeypatch.setattr(winchild, "_job", None)


ASK = ["GetConsoleProcessList", "GetConsoleWindow", "FreeConsole", "AttachConsole", "GenerateConsoleCtrlEvent"]
LEAVE = ["FreeConsole", "GetConsoleProcessList", "GetConsoleWindow"]


def test_the_ctrl_c_goes_to_the_programs_console_after_this_process_lets_go_of_its_hidden_one() -> None:
    """A program started from a launcher (a venv's python.exe) has a hidden console of its own, and
    AttachConsole refuses a process that has one (ERROR_ACCESS_DENIED)."""
    k = Kernel()
    assert winchild.ask_to_end(1234, k)
    assert k.names() == ["SetConsoleCtrlHandler", *ASK, *LEAVE]
    assert ("AttachConsole", 1234) in k.calls and ("GenerateConsoleCtrlEvent", 0, 0) in k.calls
    assert k.calls[0][2] is True, "a handler, not the ignore flag that children inherit"
    k = Kernel(GetConsoleProcessList=0)
    assert winchild.ask_to_end(1234, k) and k.names()[:2] == ["GetConsoleProcessList", "AttachConsole"], (
        "no console of its own (the installed daemon): nothing to let go of; the handler is set once"
    )


def test_no_ctrl_c_is_sent_from_a_console_with_a_window_or_without_the_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    k = Kernel(GetConsoleWindow=5)
    assert not winchild.ask_to_end(1234, k)
    assert "FreeConsole" not in k.names() and "AttachConsole" not in k.names(), (
        "the terminal someone looks at is kept: the hard end follows"
    )
    k = Kernel(AttachConsole=0)
    assert not winchild.ask_to_end(1234, k) and "GenerateConsoleCtrlEvent" not in k.names()
    monkeypatch.setattr(winchild, "_handler", None)
    k = Kernel(SetConsoleCtrlHandler=0)
    assert not winchild.ask_to_end(1234, k) and k.names() == ["SetConsoleCtrlHandler"], (
        "the Ctrl-C would end the daemon too"
    )


def test_only_the_echo_of_an_ask_is_taken_and_every_other_event_goes_on_to_pythons_own_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(winchild, "_asked_at", 100.0)
    assert winchild.ours(winchild.CTRL_C_EVENT, 101.0) and winchild.ours(winchild.CTRL_BREAK_EVENT, 105.0)
    assert not winchild.ours(winchild.CTRL_C_EVENT, 100.0 + winchild.ECHO_SEC + 1), (
        "a Ctrl-C of the daemon's own terminal later stops it as before"
    )
    assert not winchild.ours(2, 101.0), "a close event is never taken"


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
    k = Kernel()
    program._end_windows(Process(ends=True), k, lambda: port)  # type: ignore[arg-type]
    assert ended == [] and "GenerateConsoleCtrlEvent" in k.names() and port.opened_with == [], (
        "it unkeyed itself: opening the port could only key it"
    )
    program._end_windows(Process(ends=False), Kernel(), lambda: port)  # type: ignore[arg-type]
    assert ended == [77] and port.opened_with == [("COM10", False, False)], "asked, not gone: killed, then the line"
    program._end_windows(Process(ends=True), Kernel(AttachConsole=0), lambda: port)  # type: ignore[arg-type]
    assert ended == [77, 77] and len(port.opened_with) == 2, "no console to ask through: the hard end at once"


def test_under_the_no_devices_switch_the_keying_line_is_not_opened(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mercuryhelper, "_end_tree", lambda process: None)
    monkeypatch.setattr(mercuryhelper.nodevices, "on", lambda: True)
    program = Program(lambda code, lines: None)
    program.keying = "rts:COM10"
    port = FakePort()
    program._end_windows(Process(ends=False), Kernel(), lambda: port)  # type: ignore[arg-type]
    assert port.opened_with == []


def test_each_call_of_the_ask_is_written_down_with_its_result() -> None:
    """One run on a Windows machine then tells which call stops the ask."""
    steps: winchild.Steps = []
    assert not winchild.ask_to_end(1234, Kernel(GenerateConsoleCtrlEvent=0), steps)
    calls = [(s["call"], s["result"]) for s in steps if "call" in s]
    assert calls[:6] == [
        ("SetConsoleCtrlHandler", 1),
        ("GetConsoleProcessList", 1),
        ("GetConsoleWindow", 0),
        ("FreeConsole", 1),
        ("AttachConsole", 1),
        ("GenerateConsoleCtrlEvent", 0),
    ] and all("error" in s for s in steps if "call" in s)
    assert steps[-1] == {"note": "after: attached to a console: True"}, "the state it is left in"


def test_ctrl_break_goes_to_the_group_on_its_console_or_on_this_ones() -> None:
    k = Kernel()
    assert winchild.break_group(55, attach=True, k=k)
    assert k.names() == ["SetConsoleCtrlHandler", *ASK, *LEAVE] and ("GenerateConsoleCtrlEvent", 1, 55) in k.calls
    k = Kernel()
    assert winchild.break_group(55, attach=False, k=k) and k.names() == ["GenerateConsoleCtrlEvent"]
