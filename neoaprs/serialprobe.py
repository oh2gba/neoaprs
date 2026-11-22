"""Find which ports exist and which is the radio.

The system's port list (every OS), the search that listens to all ports matching a pattern at
once (Linux), and the ports Find my radio tries one after another (Linux, Windows, macOS).
"""

import asyncio
import glob
import logging
import os
import re
import sys
from collections.abc import Awaitable, Callable, Collection, Mapping
from dataclasses import dataclass
from typing import TypedDict, Unpack

import serial.tools.list_ports  # type: ignore[import-untyped]

from . import nodevices
from .btpaired import paired_devices
from .claims import PORT_KINDS, Claim
from .config import DEFAULT_SERIAL_PATTERN, Config
from .serialboards import board_kind, describe
from .serialholders import held_by, port_key
from .radiospec import RadioSpec, enabled, live
from .radiotype import RadioId, RadioTypeError
from .serialport import SerialError, SerialPort
from .tncprofile import names_tcp

log = logging.getLogger("neoaprs.serialport")

DEFAULT_PATTERN = DEFAULT_SERIAL_PATTERN
# if set, its globs are searched instead of serial/pattern (tests)
PATTERN_ENV = "NEOAPRS_SERIAL_PATTERN"
# latest bytes a listening port keeps for the validity test
HEARD_KEPT_BYTES = 16384
# listen this long before writing a CR
NUDGE_SEC = 10.0
# how often a listening search lists again
RELIST_SEC = 10.0
# said under the no-devices switch
NOT_LISTED = "the serial ports and the paired Bluetooth devices are not listed or searched"
# ports opened by searches and Find my radio, by port_key; a closed one may linger
LISTENING: dict[str, SerialPort] = {}


@dataclass(frozen=True)
class PortInfo:
    """A serial port the system lists: name, description and, for USB, vendor and product ids."""

    device: str
    description: str
    hwid: str
    vid: int | None
    pid: int | None


def available_ports() -> list[PortInfo]:
    """Return the ports the system lists (pyserial), in natural order; nothing is opened."""
    if nodevices.refused(NOT_LISTED, logging.INFO):
        return []
    try:
        found = sorted(serial.tools.list_ports.comports())
    except OSError as e:
        log.info("listing the ports failed: %s", e)
        return []
    return [PortInfo(p.device, p.description or "", p.hwid or "", p.vid, p.pid) for p in found]


@dataclass(frozen=True)
class AdapterId:
    """Which USB adapter a port is: vendor and product ids and serial number ("" if none)."""

    vid: int
    pid: int
    serial: str


def _adapter_of(port: PortInfo) -> AdapterId | None:
    found = re.search(r"\bSER=(\S+)", port.hwid)
    return (
        None if port.vid is None or port.pid is None else AdapterId(port.vid, port.pid, found.group(1) if found else "")
    )


def identity_of(path: str) -> AdapterId | None:
    """Return the USB adapter behind `path` as listed now; None for socket, Bluetooth, old port."""
    key = port_key(path)
    return next((a for p in available_ports() if port_key(p.device) == key and (a := _adapter_of(p)) is not None), None)


def moved_to(adapter: AdapterId | None, gone: str) -> str | None:
    """Return where the adapter is now that `gone` is no longer listed (a renumbered COM port)."""
    ports = available_ports()
    if adapter is None or any(port_key(p.device) == port_key(gone) for p in ports):
        return None
    same = [p.device for p in ports if _adapter_of(p) == adapter]
    return same[0] if len(same) == 1 else None


def paired_bluetooth_ports() -> list[PortInfo]:
    """Return paired Bluetooth devices (Linux) as ports `bt://ADDRESS`; never opened here."""
    if nodevices.refused(NOT_LISTED, logging.INFO):
        return []
    return [
        PortInfo(f"bt://{d.address}", f"Bluetooth: {d.name}" if d.name else "Bluetooth device", "", None, None)
        for d in paired_devices()
    ]


# where other names of a port live: udev's stable names, and the user's own links
LINK_DIRS = ("/dev/serial/by-id", "/dev")


