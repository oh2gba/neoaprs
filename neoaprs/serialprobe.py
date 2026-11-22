"""Which ports there are and which of them is the radio: the list of the ports the system knows (every OS), the search that listens to the ports that match a pattern all at once (Linux), and the ports that Find my
radio tries one after the other (Linux, Windows, macOS).

The search writes to the ports it listens to (a carriage return, to wake a TNC in command mode), and a port that is not a TNC may be a GPS, a rotator or an interface that keys a transmitter on a control line. The search
that runs by itself is therefore made only where the ports are USB serial adapters under `/dev` (Linux); on Windows and macOS the radio is the port that was named or remembered, and the operator picks it from the list, or
asks for Find my radio, which is made on a click and tries the ports of the system's list: on Windows the COM ports (a paired Bluetooth serial port is one of them), on macOS the `/dev/cu.*` devices."""
import asyncio
import glob
import logging
import os
import re
import sys
from collections.abc import Awaitable, Callable, Collection, Mapping
from dataclasses import dataclass

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

DEFAULT_PATTERN = DEFAULT_SERIAL_PATTERN       # what the search looks at when the settings say nothing else: the usual names of USB serial adapters
PATTERN_ENV = "NEOAPRS_SERIAL_PATTERN"         # the globs of this variable, when it is set and not empty, are searched instead of serial/pattern and the default (the tests: a pattern that matches nothing)
HEARD_KEPT_BYTES = 16384            # a listening port keeps this much of the latest bytes for the validity test, so a port that never stops talking noise costs no memory
NUDGE_SEC = 10.0                    # how long a port is listened to before a carriage return is written to it: a TNC in command mode answers it, one in KISS mode ignores it
RELIST_SEC = 10.0                   # how often a search that listens lists its ports again: one that appeared is opened, one that vanished is closed
NOT_LISTED = "the serial ports and the paired Bluetooth devices are not listed or searched"       # what the no-devices switch says of every list of this module: each is empty under it, as on a machine that has no port
LISTENING: dict[str, SerialPort] = {}              # the ports the searches of this process and Find my radio have open, by port_key (one closed may linger): tncsearch.let_go closes one a radio's settings name


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
    """Which USB adapter a port is: its vendor and product ids and its serial number, empty when it has none (then every adapter of the kind looks alike)."""
    vid: int
    pid: int
    serial: str


def _adapter_of(port: PortInfo) -> AdapterId | None:
    found = re.search(r"\bSER=(\S+)", port.hwid)
    return None if port.vid is None or port.pid is None else AdapterId(port.vid, port.pid, found.group(1) if found else "")


def identity_of(path: str) -> AdapterId | None:
    """The USB adapter behind the port `path`, as the system lists it now; None for a port that is none (a socket, a Bluetooth port, an old serial port)."""
    key = port_key(path)
    return next((a for p in available_ports() if port_key(p.device) == key and (a := _adapter_of(p)) is not None), None)


def moved_to(adapter: AdapterId | None, gone: str) -> str | None:
    """Where the adapter is when the system no longer lists `gone` (a COM port that came back as another number): the one port with its serial number, or, for an adapter with none, the only port with its vendor and product ids.
    None when `gone` is listed (something else keeps it), or no port or more than one qualifies: then it is the operator's to choose."""
    ports = available_ports()
    if adapter is None or any(port_key(p.device) == port_key(gone) for p in ports):
        return None
    same = [p.device for p in ports if _adapter_of(p) == adapter]
    return same[0] if len(same) == 1 else None


def paired_bluetooth_ports() -> list[PortInfo]:
    """The Bluetooth devices paired with the system (Linux), each as the port `bt://ADDRESS` that opens it. They are listed for the operator to pick from and are never opened by the search or to list them."""
    if nodevices.refused(NOT_LISTED, logging.INFO):
        return []
    return [PortInfo(f"bt://{d.address}", f"Bluetooth: {d.name}" if d.name else "Bluetooth device", "", None, None) for d in paired_devices()]


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


