"""Classic Bluetooth on Windows through its own libraries: the paired devices by name, and the RFCOMM
channels of a device's serial port (the Winsock lookup of its service directory).

Each call takes the library as an argument, so that the logic is tested with a fake elsewhere.
"""

import ctypes
import logging
import socket
import sys
from collections.abc import Callable
from typing import Any, NamedTuple

log = logging.getLogger("neoaprs.btserial")

_BOOL, _DWORD, _HANDLE, _WORD = ctypes.c_int32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint16
ERROR_NO_MORE_ITEMS = 259
NS_BTH = 16
LUP_RETURN_ADDR, LUP_FLUSHCACHE = 0x0100, 0x1000
WSA_E_NO_MORE, WSASERVICE_NOT_FOUND = 10110, 10108
WSA_TIMED_OUT = 10060  # the device did not answer
LOOKUP_BYTES = 4096
NAME_CHARS = 248


class SystemTime(ctypes.Structure):
    _fields_ = [(name, _WORD) for name in ("year", "month", "weekday", "day", "hour", "minute", "second", "ms")]


class DeviceInfo(ctypes.Structure):
    """BLUETOOTH_DEVICE_INFO; the name is UTF-16 code units, so that the size is Windows' on every system."""

    _fields_ = [
        ("size", _DWORD),
        ("address", ctypes.c_uint64),
        ("device_class", _DWORD),
        ("connected", _BOOL),
        ("remembered", _BOOL),
        ("authenticated", _BOOL),
        ("last_seen", SystemTime),
        ("last_used", SystemTime),
        ("name", _WORD * NAME_CHARS),
    ]


class SearchParams(ctypes.Structure):
    """BLUETOOTH_DEVICE_SEARCH_PARAMS."""

    _fields_ = [
        ("size", _DWORD),
        ("return_authenticated", _BOOL),
        ("return_remembered", _BOOL),
        ("return_unknown", _BOOL),
        ("return_connected", _BOOL),
        ("issue_inquiry", _BOOL),
        ("timeout_multiplier", ctypes.c_ubyte),
        ("radio", _HANDLE),
    ]


class Guid(ctypes.Structure):
    _fields_ = [("data1", _DWORD), ("data2", _WORD), ("data3", _WORD), ("data4", ctypes.c_ubyte * 8)]


class SockaddrBth(ctypes.Structure):
    """SOCKADDR_BTH, packed as Windows packs it."""

    _pack_ = 1
    _fields_ = [("family", ctypes.c_uint16), ("address", ctypes.c_uint64), ("service", Guid), ("port", ctypes.c_uint32)]


class SocketAddress(ctypes.Structure):
    _fields_ = [("sockaddr", ctypes.c_void_p), ("length", ctypes.c_int32)]


class CsAddrInfo(ctypes.Structure):
    _fields_ = [
        ("local", SocketAddress),
        ("remote", SocketAddress),
        ("socket_type", ctypes.c_int32),
        ("protocol", ctypes.c_int32),
    ]


class QuerySet(ctypes.Structure):
    """WSAQUERYSETW; the strings are pointers to UTF-16 text."""

    _fields_ = [
        ("size", _DWORD),
        ("instance_name", ctypes.c_void_p),
        ("service_class", ctypes.POINTER(Guid)),
        ("version", ctypes.c_void_p),
        ("comment", ctypes.c_void_p),
        ("name_space", _DWORD),
        ("provider", ctypes.POINTER(Guid)),
        ("context", ctypes.c_void_p),
        ("protocols", _DWORD),
        ("protocol_list", ctypes.c_void_p),
        ("query", ctypes.c_void_p),
        ("addresses", _DWORD),
        ("address_list", ctypes.POINTER(CsAddrInfo)),
        ("output_flags", _DWORD),
        ("blob", ctypes.c_void_p),
    ]


SERIAL_PORT = Guid(0x00001101, 0x0000, 0x1000, (ctypes.c_ubyte * 8)(0x80, 0x00, 0x00, 0x80, 0x5F, 0x9B, 0x34, 0xFB))

# the calls made here: argument types and result type
BTHPROPS_CALLS: dict[str, tuple[list[Any], Any]] = {
    "BluetoothFindFirstDevice": ([ctypes.POINTER(SearchParams), ctypes.POINTER(DeviceInfo)], _HANDLE),
    "BluetoothFindNextDevice": ([_HANDLE, ctypes.POINTER(DeviceInfo)], _BOOL),
    "BluetoothFindDeviceClose": ([_HANDLE], _BOOL),
}
WS2_CALLS: dict[str, tuple[list[Any], Any]] = {
    "WSALookupServiceBeginW": ([ctypes.POINTER(QuerySet), _DWORD, ctypes.POINTER(_HANDLE)], ctypes.c_int32),
    "WSALookupServiceNextW": ([_HANDLE, _DWORD, ctypes.POINTER(_DWORD), ctypes.c_void_p], ctypes.c_int32),
    "WSALookupServiceEnd": ([_HANDLE], ctypes.c_int32),
}


