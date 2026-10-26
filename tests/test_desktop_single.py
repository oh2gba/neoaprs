"""One app to a data folder: the second one finds the lock taken, says `show` (or `quit`) to the first one on the loopback and ends; what is said before the first one has a window is kept until it has."""
import ctypes
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from tests.support.ptyline import posix_only

from neoaprs.desktop import single
from neoaprs.desktop.single import LOCK_NAME, PORT_NAME, SingleApp, process_alive


def wait(event: threading.Event) -> bool:
    return event.wait(10)


def test_the_first_app_takes_the_folder_and_the_second_is_refused(tmp_path: Path) -> None:
    first, second = SingleApp(tmp_path), SingleApp(tmp_path)
    assert not first.running() and first.acquire() and first.running()
    assert (tmp_path / LOCK_NAME).is_file() and int((tmp_path / PORT_NAME).read_text(encoding="ascii")) > 0
    assert not second.acquire()
    first.close()
    assert not first.running() and not (tmp_path / PORT_NAME).exists()
    assert second.acquire(), "the lock is let go with the first app"
    second.close()


def test_the_second_app_brings_up_the_window_of_the_first(tmp_path: Path) -> None:
    first = SingleApp(tmp_path)
    assert first.acquire()
    heard: list[str] = []
    shown = threading.Event()
    first.handle(lambda command: (heard.append(command), shown.set()))
    assert SingleApp(tmp_path).tell_the_other("show")
    assert wait(shown) and heard == ["show"]
    first.close()


def test_what_is_said_before_there_is_a_window_waits_for_one(tmp_path: Path) -> None:
    first = SingleApp(tmp_path)
    assert first.acquire()
    assert SingleApp(tmp_path).tell_the_other("show")
    heard: list[str] = []
    got = threading.Event()
    first.handle(lambda command: (heard.append(command), got.set()))
    assert wait(got) and heard == ["show"], "said before the handler was there, heard once it was (or at once: both orders end the same)"
    first.close()


def test_only_show_and_quit_are_understood(tmp_path: Path) -> None:
    first = SingleApp(tmp_path)
    assert first.acquire()
    heard: list[str] = []
    got = threading.Event()
    first.handle(lambda command: (heard.append(command), got.set()))
    port = int((tmp_path / PORT_NAME).read_text(encoding="ascii"))
    for junk in (b"", b"format c:\n", b"SHOW EVERYTHING\n", b"\x00\xff" * 4):
        with socket.create_connection(("127.0.0.1", port), timeout=5) as link:
            link.sendall(junk)
    assert SingleApp(tmp_path).tell_the_other("quit")
    assert wait(got) and heard == ["quit"]
    first.close()