def claim_value(path: str) -> str | None:
    """The value a claim of this port holds in the station's table (claims.py): the device as `port_key` compares it (a link resolved, a COM port in upper case, a Bluetooth address in lower case), so that two names of
    one device are one claim; None for a KISS TCP address (a connection, not a device: two radios may each have one to one server) and for no port at all."""
    return None if not path.strip() or names_tcp(path) else port_key(path)


def holder_words(holder: RadioId | None) -> str:
    """Who holds a resource of the station, as the log says it without the station's table: "radio 3", or "the GPS receiver" for the station's own claim (with the table, `Claims.words` names the radio)."""
    return "the GPS receiver" if holder is None else f"radio {holder}"


def keying_device(text: str) -> str:
    """The serial device a keying line is on (`rts:/dev/ttyUSB0`, `dtr:COM4`); "" for a keying that is on no serial line (vox, cm108, none)."""
    way, _, device = text.strip().partition(":")
    return device if way in ("rts", "dtr") else ""


def device_claims(spec: RadioSpec) -> list[Claim]:
    """The serial devices the radio's settings name, whatever its type (its port, the port of its keying line), as its claims in the station's table; none for a field left empty, a KISS TCP address, and a
    radio of a type that is none."""
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
    """The serial devices the settings name for every enabled radio (`device_claims`): the station's table reads them as its `named` (claims.py), so that a device a radio is set to is left out by every other
    radio's search, by Find my radio for another radio and by the keying choice of another radio's modem, whether that radio has opened it yet or not. `off_too`: of the radios that are off as well (not the
    removed ones), for the keying choice, which a modem keeps while it runs: a radio switched on later is not to find its TNC's port keying another."""
    return tuple(claim for spec in (live if off_too else enabled)(station.radios) for claim in device_claims(spec))


def can_search() -> bool:
    """Whether the radio may be looked for among the ports by itself (see the top of this module)."""
    return sys.platform.startswith("linux")


def can_find() -> bool:
    """Whether Find my radio may try the ports, on the operator's click: where the search is made, and Windows and macOS."""
    return sys.platform.startswith("linux") or sys.platform in ("win32", "darwin")


MAC_LEFT_OUT = ("Bluetooth-Incoming-Port", "debug-console")          # devices under /dev/cu.* that are no serial adapter
MAC_DEVICES = "/dev/cu.*"


def is_bluetooth_com(port: PortInfo) -> bool:
    """A Bluetooth serial port that the system makes a COM port of (Windows: "Standard Serial over Bluetooth link (COM5)", hardware id BTHENUM\\...). It has no line speed, and opening one can take seconds."""
    return port.hwid.upper().startswith("BTHENUM") or "bluetooth" in port.description.lower()


def _usb_first(port: PortInfo) -> int:
    """The order Find my radio tries ports in: USB adapters, then other serial ports, then Bluetooth ones (which can take seconds to answer)."""
    return 2 if is_bluetooth_com(port) else 0 if port.vid is not None or port.hwid.upper().startswith("USB") else 1


def system_ports() -> list[PortInfo]:
    """The ports Find my radio tries where the system lists them (Windows and macOS): the system's list in natural order (COM2 before COM10), without the development boards that the search leaves alone (serialboards.py)
    and, on macOS, the `/dev/cu.*` devices pyserial did not list, without the ones that are no adapter. USB adapters come first, then the others, and the Bluetooth serial ports last. Nothing is opened."""
    if nodevices.refused(NOT_LISTED, logging.INFO):
        return []
    ports = available_ports()
    if sys.platform == "darwin":
        listed = {p.device for p in ports}
        ports += [PortInfo(path, "", "", None, None) for path in sorted(glob.glob(MAC_DEVICES)) if path not in listed and not path.endswith(MAC_LEFT_OUT)]
    ports = [p for p in ports if not (p.vid is not None and p.pid is not None and board_kind(p.vid, p.pid))]
    return sorted(ports, key=_usb_first)                          # (a stable sort: the natural order stays inside each group)