def with_links(ports: list[PortInfo], dirs: Collection[str] = LINK_DIRS) -> list[PortInfo]:
    """Return `ports` with, after each, the links in `dirs` that lead to its device."""
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
                said = (
                    f"{port.device}, {port.description}"
                    if port.description and port.description != "n/a"
                    else port.device
                )
                out.append(PortInfo(link, f"= {said}", port.hwid, port.vid, port.pid))
    return out


def claim_value(path: str) -> str | None:
    """Return the port's claim value (`port_key`); None for a TCP address or no port."""
    return None if not path.strip() or names_tcp(path) else port_key(path)


def holder_words(holder: RadioId | None) -> str:
    """Return who holds a resource for the log: "radio 3" or "the GPS receiver"."""
    return "the GPS receiver" if holder is None else f"radio {holder}"


def keying_device(text: str) -> str:
    """Return the serial device a keying line is on (`rts:/dev/ttyUSB0`), or ""."""
    way, _, device = text.strip().partition(":")
    return device if way in ("rts", "dtr") else ""


def device_claims(spec: RadioSpec) -> list[Claim]:
    """Return the claims for the serial devices the radio's settings name (port and keying line)."""
    try:
        fields = spec.rtype.fields
    except RadioTypeError:
        return []
    found = []
    for f in fields:
        if f.claims in PORT_KINDS:
            text = str(spec.settings.get(f.key, f.default))
            if (value := claim_value(keying_device(text) if f.claims == "keying" else text)) is not None:
                found.append(Claim(f.claims, value, spec.id))
    return found


def named_ports(station: Config, off_too: bool = False) -> tuple[Claim, ...]:
    """Return the serial devices named by every enabled radio (`off_too`: off ones too)."""
    return tuple(claim for spec in (live if off_too else enabled)(station.radios) for claim in device_claims(spec))


def can_search() -> bool:
    """Return whether the radio may be searched for among the ports automatically."""
    return sys.platform.startswith("linux")


def can_find() -> bool:
    """Return whether Find my radio may try the ports on the operator's click."""
    return sys.platform.startswith("linux") or sys.platform in ("win32", "darwin")


# devices under /dev/cu.* that are not serial adapters
MAC_LEFT_OUT = ("Bluetooth-Incoming-Port", "debug-console")
MAC_DEVICES = "/dev/cu.*"


def is_bluetooth_com(port: PortInfo) -> bool:
    """Return whether this is a Bluetooth serial port presented as a COM port."""
    return port.hwid.upper().startswith("BTHENUM") or "bluetooth" in port.description.lower()


def _usb_first(port: PortInfo) -> int:
    """Return the order Find my radio tries ports in: USB, other serial, then Bluetooth."""
    return 2 if is_bluetooth_com(port) else 0 if port.vid is not None or port.hwid.upper().startswith("USB") else 1


def system_ports() -> list[PortInfo]:
    """Return the ports Find my radio tries, USB first, without development boards."""
    if nodevices.refused(NOT_LISTED, logging.INFO):
        return []
    ports = available_ports()
    if sys.platform == "darwin":
        listed = {p.device for p in ports}
        ports += [
            PortInfo(path, "", "", None, None)
            for path in sorted(glob.glob(MAC_DEVICES))
            if path not in listed and not path.endswith(MAC_LEFT_OUT)
        ]
    ports = [p for p in ports if not (p.vid is not None and p.pid is not None and board_kind(p.vid, p.pid))]
    return sorted(ports, key=_usb_first)


def bluetooth_com_keys() -> set[str]:
    """Return the keys of the listed Bluetooth serial ports (none on Linux)."""
    return set() if can_search() else {port_key(p.device) for p in available_ports() if is_bluetooth_com(p)}


def search_pattern(stored: str = DEFAULT_PATTERN) -> str:
    """Return the globs to search: NEOAPRS_SERIAL_PATTERN if set, else `stored`."""
    return os.environ.get(PATTERN_ENV, "").strip() or stored


def candidate_ports(pattern: str = DEFAULT_PATTERN) -> list[str]:
    """Return the ports the globs of `pattern` match, sorted; a device appears once."""
    if nodevices.refused(NOT_LISTED, logging.INFO):
        return []
    found: dict[str, str] = {}
    for glob_pattern in pattern.split():
        for path in sorted(glob.glob(glob_pattern)):
            real = os.path.realpath(path)
            if real not in found and os.path.exists(real):
                found[real] = path
    return sorted(found.values())


