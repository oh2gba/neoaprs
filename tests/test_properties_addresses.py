"""Properties of the readers of addresses, ports and keys: the system's table of listening sockets, a
map archive's header, a `bt://` port, a gpsd's host:port, a path alias and the keys of a settings save.
A table, a header, a port, an address and an alias written read back as they were.
Any bytes or text, real ones damaged above all, give the value or the documented ValueError, never another.
A port is 0 to 65535 (1 to 65535 for gpsd), a channel 1 to 30, a box finite, a table no longer than its bytes.
"""

import ipaddress
import math
import socket
import struct
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from neoaprs import btserial, route, tcplisten
from neoaprs.configlayers import MASK, MASKED_KEYS
from neoaprs.gpsfeed import split_address
from neoaprs.pmtilesarchive import read_header
from neoaprs.pmtilesformat import HEADER_LENGTH
from neoaprs.tcplisten import AF_INET, AF_INET6, Listener
from neoaprs.web.confighandlers import split_values
from tests.support.madepmtiles import header, planet
from tests.support.mutation import mutated_bytes, mutated_text

PORTS = st.integers(0, 65535)
PIDS = st.integers(0, 2**32 - 1)
V4 = st.ip_addresses(v=4).map(str)
V6 = st.ip_addresses(v=6).map(str)


def _dword(port: int) -> int:
    return int.from_bytes(struct.pack(">H", port), "little")


def _table(family: int, rows: list[tuple[str, int, int]]) -> bytes:
    if family == AF_INET:
        body = [tcplisten.ROW_V4.pack(2, socket.inet_aton(a), _dword(p), 0, 0, pid) for a, p, pid in rows]
    else:
        body = [
            tcplisten.ROW_V6.pack(socket.inet_pton(socket.AF_INET6, a), 0, _dword(p), bytes(16), 0, 0, 2, pid)
            for a, p, pid in rows
        ]
    return struct.pack("<I", len(rows)) + b"".join(body)


REAL_V4 = _table(AF_INET, [("127.0.0.1", 8100, 4321), ("0.0.0.0", 8001, 1)])
REAL_V6 = _table(AF_INET6, [("::1", 8100, 4321), ("::", 8002, 0)])


@given(st.lists(st.tuples(V4, PORTS, PIDS), max_size=5), st.lists(st.tuples(V6, PORTS, PIDS), max_size=5))
def test_a_table_of_listeners_reads_back(v4: list[tuple[str, int, int]], v6: list[tuple[str, int, int]]) -> None:
    """parse_table of a table of rows gives each row's port, address and owner."""
    assert tcplisten.parse_table(_table(AF_INET, v4), AF_INET) == [Listener(p, a, pid) for a, p, pid in v4]
    read = [
        (r.port, ipaddress.ip_address(r.address), r.pid) for r in tcplisten.parse_table(_table(AF_INET6, v6), AF_INET6)
    ]
    assert read == [
        (p, ipaddress.ip_address(a), pid) for a, p, pid in v6
    ]  # Windows writes ::ffff:0:0 for ::ffff:0.0.0.0


@given(
    st.sampled_from([AF_INET, AF_INET6]),
    st.one_of(st.binary(max_size=120), mutated_bytes(REAL_V4), mutated_bytes(REAL_V6)),
)
def test_any_table_gives_listeners_on_a_port_and_an_address_no_more_than_its_rows(family: int, data: bytes) -> None:
    """Any bytes give listeners on ports 0 to 65535 at addresses of the family, no more than the bytes hold."""
    size = (tcplisten.ROW_V4 if family == AF_INET else tcplisten.ROW_V6).size
    found = tcplisten.parse_table(data, family)
    assert len(found) <= max(0, len(data) - 4) // size
    for listener in found:
        assert 0 <= listener.port <= 65535 and listener.pid is not None and 0 <= listener.pid < 2**32
        assert ipaddress.ip_address(listener.address).version == (4 if family == AF_INET else 6)


_E7 = st.integers(-(2**31), 2**31 - 1)


