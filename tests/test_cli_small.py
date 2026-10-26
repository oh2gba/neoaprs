"""The small pieces of the command line (neoaprs/__main__.py, neoaprs/cli/output.py, neoaprs/cli/uncaught.py) where they branch: the module that is imported and the one that is run, Ctrl+Break on the systems that have
it, the message for a person on stderr, and the hook for what nothing caught when the program does not chain to Python's own."""
import logging
import runpy
import signal
import sys
import threading
from types import SimpleNamespace

import pytest

from neoaprs.cli import output, uncaught


def test_importing_the_main_module_runs_nothing_and_running_it_ends_with_the_exit_code_of_the_command(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[bool] = []
    monkeypatch.setattr("neoaprs.cli.main", lambda: called.append(True) or 7)
    sys.modules.pop("neoaprs.__main__", None)
    __import__("neoaprs.__main__")
    assert called == []
    sys.modules.pop("neoaprs.__main__", None)
    with pytest.raises(SystemExit) as stop:
        runpy.run_module("neoaprs", run_name="__main__")
    assert stop.value.code == 7 and called == [True]


def test_where_the_system_has_ctrl_break_it_ends_the_program_like_ctrl_c_and_where_it_has_not_nothing_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    set_for: list[tuple[int, object]] = []
    monkeypatch.setattr(signal, "signal", lambda number, handler: set_for.append((number, handler)))
    monkeypatch.delattr(signal, "SIGBREAK", raising=False)
    output.ctrl_break_is_ctrl_c()
    assert set_for == []
    monkeypatch.setattr(signal, "SIGBREAK", 21, raising=False)
    output.ctrl_break_is_ctrl_c()
    assert set_for == [(21, signal.default_int_handler)]


def test_a_message_for_a_person_goes_to_stderr_and_leaves_stdout_to_the_scripts(capsys: pytest.CaptureFixture[str]) -> None:
    output.say("neoaprs: the port is taken")
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == "neoaprs: the port is taken\n"


@pytest.mark.expects_errors
def test_an_exception_that_ends_the_program_is_only_logged_when_python_is_not_to_print_it_too(caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    printed: list[type] = []
    monkeypatch.setattr(sys, "excepthook", lambda kind, error, trace: printed.append(kind))
    restore = uncaught.install(logging.getLogger("neoaprs.test"))
    try:
        sys.excepthook(RuntimeError, RuntimeError("x"), None)
    finally:
        restore()
    assert [r.levelno for r in caplog.records if r.name == "neoaprs.test"] == [logging.CRITICAL] and printed == []


@pytest.mark.expects_errors
def test_a_thread_that_ends_with_an_exit_or_with_nothing_to_say_is_not_logged_and_a_chained_one_is_printed_too(caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    printed: list[BaseException | None] = []
    monkeypatch.setattr(threading, "excepthook", lambda args: printed.append(args.exc_value))
    restore = uncaught.install(logging.getLogger("neoaprs.test"), chain=True)
    try:
        thread = threading.Thread(name="neoaprs-test-thread")
        for kind, error in ((SystemExit, SystemExit(0)), (None, None), (ValueError, ValueError("a thread went wrong"))):
            threading.excepthook(SimpleNamespace(exc_type=kind, exc_value=error, exc_traceback=None, thread=thread))   # type: ignore[arg-type]
        threading.excepthook(SimpleNamespace(exc_type=KeyError, exc_value=KeyError("k"), exc_traceback=None, thread=None))   # type: ignore[arg-type]
    finally:
        restore()
    records = [r for r in caplog.records if r.name == "neoaprs.test"]
    assert [r.getMessage() for r in records] == ["uncaught exception in the thread neoaprs-test-thread", "uncaught exception in the thread ?"]
    assert [type(e) for e in printed] == [ValueError, KeyError]
