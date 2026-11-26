"""The Windows calls for the child programs (neoaprs/winchild.py) against a fake kernel32: the Ctrl-C
that asks a program to end, the job that ends the children with the daemon, the keying line lowered
after a Windows end, and the Mercury end that uses them. Needs no Windows; test_windows_child_end.py
makes the real calls.
"""

import ctypes
import subprocess
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
        self.answers |= {"AssignProcessToJobObject": 1, "CreateFileW": 11, "EscapeCommFunction": 1} | answers
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


def test_the_ctrl_c_goes_to_the_programs_console_and_this_process_takes_none_of_it() -> None:
    k = Kernel()
    assert winchild.ask_to_end(1234, k)
    assert k.names() == ["AttachConsole", "SetConsoleCtrlHandler", "GenerateConsoleCtrlEvent", "FreeConsole"]
    assert k.calls[0] == ("AttachConsole", 1234) and k.calls[2] == ("GenerateConsoleCtrlEvent", 0, 0)
    assert k.calls[1][2] is True, "a handler that says handled, not the ignore flag that children inherit"
    assert winchild.ask_to_end(1234, k)
    assert k.names()[4:] == ["AttachConsole", "GenerateConsoleCtrlEvent", "FreeConsole"], "the handler is set once"


def test_no_ctrl_c_is_sent_without_the_console_or_without_the_handler() -> None:
    k = Kernel(AttachConsole=0)
    assert not winchild.ask_to_end(1234, k) and k.names() == ["AttachConsole"], (
        "a daemon with a console of its own cannot attach: the hard end follows"
    )
    k = Kernel(SetConsoleCtrlHandler=0)
    assert not winchild.ask_to_end(1234, k)
    assert k.names() == ["AttachConsole", "SetConsoleCtrlHandler", "FreeConsole"], "the Ctrl-C would end the daemon too"


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


@pytest.mark.parametrize("keying, line", [("rts:COM10", winchild.CLRRTS), ("dtr:com3", winchild.CLRDTR)])
def test_the_keying_line_of_the_setting_is_lowered(keying: str, line: int) -> None:
    k = Kernel()
    assert winchild.drop_line(keying, k)
    port = keying.split(":")[1].upper()
    assert k.calls[0][:2] == ("CreateFileW", f"\\\\.\\{port}") and k.calls[1] == ("EscapeCommFunction", 11, line)
    assert k.calls[2] == ("CloseHandle", 11)


@pytest.mark.parametrize("keying", ["vox", "cm108", "rts:/dev/ttyUSB0", "rts:COM3 x"])
def test_no_port_is_opened_for_a_keying_that_is_no_com_line(keying: str) -> None:
    k = Kernel()
    assert not winchild.drop_line(keying, k) and k.calls == []


def test_a_port_that_cannot_be_opened_is_not_lowered() -> None:
    k = Kernel(CreateFileW=ctypes.c_void_p(-1).value)
    assert not winchild.drop_line("rts:COM10", k) and k.names() == ["CreateFileW"]


class Process:
    pid = 77

    def __init__(self, ends: bool) -> None:
        self.ends = ends

    def wait(self, timeout: float | None = None) -> int:
        if not self.ends:
            raise subprocess.TimeoutExpired("mercury", timeout or 0)
        return 0


def test_mercury_on_windows_is_asked_then_ended_and_its_keying_line_lowered(monkeypatch: pytest.MonkeyPatch) -> None:
    ended: list[int] = []
    monkeypatch.setattr(mercuryhelper, "_end_tree", lambda process: ended.append(process.pid))
    monkeypatch.setattr(mercuryhelper.nodevices, "on", lambda: False)
    program = Program(lambda code, lines: None)
    program.keying = "rts:COM10"
    k = Kernel()
    program._end_windows(Process(ends=True), k)  # type: ignore[arg-type]
    assert ended == [] and "GenerateConsoleCtrlEvent" in k.names() and ("EscapeCommFunction", 11, 4) in k.calls
    k = Kernel()
    program._end_windows(Process(ends=False), k)  # type: ignore[arg-type]
    assert ended == [77] and ("EscapeCommFunction", 11, 4) in k.calls, "asked, not gone: the hard end, then the line"
    k = Kernel(AttachConsole=0)
    program._end_windows(Process(ends=True), k)  # type: ignore[arg-type]
    assert ended == [77, 77], "no console to ask through: the hard end at once"


def test_under_the_no_devices_switch_the_keying_line_is_not_opened(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mercuryhelper, "_end_tree", lambda process: None)
    monkeypatch.setattr(mercuryhelper.nodevices, "on", lambda: True)
    program = Program(lambda code, lines: None)
    program.keying = "rts:COM10"
    k = Kernel()
    program._end_windows(Process(ends=True), k)  # type: ignore[arg-type]
    assert "CreateFileW" not in k.names()