def searchable_ports(pattern: str = DEFAULT_PATTERN) -> tuple[list[str], dict[str, str]]:
    """Return the ports the search may listen to, and {path: board} for those left out."""
    paths = candidate_ports(pattern)
    if not paths:
        return [], {}
    kinds = {
        port_key(p.device): describe(p.vid, p.pid)
        for p in available_ports()
        if p.vid is not None and p.pid is not None and board_kind(p.vid, p.pid)
    }
    boards = {path: kinds[port_key(path)] for path in paths if port_key(path) in kinds}
    return [p for p in paths if p not in boards], boards


class _Listener(SerialPort):
    """A port that keeps what it hears and wakes the probe when it has heard enough or died."""

    def __init__(self, path: str, baud: int, looks_valid: Callable[[bytes], bool], wake: asyncio.Event) -> None:
        super().__init__(path, baud)
        self.looks_valid = looks_valid
        self.heard = bytearray()
        self.valid = False
        self.opened_at = 0.0
        self.nudged = False
        self.wake = wake

    def _deliver(self, chunk: bytes) -> None:
        self.heard.extend(chunk)
        del self.heard[:-HEARD_KEPT_BYTES]
        if not self.valid and self.looks_valid(bytes(self.heard)):
            self.valid = True
            self.wake.set()

    def _lost(self, reason: str) -> None:
        super()._lost(reason)
        self.wake.set()

    def let_go(self) -> None:
        super().let_go()
        self.wake.set()


async def _open_one(port: _Listener, level: int) -> bool:
    if (held := LISTENING.get(key := port_key(port.path))) is None or not (held.is_open or held.is_opening):
        # before the open too: let_go reaches a port being opened
        LISTENING[key] = port
    try:
        await port.open()
    except SerialError as e:
        log.log(level, "probe: skipping %s", e)
        return False
    port.opened_at = asyncio.get_running_loop().time()
    LISTENING[key] = port
    return True


async def _open_all(
    paths: list[str],
    baud: int,
    looks_valid: Callable[[bytes], bool],
    wake: asyncio.Event,
    skip: Collection[str],
    level: int = logging.INFO,
    claimed: Mapping[str, str] | None = None,
) -> list[_Listener]:
    """Open side by side every port not skipped, claimed (`port_key` to reason) or held."""
    never = {port_key(p) for p in skip}
    ports: list[_Listener] = []
    for path in paths:
        if port_key(path) in never:
            log.log(level, "probe: skipping %s: on the skip list", path)
        elif other := (claimed or {}).get(port_key(path)):
            log.log(level, "probe: skipping %s: %s", path, other)
        elif held := await asyncio.to_thread(held_by, path):
            log.log(level, "probe: skipping %s: %s", path, held)
        else:
            ports.append(_Listener(path, baud, looks_valid, wake))
    try:
        opened = await asyncio.gather(*(_open_one(p, level) for p in ports))
    except BaseException:
        for port in ports:
            port.close()
        raise
    return [p for p, ok in zip(ports, opened) if ok]


async def _relist(
    ports: list[_Listener],
    listing: Callable[[], Awaitable[list[str]]],
    baud: int,
    looks_valid: Callable[[bytes], bool],
    wake: asyncio.Event,
    skip: Collection[str],
    on_open: Callable[[list[str]], None] | None,
    claimed: Mapping[str, str] | None = None,
) -> list[_Listener]:
    """Re-list the ports: keep open ones still listed, close those gone or claimed, try the rest."""
    paths = await listing()
    for port in (p for p in ports if p.path not in paths):
        port.close()
    kept = _still_mine(ports, claimed)
    opened = await _open_all(
        [path for path in paths if all(path != p.path for p in kept)],
        baud,
        looks_valid,
        wake,
        skip,
        logging.DEBUG,
        claimed,
    )
    if on_open is not None and (opened or len(kept) != len(ports)):
        on_open([p.path for p in kept + opened])
    return kept + opened


