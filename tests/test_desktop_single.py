"""One app to a data folder: the second one finds the lock taken, says `show` (or `quit`) to the first one on the loopback and ends; what is said before the first one has a window is kept until it has."""
import socket
import threading
import os
import subprocess
import sys
from pathlib import Path

import pytest

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
