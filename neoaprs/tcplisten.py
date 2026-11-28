"""Who listens on a TCP port of this computer: the kernel's table on Linux, iphlpapi's on Windows.

`not_ours` tells a modem program the daemon started from another program on the same ports. The
Windows calls take their library as an argument, so the logic is tested with a fake elsewhere.
"""

import ctypes
import os
import socket
import struct
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROC_TCP = ("/proc/net/tcp", "/proc/net/tcp6")
LISTEN_HEX = "0A"
# iphlpapi: GetExtendedTcpTable's table class, its "more room" answer, and the address families
TCP_TABLE_OWNER_PID_LISTENER = 3
NO_ERROR, ERROR_INSUFFICIENT_BUFFER = 0, 122
AF_INET, AF_INET6 = 2, 23
# MIB_TCPROW_OWNER_PID: state, address, port, remote address, remote port, pid (six DWORDs)
ROW_V4 = struct.Struct("<I4sIIII")
# MIB_TCP6ROW_OWNER_PID: address, scope, port, remote address, scope, port, state, pid
ROW_V6 = struct.Struct("<16sII16sIIII")
# kernel32: a snapshot of the processes, for the children of a program started through a launcher
TH32CS_SNAPPROCESS = 0x2
INVALID_HANDLE = ctypes.c_void_p(-1).value


@dataclass(frozen=True)
class Listener:
    port: int
    address: str  # "127.0.0.1", "0.0.0.0", "::"
    pid: int | None  # the owner; None where the system does not say (Linux: a process not asked about)


def _port_of(value: int) -> int:
    """Return the port of a table's DWORD, which holds it in network order in its low two bytes."""
    return ((value & 0xFF) << 8) | ((value >> 8) & 0xFF)


def parse_table(buffer: bytes, family: int) -> list[Listener]:
    """Return the rows of a MIB_TCPTABLE_OWNER_PID (or its IPv6 form) as listeners."""
    if len(buffer) < 4:
        return []
    (count,) = struct.unpack_from("<I", buffer)
    row = ROW_V4 if family == AF_INET else ROW_V6
    found: list[Listener] = []
    for i in range(count):
        offset = 4 + i * row.size
        if offset + row.size > len(buffer):
            break
        if family == AF_INET:
            _, address, port, _, _, pid = ROW_V4.unpack_from(buffer, offset)
            found.append(Listener(_port_of(port), socket.inet_ntop(socket.AF_INET, address), pid))
        else:
            address6, _, port, _, _, _, _, pid = ROW_V6.unpack_from(buffer, offset)
            found.append(Listener(_port_of(port), socket.inet_ntop(socket.AF_INET6, address6), pid))
    return found


def windows_table(family: int, api: Any) -> bytes:
    """Return GetExtendedTcpTable's listeners of the family as raw bytes; empty when the call fails."""
    size = ctypes.c_ulong(0)
    for _ in range(4):  # the table may grow between the two calls
        buffer = ctypes.create_string_buffer(max(size.value, 4))
        size.value = len(buffer)
        answer = api.GetExtendedTcpTable(buffer, ctypes.byref(size), False, family, TCP_TABLE_OWNER_PID_LISTENER, 0)
        if answer == NO_ERROR:
            return buffer.raw[: size.value]
        if answer != ERROR_INSUFFICIENT_BUFFER:
            return b""
    return b""


def iphlpapi() -> Any:
    """Return iphlpapi; raise OSError where there is none."""
    if not hasattr(ctypes, "WinDLL"):
        raise OSError("iphlpapi is Windows only")
    return ctypes.WinDLL("iphlpapi")


def windows_listeners(api: Any = None) -> list[Listener]:
    api = api if api is not None else iphlpapi()
    return [listener for family in (AF_INET, AF_INET6) for listener in parse_table(windows_table(family, api), family)]


class ProcessEntry(ctypes.Structure):
    """PROCESSENTRY32W."""

    _fields_ = [
        ("size", ctypes.c_uint32),
        ("usage", ctypes.c_uint32),
        ("pid", ctypes.c_uint32),
        ("heap", ctypes.c_size_t),
        ("module", ctypes.c_uint32),
        ("threads", ctypes.c_uint32),
        ("parent", ctypes.c_uint32),
        ("priority", ctypes.c_long),
        ("flags", ctypes.c_uint32),
        ("exe", ctypes.c_wchar * 260),
    ]


