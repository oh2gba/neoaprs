"""One open of a port at a time in this process, and which ports it holds open.

Windows refuses a second open of a COM port with "access denied" even from the same program, so an
open of ours that raced another of ours (a radio's retry, a search, Find my radio, an open given up
on that still runs) would read as another program's.
"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

# the longest an open waits for another open of the same port (a Bluetooth COM port takes seconds)
OPEN_WAIT_SEC = 30.0

_lock = threading.Lock()
_gates: dict[str, threading.Lock] = {}
# the ports held open, by the id of their pyserial object
_held: dict[int, str] = {}


def key(path: str) -> str:
    """Return the port as one name: COM ports by their upper-case name without the `\\\\.\\` prefix."""
    name = path.strip()
    if name.upper().startswith(("COM", "\\\\.\\")):
        return name.upper().removeprefix("\\\\.\\")
    return name


@contextmanager
def turn(path: str, wait_sec: float | None = None) -> Iterator[bool]:
    """Hold the port's gate while an open runs; give False if another open kept it past the wait."""
    with _lock:
        gate = _gates.setdefault(key(path), threading.Lock())
    got = gate.acquire(timeout=OPEN_WAIT_SEC if wait_sec is None else wait_sec)
    try:
        yield got
    finally:
        if got:
            gate.release()


def hold(ser: Any, path: str) -> None:
    with _lock:
        _held[id(ser)] = key(path)


def release(ser: Any) -> None:
    with _lock:
        _held.pop(id(ser), None)


def held(path: str) -> bool:
    """Return whether this process holds the port open."""
    with _lock:
        return key(path) in _held.values()