def _still_mine(
    ports: list[_Listener], claimed: Mapping[str, str] | None, on_open: Callable[[list[str]], None] | None = None
) -> list[_Listener]:
    """Return the open ports minus those another radio holds now; those are closed."""
    held = dict(claimed or {})
    for port in (p for p in ports if p.is_open and port_key(p.path) in held):
        port.close()
    left = [p for p in ports if p.is_open]
    if on_open is not None and len(left) != len(ports):
        on_open([p.path for p in left])
    return left


def _first_valid(ports: list[_Listener]) -> tuple[str, bytes] | None:
    """Return the first port whose bytes passed the validity test, with what it said."""
    return next(((p.path, bytes(p.heard)) for p in ports if p.valid), None)


def _nudge_due(
    ports: list[_Listener], nudge: bytes, after_sec: float, now: float, nudged: set[str] | None = None
) -> float | None:
    """Nudge ports open for `after_sec` and not yet nudged; return when the next is due, or None."""
    due = [p for p in ports if not p.nudged and now >= p.opened_at + after_sec]
    for port in due:
        port.nudged = True
        if nudged is not None:
            if (key := port_key(port.path)) in nudged:
                continue
            nudged.add(key)
        try:
            port.write(nudge)
        except SerialError as e:
            log.info("probe: dropping %s", e)
            port.close()
    left = [p.opened_at + after_sec for p in ports if p.is_open and not p.nudged]
    return min(left) if left else None


async def _sleep_until(wake: asyncio.Event, times: list[float], now: float) -> None:
    """Wait for `wake`, or until the earliest of `times` (loop time) if there are any."""
    try:
        await asyncio.wait_for(wake.wait(), min(times) - now if times else None)
    except TimeoutError:
        pass


class ProbeOptions(TypedDict, total=False):
    """The optional arguments of `probe_heard` that `probe` passes on."""

    nudge: bytes | None
    nudge_after_sec: float
    on_open: Callable[[list[str]], None] | None
    skip: Collection[str]
    relist: Callable[[], Awaitable[list[str]]] | None
    claimed: Mapping[str, str] | None


async def probe(
    paths: list[str],
    baud: int,
    seconds: float | None,
    looks_valid: Callable[[bytes], bool],
    **options: Unpack[ProbeOptions],
) -> str | None:
    """Listen to all openable paths at once; return the first whose bytes satisfy `looks_valid`.

    Every port it opened is closed again, cancellation included. None after `seconds` (0: no limit).
    """
    found = await probe_heard(paths, baud, seconds, looks_valid, **options)
    return None if found is None else found[0]


async def probe_heard(
    paths: list[str],
    baud: int,
    seconds: float | None,
    looks_valid: Callable[[bytes], bool],
    nudge: bytes | None = None,
    nudge_after_sec: float = NUDGE_SEC,
    on_open: Callable[[list[str]], None] | None = None,
    skip: Collection[str] = (),
    relist: Callable[[], Awaitable[list[str]]] | None = None,
    claimed: Mapping[str, str] | None = None,
    nudged: set[str] | None = None,
) -> tuple[str, bytes] | None:
    """Like `probe`, but return the port's path with what it was heard to say (the latest bytes)."""
    loop = asyncio.get_running_loop()
    wake = asyncio.Event()
    ports = await _open_all(paths, baud, looks_valid, wake, skip, claimed=claimed)
    try:
        if on_open is not None:
            on_open([p.path for p in ports])
        deadline = loop.time() + seconds if seconds else None
        relist_at = loop.time() + RELIST_SEC if relist is not None else None
        while True:
            ports = _still_mine(ports, claimed, on_open)
            if (found := _first_valid(ports)) is not None:
                return found
            now = loop.time()
            if not ports or (deadline is not None and now >= deadline):
                return None
            if relist is not None and relist_at is not None and now >= relist_at:
                relist_at = now + RELIST_SEC
                ports = await _relist(ports, relist, baud, looks_valid, wake, skip, on_open, claimed)
                continue
            nudge_at = _nudge_due(ports, nudge, nudge_after_sec, now, nudged) if nudge is not None else None
            wake.clear()
            await _sleep_until(wake, [t for t in (deadline, nudge_at, relist_at) if t is not None], now)
    finally:
        for port in ports:
            port.close()