def windows_parents(k: Any = None) -> dict[int, int]:
    """Return each process's parent, from a snapshot; empty when none can be made."""
    if k is None:
        k = ctypes.WinDLL("kernel32")  # type: ignore[attr-defined, unused-ignore]
        k.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
        k.Process32FirstW.argtypes = k.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        k.CloseHandle.argtypes = [ctypes.c_void_p]
    snapshot = k.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snapshot or snapshot == INVALID_HANDLE:
        return {}
    parents: dict[int, int] = {}
    try:
        entry = ProcessEntry()
        entry.size = ctypes.sizeof(ProcessEntry)
        more = k.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            parents[int(entry.pid)] = int(entry.parent)
            more = k.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        k.CloseHandle(snapshot)
    return parents


def family_of(pid: int, parents: Mapping[int, int]) -> set[int]:
    """Return the process and its descendants (a launcher's child holds the program's sockets)."""
    children: dict[int, list[int]] = {}
    for child, parent in parents.items():
        if child != parent:
            children.setdefault(parent, []).append(child)
    found, todo = {pid}, [pid]
    while todo:
        for child in children.get(todo.pop(), []):
            if child not in found:
                found.add(child)
                todo.append(child)
    return found


# ---- Linux


def _hex_address(text: str) -> str:
    raw = bytes.fromhex(text)
    if len(raw) == 4:
        return socket.inet_ntop(socket.AF_INET, raw[::-1])
    return socket.inet_ntop(socket.AF_INET6, b"".join(raw[i : i + 4][::-1] for i in range(0, 16, 4)))


def proc_listeners(tables: Iterable[str], inodes: Mapping[str, int]) -> list[Listener]:
    """Return the LISTEN rows of /proc/net/tcp texts; `inodes` gives the owner of a socket inode."""
    found: list[Listener] = []
    for text in tables:
        for line in text.splitlines()[1:]:
            fields = line.split()
            if len(fields) < 10 or fields[3] != LISTEN_HEX:
                continue
            address, _, port = fields[1].rpartition(":")
            found.append(Listener(int(port, 16), _hex_address(address), inodes.get(fields[9])))
    return found


def _proc_tables() -> list[str]:
    tables: list[str] = []
    for name in PROC_TCP:
        try:
            tables.append(Path(name).read_text(encoding="ascii"))
        except OSError:
            continue
    return tables


def _proc_family(pid: int) -> set[int]:
    """Return the process and its descendants as /proc's `children` lists them."""
    found, todo = {pid}, [pid]
    while todo:
        current = todo.pop()
        try:
            listed = Path(f"/proc/{current}/task/{current}/children").read_text(encoding="ascii").split()
        except OSError:
            continue
        for child in (int(p) for p in listed if p.isdigit()):
            if child not in found:
                found.add(child)
                todo.append(child)
    return found


def _socket_inodes(pids: Iterable[int], owner: int) -> dict[str, int]:
    """Return the socket inodes the processes hold, each as `owner`'s."""
    held: dict[str, int] = {}
    for pid in pids:
        try:
            fds = list(Path(f"/proc/{pid}/fd").iterdir())
        except OSError:
            continue
        for fd in fds:
            try:
                target = os.readlink(fd)
            except OSError:
                continue
            if target.startswith("socket:["):
                held[target[8:-1]] = owner
    return held


# ---- the questions


def listeners(ports: Iterable[int], ours: int | None = None, system: str | None = None) -> list[Listener]:
    """Return the listeners on `ports`; on Linux the owner is known for `ours` and its children only.

    Empty where the system has no table to read (macOS).
    """
    wanted = set(ports)
    on = system or sys.platform
    if on == "win32":
        found = windows_listeners()
    elif on.startswith("linux"):
        found = proc_listeners(_proc_tables(), _socket_inodes(_proc_family(ours), ours) if ours is not None else {})
    else:
        found = []
    return [listener for listener in found if listener.port in wanted]


def not_ours(
    ports: Iterable[int],
    pid: int | None,
    found: Callable[[Iterable[int], int | None], list[Listener]] = listeners,
    parents: Callable[[], Mapping[int, int]] | None = None,
) -> list[Listener]:
    """Return the listeners on `ports` that are not the process `pid` or one of its children.

    Without a pid every listener is another's.
    """
    seen = found(ports, pid)
    if pid is None:
        return seen
    if sys.platform == "win32" and any(listener.pid not in (pid, None) for listener in seen):
        family = family_of(pid, (parents or windows_parents)())
    else:
        family = {pid}
    return [listener for listener in seen if listener.pid not in family]