class Device(NamedTuple):
    address: str  # AA:BB:CC:DD:EE:FF
    name: str


def _on_windows() -> bool:
    return sys.platform == "win32"


def _library(name: str, calls: dict[str, tuple[list[Any], Any]]) -> Any:
    """Return the library with the argument types of `calls`; raise OSError where there is none."""
    if not _on_windows() or not hasattr(ctypes, "WinDLL"):
        raise OSError(f"{name} is Windows only")
    library = ctypes.WinDLL(name, use_last_error=True)
    for function, (argtypes, restype) in calls.items():
        call = getattr(library, function)
        call.argtypes, call.restype = argtypes, restype
    return library


def bthprops() -> Any:
    return _library("bthprops.cpl", BTHPROPS_CALLS)


def ws2_32() -> Any:
    return _library("ws2_32", WS2_CALLS)


def last_error() -> int:
    get = getattr(ctypes, "get_last_error", None)
    return int(get()) if get is not None else 0


def usable() -> bool:
    """Return whether this Windows Python can make RFCOMM sockets and list the paired devices."""
    if not (hasattr(socket, "AF_BLUETOOTH") and hasattr(socket, "BTPROTO_RFCOMM")):
        return False
    try:
        bthprops()
    except (OSError, AttributeError) as e:
        log.debug("no Bluetooth library: %s", e)
        return False
    return True


def address_text(value: int) -> str:
    return ":".join(f"{(value >> shift) & 0xFF:02X}" for shift in range(40, -8, -8))


def name_of(info: DeviceInfo) -> str:
    units = list(info.name)
    end = units.index(0) if 0 in units else len(units)
    return bytes(info.name)[: 2 * end].decode("utf-16-le", "replace")


def paired_devices(api: Any, error: Callable[[], int] = last_error) -> list[Device]:
    """Return the devices paired with this computer, as the system remembers them; no device is asked."""
    params = SearchParams(size=ctypes.sizeof(SearchParams), return_authenticated=True, return_remembered=True)
    info = DeviceInfo(size=ctypes.sizeof(DeviceInfo))
    find = api.BluetoothFindFirstDevice(ctypes.byref(params), ctypes.byref(info))
    if not find:
        if (code := error()) != ERROR_NO_MORE_ITEMS:
            log.info("the paired Bluetooth devices could not be listed (Windows error %d)", code)
        return []
    found: list[Device] = []
    try:
        while True:
            if info.authenticated:
                found.append(Device(address_text(info.address), name_of(info)))
            info = DeviceInfo(size=ctypes.sizeof(DeviceInfo))
            if not api.BluetoothFindNextDevice(find, ctypes.byref(info)):
                break
    finally:
        api.BluetoothFindDeviceClose(find)
    return found


def _wide(text: str) -> ctypes.Array[ctypes.c_char]:
    return ctypes.create_string_buffer((text + "\0").encode("utf-16-le"))


def serial_channels(address: str, api: Any, error: Callable[[], int] = last_error) -> list[int]:
    """Return the RFCOMM channels of the device's serial port services; [] if the device gives none."""
    context = _wide(f"({address})")
    query = QuerySet(size=ctypes.sizeof(QuerySet), name_space=NS_BTH)
    query.service_class = ctypes.pointer(SERIAL_PORT)
    query.context = ctypes.cast(context, ctypes.c_void_p)
    flags = LUP_FLUSHCACHE | LUP_RETURN_ADDR
    handle = _HANDLE()
    if api.WSALookupServiceBeginW(ctypes.byref(query), flags, ctypes.byref(handle)) != 0:
        if (code := error()) == WSA_TIMED_OUT:
            raise TimeoutError(f"{address}: the device did not answer for its service directory (Windows error {code})")
        log.info("%s: the service directory was not read (Windows error %d)", address, code)
        return []
    found: list[int] = []
    try:
        while True:
            size = _DWORD(LOOKUP_BYTES)
            buffer = ctypes.create_string_buffer(LOOKUP_BYTES)
            if api.WSALookupServiceNextW(handle, flags, ctypes.byref(size), buffer) != 0:
                if (code := error()) not in (WSA_E_NO_MORE, WSASERVICE_NOT_FOUND):
                    log.info("%s: the service directory ended with Windows error %d", address, code)
                break
            found += _ports(ctypes.cast(buffer, ctypes.POINTER(QuerySet)).contents)
    finally:
        api.WSALookupServiceEnd(handle)
    return list(dict.fromkeys(c for c in found if 1 <= c <= 30))


def _ports(result: QuerySet) -> list[int]:
    out = []
    for i in range(result.addresses):
        remote = result.address_list[i].remote
        if remote.sockaddr and remote.length >= ctypes.sizeof(SockaddrBth):
            out.append(int(ctypes.cast(remote.sockaddr, ctypes.POINTER(SockaddrBth)).contents.port))
    return out
