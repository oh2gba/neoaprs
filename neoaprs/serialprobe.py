"""Which ports there are and which of them is the radio: the list of the ports the system knows (every OS), and, on Linux, the search that listens to the ports that match a pattern all at once.

The search writes to the ports it listens to (a carriage return, to wake a TNC in command mode), and a port that is not a TNC may be a GPS, a rotator or an interface that keys a transmitter on a control line. It is
therefore made only where the ports are USB serial adapters under `/dev` (Linux); on Windows and macOS the radio is the port that was named or remembered, and the operator picks it from the list."""
import asyncio
import glob
import logging
import os
import sys
from collections.abc import Callable, Collection
from dataclasses import dataclass

import serial.tools.list_ports  # type: ignore[import-untyped]

from .config import DEFAULT_SERIAL_PATTERN
from .serialboards import board_kind, describe
from .serialholders import held_by, port_key
from .serialport import SerialError, SerialPort

log = logging.getLogger("neoaprs.serialport")

DEFAULT_PATTERN = DEFAULT_SERIAL_PATTERN       # what the search looks at when the settings say nothing else: the usual names of USB serial adapters
PATTERN_ENV = "NEOAPRS_SERIAL_PATTERN"         # the globs of this variable, when it is set and not empty, are searched instead of serial/pattern and the default (the tests: a pattern that matches nothing)
HEARD_KEPT_BYTES = 16384            # a listening port keeps this much of the latest bytes for the validity test, so a port that never stops talking noise costs no memory


@dataclass(frozen=True)
class PortInfo:
    """A serial port the system lists: the name to open it by, what the system calls it, and for a USB adapter the vendor and product ids."""
    device: str
    description: str
    hwid: str
    vid: int | None
    pid: int | None


def available_ports() -> list[PortInfo]:
    """The ports the system lists (pyserial: sysfs on Linux, SetupAPI on Windows, IOKit on macOS), in natural order (COM2 before COM10). Nothing is opened."""
    try:
        found = sorted(serial.tools.list_ports.comports())
    except OSError as e:
        log.info("listing the ports failed: %s", e)
        return []
    return [PortInfo(p.device, p.description or "", p.hwid or "", p.vid, p.pid) for p in found]


LINK_DIRS = ("/dev/serial/by-id", "/dev")         # where the other names of a port are: the stable names udev makes, and links of the user's own rules (such as /dev/brainbox_3)


def with_links(ports: list[PortInfo], dirs: Collection[str] = LINK_DIRS) -> list[PortInfo]:
    """`ports` with, after each, the other names it has: the links in `dirs` that lead to its device, each as a port of its own whose description says which device it is.
    Nothing is opened; a folder that is not there, or a link that leads nowhere, is passed over."""
    names: dict[str, list[str]] = {}
    for folder in dirs:
        try:
            entries = sorted(os.scandir(folder), key=lambda e: e.name)
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                names.setdefault(os.path.realpath(entry.path), []).append(entry.path)
    out: list[PortInfo] = []
    for port in ports:
        out.append(port)
        for link in names.get(os.path.realpath(port.device), []):
            if link != port.device:
                said = f"{port.device}, {port.description}" if port.description and port.description != "n/a" else port.device
                out.append(PortInfo(link, f"= {said}", port.hwid, port.vid, port.pid))
    return out


def can_search() -> bool:
    """Whether the radio may be looked for among the ports (see the top of this module)."""
    return sys.platform.startswith("linux")


def search_pattern(stored: str = DEFAULT_PATTERN) -> str:
    """The globs the search looks at: those of the environment variable NEOAPRS_SERIAL_PATTERN if there are any, else `stored` (serial/pattern)."""
    return os.environ.get(PATTERN_ENV, "").strip() or stored


def candidate_ports(pattern: str = DEFAULT_PATTERN) -> list[str]:
    """The ports the search may listen to: what the globs of `pattern` (separated by spaces) match. A device is listed once however many names it has (a link in /dev/serial/by-id and the
    ttyUSB node it points to): the name that the earliest glob matched stays, which is the stable one when the globs are in that order. A name that leads nowhere is left out. Sorted."""
    found: dict[str, str] = {}
    for glob_pattern in pattern.split():
        for path in sorted(glob.glob(glob_pattern)):
            real = os.path.realpath(path)
            if real not in found and os.path.exists(real):
                found[real] = path
    return sorted(found.values())


