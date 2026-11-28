"""Who listens on a port (neoaprs/tcplisten.py): iphlpapi's table read against a fake on any system,
/proc's table on Linux, and a real listener of this process found with its owner on Linux and Windows.
"""

import ctypes
import os
import socket
import struct
import sys
from typing import Any

import pytest

from neoaprs import mercuryhelper, tcplisten
from neoaprs.tcplisten import AF_INET, AF_INET6, ERROR_INSUFFICIENT_BUFFER, NO_ERROR, Listener


def port_dword(port: int) -> int:
    """A port as the table's DWORD holds it: network order in the low two bytes."""
    return int.from_bytes(struct.pack(">H", port), "little")


def table_v4(*rows: tuple[str, int, int]) -> bytes:
    body = b"".join(
        tcplisten.ROW_V4.pack(2, socket.inet_aton(address), port_dword(port), 0, 0, pid) for address, port, pid in rows
    )
    return struct.pack("<I", len(rows)) + body


def table_v6(*rows: tuple[str, int, int]) -> bytes:
    body = b"".join(
        tcplisten.ROW_V6.pack(socket.inet_pton(socket.AF_INET6, address), 0, port_dword(port), bytes(16), 0, 0, 2, pid)
        for address, port, pid in rows
    )
    return struct.pack("<I", len(rows)) + body


class Iphlpapi:
    """GetExtendedTcpTable as Windows answers it: too small a buffer is told the size it needs."""

    def __init__(self, tables: dict[int, bytes], fails: int = 0) -> None:
        self.tables, self.fails, self.calls = tables, fails, 0

    def GetExtendedTcpTable(self, buffer: Any, size: Any, order: bool, family: int, kind: int, reserved: int) -> int:
        self.calls += 1
        assert kind == tcplisten.TCP_TABLE_OWNER_PID_LISTENER and not order and reserved == 0
        if self.fails:
            return self.fails
        table = self.tables.get(family, struct.pack("<I", 0))
        wanted = size._obj if hasattr(size, "_obj") else size
        if wanted.value < len(table):
            wanted.value = len(table)
            return ERROR_INSUFFICIENT_BUFFER
        ctypes.memmove(buffer, table, len(table))
        wanted.value = len(table)
        return NO_ERROR


def test_the_windows_tables_are_read_with_the_port_in_network_order_and_the_owner_of_each_row() -> None:
    api = Iphlpapi(
        {
            AF_INET: table_v4(("0.0.0.0", 8100, 4321), ("127.0.0.1", 8300, 4321), ("192.168.1.5", 445, 4)),
            AF_INET6: table_v6(("::", 8100, 4321), ("::1", 10100, 99)),
        }
    )
    assert tcplisten.windows_listeners(api) == [
        Listener(8100, "0.0.0.0", 4321),
        Listener(8300, "127.0.0.1", 4321),
        Listener(445, "192.168.1.5", 4),
        Listener(8100, "::", 4321),
        Listener(10100, "::1", 99),
    ]
    assert api.calls == 4, "each family asked twice: once for the size, once for the rows"


def test_a_table_that_cannot_be_read_is_empty_and_a_short_one_is_read_as_far_as_it_goes() -> None:
    assert tcplisten.windows_listeners(Iphlpapi({}, fails=87)) == []
    whole = table_v4(("0.0.0.0", 8100, 1), ("0.0.0.0", 8300, 1))
    assert tcplisten.parse_table(whole[:-3], AF_INET) == [Listener(8100, "0.0.0.0", 1)]
    assert tcplisten.parse_table(b"", AF_INET6) == []