@pytest.fixture(scope="module")
def folder(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("headers")


@given(st.integers(0, 255), st.integers(0, 255), st.tuples(_E7, _E7, _E7, _E7))
def test_the_zooms_and_the_box_of_a_header_read_back(
    folder: Path, low: int, high: int, bounds: tuple[int, int, int, int]
) -> None:
    """read_header of a written header gives its zooms and its box in degrees."""
    (folder / "made").write_bytes(header(min_zoom=low, max_zoom=high, bounds=bounds))  # type: ignore[arg-type]
    found = read_header(folder / "made")
    assert found is not None and (found.min_zoom, found.max_zoom) == (low, high)
    assert found.bbox == tuple(v / 1e7 for v in bounds)


@given(st.one_of(st.binary(max_size=HEADER_LENGTH + 8), mutated_bytes(planet()[: HEADER_LENGTH + 16])))
def test_any_file_is_a_header_with_a_finite_box_or_none(folder: Path, data: bytes) -> None:
    """Any bytes give None or zooms of a byte and a box within 215 degrees."""
    (folder / "any").write_bytes(data)
    found = read_header(folder / "any")
    if found is not None:
        assert 0 <= found.min_zoom <= 255 and 0 <= found.max_zoom <= 255
        assert all(math.isfinite(v) and abs(v) < 215 for v in found.bbox)


_HEX = st.text(alphabet="0123456789abcdefABCDEF", min_size=2, max_size=2)
_MAC = st.tuples(st.lists(_HEX, min_size=6, max_size=6), st.sampled_from([":", "-"])).map(lambda p: p[1].join(p[0]))


@given(_MAC, st.one_of(st.none(), st.integers(1, 30)), st.booleans())
def test_a_bluetooth_port_reads_back(address: str, channel: int | None, slash: bool) -> None:
    """parse_url of bt://address[/channel] gives the address with colons in capitals and the channel."""
    url = f"bt://{address}" + (f"/{channel}" if channel is not None else "") + ("/" if slash else "")
    assert btserial.parse_url(url) == (address.replace("-", ":").upper(), channel)


@given(
    st.one_of(
        st.text(max_size=40),
        st.sampled_from(["bt://00:11:22:33:44:55/2", "bt://AA-BB-CC-DD-EE-FF"]).flatmap(mutated_text),
    )
)
def test_any_bluetooth_port_is_an_address_and_a_channel_or_a_value_error(path: str) -> None:
    """Any text gives six bytes of address and a channel of 1 to 30 (or none), or a ValueError."""
    try:
        address, channel = btserial.parse_url(path)
    except ValueError:
        return
    assert len(bytes.fromhex(address.replace(":", ""))) == 6
    assert channel is None or 1 <= channel <= 30


_HOST = st.one_of(
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789.-", min_size=1, max_size=30),
    V4,
    V6.map(lambda a: f"[{a}]"),
)


@given(_HOST, st.integers(1, 65535))
def test_a_gpsd_address_reads_back(host: str, port: int) -> None:
    """split_address of host:port is the host, an IPv6 address without its brackets, and the port."""
    assert split_address(f"{host}:{port}") == (host.strip("[]"), port)


@given(
    st.one_of(
        st.text(max_size=40),
        st.sampled_from(["localhost:2947", "[::1]:2947", "192.168.1.5:2947"]).flatmap(mutated_text),
    )
)
def test_any_gpsd_address_is_a_host_and_a_port_or_a_value_error(target: str) -> None:
    """Any text gives a host and a port of 1 to 65535, or a ValueError."""
    try:
        host, port = split_address(target)
    except ValueError:
        return
    assert host and 1 <= port <= 65535


@given(st.sampled_from(route._WORD_ALIAS.split("|")), st.one_of(st.none(), st.integers(0, 9)), st.integers(0, 99))
def test_an_alias_reads_back(prefix: str, n: int | None, left: int) -> None:
    """parse_alias of WIDEn-N, starred or not, is its prefix and numbers; without n it has no left either."""
    text = prefix if n is None else f"{prefix}{n}-{left}"
    expected = route.Alias(prefix, n, None if n is None else left)
    assert route.parse_alias(text) == expected == route.parse_alias(f"{text}*")


@given(
    st.one_of(
        st.text(max_size=12),
        st.sampled_from(["WIDE2-1", "WIDE1-1*", "SS3-3", "RELAY", "OH2RDG-1"]).flatmap(mutated_text),
    )
)
def test_any_path_element_is_an_alias_with_small_numbers_or_none(address: str) -> None:
    """Any text gives None or an alias whose numbers are 0 to 9 and 0 to 99 and whose hops are not negative."""
    alias = route.parse_alias(address)
    if alias is not None:
        assert alias.prefix and (alias.n is None or 0 <= alias.n <= 9)
        assert (alias.left is None or 0 <= alias.left <= 99) and alias.hops >= 0


_KEYS = st.one_of(
    st.text(max_size=20),
    st.sampled_from(["station/call", "radio/2/sound_card", "pair/1/2/ssid", "pair/2/1/ssid", *MASKED_KEYS]).flatmap(
        mutated_text
    ),
    st.integers(1, 6000).map(lambda n: f"radio/{'9' * n}/x"),
    st.integers(1, 6000).map(lambda n: f"pair/1/{'9' * n}/enabled"),
)


@given(st.dictionaries(_KEYS, st.one_of(st.text(max_size=8), st.just(MASK)), max_size=6))
def test_a_save_is_split_into_its_keys_without_the_mask_sent_back(values: dict[str, str]) -> None:
    """Any keys are split into station, radio and pair keys, each once with its value; a masked key's mask is not."""
    flat, own, pairs = split_values(values)
    kept = {k: v for k, v in values.items() if not (k in MASKED_KEYS and v == MASK)}
    assert {**flat, **own, **pairs} == kept and len(flat) + len(own) + len(pairs) == len(kept)


def test_a_radio_or_pair_number_of_thousands_of_digits_is_a_station_key() -> None:
    """A radio number too long for int() stays with the station settings, which refuse it, not a ValueError."""
    radio, pair = f"radio/{'1' * 5000}/x", f"pair/1/{'2' * 5000}/ssid"
    assert split_values({radio: "a", pair: "b"}) == ({radio: "a", pair: "b"}, {}, {})