def searchable_ports(pattern: str = DEFAULT_PATTERN) -> tuple[list[str], dict[str, str]]:
    """The ports the search may listen to, and the ones it leaves out because a development board is behind them (serialboards.py): {path: "an ESP32 development board (USB 303a:1001)"}. The system is asked
    for the ports' USB ids only when the globs match anything. A port the system does not list, or lists without ids, stays."""
    paths = candidate_ports(pattern)
    if not paths:
        return [], {}
    kinds = {port_key(p.device): describe(p.vid, p.pid) for p in available_ports() if p.vid is not None and p.pid is not None and board_kind(p.vid, p.pid)}
    boards = {path: kinds[port_key(path)] for path in paths if port_key(path) in kinds}
    return [p for p in paths if p not in boards], boards


class _Listener(SerialPort):
    """A port that keeps what it hears and tells the probe that it has heard enough or that its line died, instead of telling signals to anyone."""

    def __init__(self, path: str, baud: int, looks_valid: Callable[[bytes], bool], wake: asyncio.Event) -> None:
        super().__init__(path, baud)
        self.looks_valid = looks_valid
        self.heard = bytearray()
        self.valid = False
        self._wake = wake

    def _deliver(self, chunk: bytes) -> None:
        self.heard.extend(chunk)
        del self.heard[:-HEARD_KEPT_BYTES]
        if not self.valid and self.looks_valid(bytes(self.heard)):
            self.valid = True
            self._wake.set()

    def _lost(self, reason: str) -> None:
        super()._lost(reason)
        self._wake.set()


async def _open_one(port: _Listener) -> bool:
    try:
        await port.open()
    except SerialError as e:
        log.info("probe: skipping %s", e)
        return False
    return True


async def _open_all(paths: list[str], baud: int, looks_valid: Callable[[bytes], bool], wake: asyncio.Event, skip: Collection[str]) -> list[_Listener]:
    """Every port that is not skipped, not held by another program and can be opened, opened side by side (one that is slow to answer holds up no other). Cancelled, it leaves none open."""
    never = {port_key(p) for p in skip}
    ports: list[_Listener] = []
    for path in paths:
        if port_key(path) in never:
            log.info("probe: skipping %s: on the skip list", path)
        elif held := held_by(path):
            log.info("probe: skipping %s: %s", path, held)
        else:
            ports.append(_Listener(path, baud, looks_valid, wake))
    try:
        opened = await asyncio.gather(*(_open_one(p) for p in ports))
    except BaseException:
        for port in ports:
            port.close()
        raise
    return [p for p, ok in zip(ports, opened) if ok]


def _nudge_all(ports: list[_Listener], nudge: bytes) -> None:
    for port in ports:
        try:
            port.write(nudge)
        except SerialError as e:
            log.info("probe: dropping %s", e)
            port.close()


async def _sleep_until(wake: asyncio.Event, times: list[float], now: float) -> None:
    """Waits for `wake`, or until the earliest of `times` (loop time) when there are any."""
    try:
        await asyncio.wait_for(wake.wait(), min(times) - now if times else None)
    except TimeoutError:
        pass


async def probe(paths: list[str], baud: int, seconds: float | None, looks_valid: Callable[[bytes], bool], nudge: bytes | None = None, nudge_after_sec: float = 10.0,
                on_open: Callable[[list[str]], None] | None = None, skip: Collection[str] = ()) -> str | None:
    """Opens every path it can and listens to all of them at once; the first one whose bytes satisfy `looks_valid` is the radio's. Every port it opened is closed again, whatever ends the search,
    cancellation included. A path that another process has open (`holders`), or that is in `skip` (compared by what it resolves to), is never touched: not opened, not written to. A path that cannot be opened is skipped; a port whose line dies, or that cannot be written to, is dropped; with no port left the answer is None at once.
    `seconds` is the whole wait (None or 0: no limit, until a port is valid or the caller cancels). `nudge` is written to every open port `nudge_after_sec` after the open, once: a TNC in command
    mode answers a bare CR, one in KISS mode ignores it. `on_open` is told which paths could be opened, before the wait begins."""
    loop = asyncio.get_running_loop()
    wake = asyncio.Event()
    ports = await _open_all(paths, baud, looks_valid, wake, skip)
    try:
        if on_open is not None:
            on_open([p.path for p in ports])
        deadline = loop.time() + seconds if seconds else None
        nudge_at = loop.time() + nudge_after_sec if nudge is not None else None
        while True:
            ports = [p for p in ports if p.is_open]
            for port in ports:
                if port.valid:
                    return port.path
            now = loop.time()
            if not ports or (deadline is not None and now >= deadline):
                return None
            if nudge is not None and nudge_at is not None and now >= nudge_at:
                nudge_at = None
                _nudge_all(ports, nudge)
                continue
            wake.clear()
            await _sleep_until(wake, [t for t in (deadline, nudge_at) if t is not None], now)
    finally:
        for port in ports:
            port.close()