def test_a_program_started_through_a_launcher_owns_what_its_children_listen_on() -> None:
    parents = {10: 1, 11: 10, 12: 11, 13: 1, 0: 0}
    assert tcplisten.family_of(10, parents) == {10, 11, 12}
    assert tcplisten.family_of(13, parents) == {13}
    found = [Listener(8100, "127.0.0.1", 12), Listener(8300, "0.0.0.0", 13)]
    if sys.platform == "win32":
        assert tcplisten.not_ours([8100, 8300], 10, lambda ports, pid: found, lambda: parents) == [found[1]]
    assert tcplisten.not_ours([8100, 8300], None, lambda ports, pid: found) == found, "no program: all are another's"


PROC = """  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 0100007F:1FA4 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 5001 1 0
   1: 00000000:206C 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 5002 1 0
   2: 0100007F:1FA4 0100007F:9C40 01 00000000:00000000 00:00000000 00000000  1000        0 5003 1 0
"""
PROC6 = """  sl  local_address                         remote_address                        st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 00000000000000000000000001000000:2774 00000000000000000000000000000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 6001 1 0
"""


def test_the_kernels_table_gives_the_listeners_and_the_owner_of_the_sockets_asked_about() -> None:
    assert tcplisten.proc_listeners([PROC, PROC6], {"5001": 77}) == [
        Listener(8100, "127.0.0.1", 77),
        Listener(8300, "0.0.0.0", None),
        Listener(10100, "::1", None),
    ], "a connection is no listener; a socket of another process has no owner here"


def test_a_system_without_a_table_has_no_listeners() -> None:
    assert tcplisten.listeners([8100], system="darwin") == []


@pytest.fixture
def listening() -> Any:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        yield sock.getsockname()[1]


@pytest.mark.skipif(sys.platform == "darwin", reason="macOS has no table of listeners to read")
def test_a_listener_of_this_process_is_found_as_its_own_and_as_another_programs_for_any_other(
    listening: int,
) -> None:
    found = tcplisten.listeners([listening], os.getpid())
    assert found == [Listener(listening, "127.0.0.1", os.getpid())]
    assert tcplisten.not_ours([listening], os.getpid()) == []
    stranger = next(pid for pid in range(os.getpid() + 1, os.getpid() + 1000) if pid not in (os.getppid(),))
    assert [f.port for f in tcplisten.not_ours([listening], stranger)] == [listening]


@pytest.mark.skipif(sys.platform == "darwin", reason="macOS has no table of listeners to read")
def test_a_pair_with_a_listener_on_every_address_is_not_free_and_on_mercurys_own_pair_it_is_another_mercury(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The station's case: another Mercury on 0.0.0.0:8100; a bind on 127.0.0.1 beside it could succeed on Windows."""
    with socket.socket() as other:
        other.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        other.bind(("0.0.0.0", 0))
        other.listen()
        port = other.getsockname()[1]
        assert not mercuryhelper.pair_free(port)
        with pytest.raises(OSError, match="no free pair"):
            mercuryhelper.free_ports(port, 1)
        monkeypatch.setattr(mercuryhelper, "OWN_PAIR", port)
        with pytest.raises(mercuryhelper.PortsTaken):
            mercuryhelper.free_ports(port, 1)
        with pytest.raises(OSError, match="no free pair"):
            mercuryhelper.free_ports(port, 1, mercury=False)


def test_on_windows_a_listener_whose_lineage_cannot_be_read_is_not_taken_for_another_program(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed snapshot must not end our own run, started through a launcher, again and again."""
    found = [Listener(8100, "127.0.0.1", 12), Listener(8300, "127.0.0.1", 12)]
    stranger = [Listener(8100, "0.0.0.0", 13)]
    monkeypatch.setattr(sys, "platform", "win32")
    assert tcplisten.not_ours([8100, 8300], 10, lambda ports, pid: found, lambda: {}) == []
    assert tcplisten.not_ours([8100, 8300], 10, lambda ports, pid: found, lambda: {13: 1, 10: 1}) == []
    assert tcplisten.not_ours([8100], 10, lambda ports, pid: stranger, lambda: {13: 1, 10: 1, 12: 10}) == stranger
