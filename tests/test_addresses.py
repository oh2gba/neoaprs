"""The address another device can open the page at (neoaprs/web/addresses.py), on a socket that is a stand-in: no route, a refused probe, the loopback, and an address. The probe sends nothing (a UDP connect)."""
import socket
from types import SimpleNamespace

import pytest

from neoaprs.web import addresses


class FakeSocket:
    def __init__(self, route: int = 0, address: str = "192.168.1.20", fail: type[BaseException] | None = None) -> None:
        self.route, self.address, self.fail = route, address, fail

    def __enter__(self) -> "FakeSocket":
        if self.fail is not None:
            raise self.fail("no sockets here")
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def connect_ex(self, address: tuple[str, int]) -> int:
        assert address == (addresses.PROBE, 9), "the probe is the documentation address, nothing real"
        return self.route

    def getsockname(self) -> tuple[str, int]:
        return self.address, 54321


def with_socket(monkeypatch: pytest.MonkeyPatch, fake: FakeSocket) -> None:
    monkeypatch.setattr(addresses, "socket", SimpleNamespace(AF_INET=socket.AF_INET, SOCK_DGRAM=socket.SOCK_DGRAM, socket=lambda *args: fake))


def test_the_address_the_system_would_send_from_is_the_one_to_give(monkeypatch: pytest.MonkeyPatch) -> None:
    with_socket(monkeypatch, FakeSocket(address="192.168.1.20"))
    assert addresses.lan_addresses() == ["192.168.1.20"]


def test_with_no_route_there_is_no_address(monkeypatch: pytest.MonkeyPatch) -> None:
    with_socket(monkeypatch, FakeSocket(route=101))                   # (network unreachable)
    assert addresses.lan_addresses() == []


@pytest.mark.parametrize("address", ["127.0.0.1", "0.0.0.0"])
def test_the_loopback_and_the_unspecified_address_are_never_given(monkeypatch: pytest.MonkeyPatch, address: str) -> None:
    with_socket(monkeypatch, FakeSocket(address=address))
    assert addresses.lan_addresses() == []


def test_a_system_that_cannot_make_the_socket_has_no_address_and_no_error(monkeypatch: pytest.MonkeyPatch) -> None:
    with_socket(monkeypatch, FakeSocket(fail=OSError))
    assert addresses.lan_addresses() == []


@pytest.mark.parametrize(("text", "expected"), [
    ("192.168.1.20", "192.168.1.20"), ("::1", "::1"), ("fe80::1%eth0", "fe80::1"), ("::ffff:127.0.0.1", "127.0.0.1"), ("::ffff:192.168.1.20%2", "192.168.1.20"),
    ("pi.local", None), ("localhost", None), ("", None), ("300.1.1.1", None), ("192.168.1.20:7303", None),
])
def test_an_address_is_read_with_its_zone_left_off_and_an_ipv4_address_in_its_ipv6_form_as_the_ipv4_one(text: str, expected: str | None) -> None:
    address = addresses.as_address(text)
    assert (None if address is None else str(address)) == expected


@pytest.mark.parametrize(("text", "loopback"), [("127.0.0.1", True), ("127.9.9.9", True), ("::1", True), ("::ffff:127.0.0.1", True), ("::1%lo", True), ("192.168.1.20", False), ("fe80::1", False), ("localhost", False), ("", False)])
def test_the_loopback_is_any_form_of_an_address_of_this_computer_itself(text: str, loopback: bool) -> None:
    assert addresses.is_loopback(text) is loopback


def test_a_probe_that_answers_with_a_loopback_or_an_unset_address_is_no_address_on_the_network(monkeypatch: pytest.MonkeyPatch) -> None:
    for answer in ("127.0.0.1", "127.8.0.3", "0.0.0.0"):
        with_socket(monkeypatch, FakeSocket(address=answer))
        assert addresses.lan_addresses() == []
