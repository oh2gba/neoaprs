"""A pseudo-terminal pair standing in for a radio's serial port, for the few tests that are about a real device file (POSIX only: they are marked `skipif(sys.platform == "win32")`; everything that only needs a radio
to talk to uses the fake radio of tests/support/fakeradio.py). The test holds the master (the radio's side), the code under test opens the slave path with pyserial as it would open /dev/brainbox_N.
This module imports on Windows; making a pair there raises.

`make_pty()` gives the master descriptor and the slave path; `feed` is the radio talking, `heard` is what the port wrote. The helper keeps one slave descriptor open, in raw mode, for the life of the pair, so
that the pair does not hang up when the code under test closes its end. Closing the pair (`close_pty`) is the radio's cable being pulled.
A port that opens the slave resets its input buffer, so feed after the open.

The fixture `ptys` (registered by tests/conftest.py) makes pairs for a test and closes them when it ends; `held_by_a_program(path)` is another process that has a port open, as rotctld has its own."""
import os
import select
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import pytest

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="needs a pseudo-terminal, a device file, a POSIX shell, file modes or a signal sent to a process: POSIX only")      # for a test, or `pytestmark = posix_only` for a file

Ptys = Callable[[], tuple[int, str]]         # the fixture `ptys`: each call is a new pair, (master, slave path)

_slaves: dict[int, int] = {}                 # master descriptor -> the slave descriptor this helper holds


def _on_windows() -> bool:
    return sys.platform == "win32"


def make_pty() -> tuple[int, str]:
    if _on_windows():
        raise RuntimeError("pseudo-terminals exist on POSIX systems only")
    import tty                                           # (Windows has none)
    master, slave = os.openpty()  # type: ignore[attr-defined, unused-ignore]
    tty.setraw(slave)  # type: ignore[attr-defined, unused-ignore]
    _slaves[master] = slave
    return master, os.ttyname(slave)  # type: ignore[attr-defined, unused-ignore]


def feed(master_fd: int, data: bytes) -> None:
    """The radio sends `data` to the port."""
    view = memoryview(data)
    while view:
        view = view[os.write(master_fd, view):]


def heard(master_fd: int, count: int = 1, timeout_sec: float = 2.0) -> bytes:
    """What the port has written, waiting until at least `count` bytes came or the time is up."""
    out = bytearray()
    deadline = time.monotonic() + timeout_sec
    while len(out) < count and time.monotonic() < deadline:
        if select.select([master_fd], [], [], max(0.0, deadline - time.monotonic()))[0]:
            out += os.read(master_fd, 4096)
    return bytes(out)


def close_pty(master_fd: int) -> None:
    """Closes both ends. Before the test is over this is the radio's cable being pulled: the code under test finds its next read failing. Closing a pair again does nothing."""
    slave = _slaves.pop(master_fd, None)
    if slave is None:
        return
    for fd in (master_fd, slave):
        try:
            os.close(fd)
        except OSError:
            pass


@pytest.fixture
def ptys() -> Iterator[Callable[[], tuple[int, str]]]:
    """Makes pairs for the test and closes every one of them when it ends."""
    made: list[int] = []

    def make() -> tuple[int, str]:
        master, path = make_pty()
        made.append(master)
        return master, path

    yield make
    for master in made:
        close_pty(master)


_HOLD = "import os, sys, time\nos.open(sys.argv[1], os.O_RDWR | os.O_NOCTTY)\nprint('ready', flush=True)\ntime.sleep(60)\n"


@contextmanager
def held_by_a_program(path: str) -> Iterator[subprocess.Popen[str]]:
    """Another process that has `path` open, as rotctld has its port: no lock, just open."""
    child = subprocess.Popen([sys.executable, "-c", _HOLD, path], stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout is not None and child.stdout.readline().strip() == "ready"
        yield child
    finally:
        child.kill()
        child.wait()
        if child.stdout is not None:
            child.stdout.close()