def bluetooth_com_keys() -> set[str]:
    """The ports of the system's list that are Bluetooth serial ports, by `port_key` (Windows and macOS; none on Linux, where the paired devices are `bt://` ports)."""
    return set() if can_search() else {port_key(p.device) for p in available_ports() if is_bluetooth_com(p)}


def search_pattern(stored: str = DEFAULT_PATTERN) -> str:
    """The globs the search looks at: those of the environment variable NEOAPRS_SERIAL_PATTERN if there are any, else `stored` (serial/pattern)."""
    return os.environ.get(PATTERN_ENV, "").strip() or stored


def candidate_ports(pattern: str = DEFAULT_PATTERN) -> list[str]:
    """The ports the search may listen to: what the globs of `pattern` (separated by spaces) match. A device is listed once however many names it has (a link in /dev/serial/by-id and the
    ttyUSB node it points to): the name that the earliest glob matched stays, which is the stable one when the globs are in that order. A name that leads nowhere is left out. Sorted."""
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
        self.opened_at = 0.0                                  # loop time of the open: the nudge comes a while after it
        self.nudged = False
        self.wake = wake                                      # (set when the probe is to look at its ports again)

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
        self.wake.set()                                       # (the probe looks at its ports again, without this one)


async def _open_one(port: _Listener, level: int) -> bool:
    if (held := LISTENING.get(key := port_key(port.path))) is None or not (held.is_open or held.is_opening):
        LISTENING[key] = port                                 # (before the open too: tncsearch.let_go reaches a port that is being opened)
    try:
        await port.open()
    except SerialError as e:
        log.log(level, "probe: skipping %s", e)
        return False
    port.opened_at = asyncio.get_running_loop().time()
    LISTENING[key] = port
    return True


async def _open_all(paths: list[str], baud: int, looks_valid: Callable[[bytes], bool], wake: asyncio.Event, skip: Collection[str], level: int = logging.INFO, claimed: Mapping[str, str] | None = None) -> list[_Listener]:
    """Every port that is not skipped, not held by another radio of the station (`claimed`: why, by the port's `port_key`), not held by another program and can be opened, opened side by side (one that is slow to answer
    holds up no other). Cancelled, it leaves none open. `level` is how loud a port that cannot be listened to is told: INFO when the ports are first listed, DEBUG when a listing repeats and says the same."""
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


async def _relist(ports: list[_Listener], listing: Callable[[], Awaitable[list[str]]], baud: int, looks_valid: Callable[[bytes], bool], wake: asyncio.Event, skip: Collection[str],
                  on_open: Callable[[list[str]], None] | None, claimed: Mapping[str, str] | None = None) -> list[_Listener]:
    """The ports as they are listed now: the open ones that are still listed stay, the ones no longer listed (the device went away) or held by another radio of the station meanwhile (`claimed`) are closed, and the
    others, new or not openable before, are tried (quietly: a port that is still held says nothing new). `on_open` is told the new set when it differs."""
    paths = await listing()
    for port in (p for p in ports if p.path not in paths):
        port.close()
    kept = _still_mine(ports, claimed)
    opened = await _open_all([path for path in paths if all(path != p.path for p in kept)], baud, looks_valid, wake, skip, logging.DEBUG, claimed)
    if on_open is not None and (opened or len(kept) != len(ports)):
        on_open([p.path for p in kept + opened])
    return kept + opened