def test_a_stale_port_file_is_a_failure_to_say_so_and_not_a_hang(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(single, "FIND_SEC", 0.3)
    (tmp_path / PORT_NAME).write_text("9\n", encoding="ascii")           # (nothing listens on the port 9 of the loopback)
    assert not SingleApp(tmp_path).tell_the_other("show")
    (tmp_path / PORT_NAME).write_text("not a port\n", encoding="ascii")
    assert not SingleApp(tmp_path).tell_the_other("show")


def test_the_app_writes_its_process_id_beside_the_port_and_a_second_app_reads_it(tmp_path: Path) -> None:
    app = SingleApp(tmp_path)
    assert app.pid() is None
    assert app.acquire()
    try:
        assert app.pid() == os.getpid() and SingleApp(tmp_path).pid() == os.getpid()
    finally:
        app.close()


def test_a_process_that_has_ended_is_not_alive_and_this_one_is() -> None:
    assert process_alive(os.getpid())
    assert not process_alive(_ended_pid())


def _ended_pid() -> int:
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


# ---- the edges: a lock that cannot be looked at, a handler that fails, a client that says nothing, and the process check of each system

def test_a_lock_that_cannot_be_looked_at_is_no_app_running(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / LOCK_NAME).write_text("")

    class Unreadable:
        def __init__(self, data: Path, name: str) -> None:
            pass

        def acquire(self) -> None:
            raise OSError("the folder cannot be read")

    monkeypatch.setattr(single, "InstanceLock", Unreadable)
    assert not SingleApp(tmp_path).running()


def test_what_was_said_before_the_handler_is_given_to_it_in_order_when_it_comes(tmp_path: Path) -> None:
    app = SingleApp(tmp_path)
    app._deliver("show")
    app._deliver("quit")
    heard: list[str] = []
    app.handle(heard.append)
    assert heard == ["show", "quit"]
    app._deliver("show")
    assert heard == ["show", "quit", "show"], "(and straight to it afterwards)"


@pytest.mark.expects_errors
def test_a_handler_that_fails_is_logged_and_the_next_command_still_comes_to_it(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    app = SingleApp(tmp_path)
    heard: list[str] = []

    def handler(command: str) -> None:
        heard.append(command)
        if command == "show":
            raise RuntimeError("no window to show")

    app.handle(handler)
    app._deliver("show")
    app._deliver("quit")
    assert heard == ["show", "quit"] and "show: the app could not do what the second one asked" in caplog.text


def test_a_client_that_says_nothing_does_not_hold_up_the_next_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(single, "HEAR_SEC", 0.1)
    first = SingleApp(tmp_path)
    assert first.acquire()
    heard: list[str] = []
    got = threading.Event()
    first.handle(lambda command: (heard.append(command), got.set()))
    port = int((tmp_path / PORT_NAME).read_text(encoding="ascii"))
    with socket.create_connection(("127.0.0.1", port), timeout=5):          # (connected, and silent until the app gives up on it)
        assert SingleApp(tmp_path).tell_the_other("quit")
        assert wait(got) and heard == ["quit"]
    first.close()


@posix_only                                                                      # (Windows: see the commit "five new tests are POSIX only for now")
def test_a_process_that_may_not_be_signalled_is_alive_all_the_same(monkeypatch: pytest.MonkeyPatch) -> None:
    def refused(pid: int, sig: int) -> None:
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(single.os, "kill", refused)
    assert process_alive(1)


class FakeOs:
    """`os` as the module sees it on Windows: the name is `nt`, the rest is this system's."""

    name = "nt"

    def __getattr__(self, name: str) -> object:
        return getattr(os, name)


class FakeKernel32:
    """The three calls of the Windows API that the check makes, for the processes that are running."""

    def __init__(self, running: set[int]) -> None:
        self.running = running
        self.opened: list[tuple[int, bool, int]] = []
        self.closed: list[int] = []

    def OpenProcess(self, access: int, inherit: bool, pid: int) -> int:
        self.opened.append((access, inherit, pid))
        return pid + 1000 if pid in self.running or pid == 777 else 0

    def WaitForSingleObject(self, handle: int, wait_ms: int) -> int:
        return 0x102 if handle - 1000 in self.running else 0                  # WAIT_TIMEOUT: still running; 0: it ended

    def CloseHandle(self, handle: int) -> None:
        self.closed.append(handle)


@pytest.fixture
def windows(monkeypatch: pytest.MonkeyPatch) -> FakeKernel32:
    kernel = FakeKernel32(running={4242})
    monkeypatch.setattr(single, "os", FakeOs())
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(kernel32=kernel), raising=False)
    return kernel


def test_on_windows_a_process_is_asked_for_by_its_handle_and_alive_while_the_wait_on_it_times_out(windows: FakeKernel32) -> None:
    assert process_alive(4242)
    assert windows.opened == [(0x00100000 | 0x1000, False, 4242)] and windows.closed == [5242], "(synchronize and query: the handle is let go)"


def test_on_windows_a_process_that_has_ended_is_not_alive_and_one_that_cannot_be_opened_is_not_either(windows: FakeKernel32) -> None:
    assert not process_alive(777)
    assert windows.closed == [1777]
    windows.closed.clear()
    assert not process_alive(31337)
    assert windows.closed == [], "(no handle, nothing to close)"