def _still_mine(ports: list[_Listener], claimed: Mapping[str, str] | None, on_open: Callable[[list[str]], None] | None = None) -> list[_Listener]:
    """The ports that are open, without the ones another radio of the station holds or is set to now (`claimed`: a save named it a moment ago, before the next listing), which are closed and never the
    search's answer; `on_open` is told the set when it shrank (that, a port a radio took: tncsearch.let_go, or a line that died)."""
    held = dict(claimed or {})
    for port in (p for p in ports if p.is_open and port_key(p.path) in held):
        port.close()
    left = [p for p in ports if p.is_open]
    if on_open is not None and len(left) != len(ports):
        on_open([p.path for p in left])
    return left


def _first_valid(ports: list[_Listener]) -> tuple[str, bytes] | None:
    """The first port whose bytes satisfied the validity test, with what it said; None while there is none."""
    return next(((p.path, bytes(p.heard)) for p in ports if p.valid), None)


def _nudge_due(ports: list[_Listener], nudge: bytes, after_sec: float, now: float, nudged: set[str] | None = None) -> float | None:
    """Writes the nudge to the ports that have been open for `after_sec` and were not nudged yet (a port that cannot be written to is dropped); the loop time the next nudge is due at, None when none is.
    `nudged`: the ports (by `port_key`) the caller's search has nudged already, in an earlier turn of it: each is nudged once in the whole search, and the ones nudged now are added."""
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
    """Waits for `wake`, or until the earliest of `times` (loop time) when there are any."""
    try:
        await asyncio.wait_for(wake.wait(), min(times) - now if times else None)
    except TimeoutError:
        pass


async def probe(paths: list[str], baud: int, seconds: float | None, looks_valid: Callable[[bytes], bool], nudge: bytes | None = None, nudge_after_sec: float = NUDGE_SEC,
                on_open: Callable[[list[str]], None] | None = None, skip: Collection[str] = (), relist: Callable[[], Awaitable[list[str]]] | None = None, claimed: Mapping[str, str] | None = None) -> str | None:
    """Opens every path it can and listens to all of them at once; the first one whose bytes satisfy `looks_valid` is the radio's. Every port it opened is closed again, whatever ends the search,
    cancellation included. A path that another process has open (`holders`), that another radio of the station holds (`claimed`, by `port_key`, with the words of why), or that is in `skip` (compared by what it resolves to), is never touched: not opened, not written to. A path that cannot be opened is skipped; a port whose line dies, or that cannot be written to, is dropped; with no port left the answer is None at once.
    `seconds` is the whole wait (None or 0: no limit, until a port is valid or the caller cancels). `nudge` is written to every open port `nudge_after_sec` after the open, once: a TNC in command
    mode answers a bare CR, one in KISS mode ignores it. `on_open` is told which paths could be opened, before the wait begins and again whenever the set of open ports changes. `relist`, when given, is asked
    for the paths again every RELIST_SEC while the search listens: a port that appeared (a radio plugged back in) is opened and nudged in its turn, one that vanished is closed. The search lists again
    instead of ending after a time, because a search with no limit is what the Tnc asks for, and a search that ended and started over would only see the same ports and leave a port that appeared in the
    meantime, or the named port the search stands in for, unheard for as long as another port keeps talking."""
    found = await probe_heard(paths, baud, seconds, looks_valid, nudge, nudge_after_sec, on_open, skip, relist, claimed)
    return None if found is None else found[0]


async def probe_heard(paths: list[str], baud: int, seconds: float | None, looks_valid: Callable[[bytes], bool], nudge: bytes | None = None, nudge_after_sec: float = NUDGE_SEC,
                      on_open: Callable[[list[str]], None] | None = None, skip: Collection[str] = (), relist: Callable[[], Awaitable[list[str]]] | None = None, claimed: Mapping[str, str] | None = None,
                      nudged: set[str] | None = None) -> tuple[str, bytes] | None:
    """`probe`, with what the port it chose was heard to say (the latest HEARD_KEPT_BYTES of it), so that the caller can tell a TNC that types command-mode text from one that sends KISS frames. `nudged`: the
    ports the caller's search nudged in its earlier turns, which are not nudged again (`_nudge_due`)."""
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
