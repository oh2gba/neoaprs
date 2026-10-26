"""The cap on the web server's connections (neoaprs/web/connections.py) with streams of made-up addresses: so many from one address, so many in all, the place that is made for whoever has the fewest, a
connection that has proved a token that is never the one that goes, and the book of addresses that does not grow for ever. The loopback is every visitor at once: a proxy on this computer has no cap of its own."""
import asyncio
import socket
from collections.abc import Iterator

import pytest
import tornado.web
from tornado.iostream import IOStream

from neoaprs.web import connections
from neoaprs.web.connections import MAX_PER_ADDRESS, LimitedHTTPServer
from tests.support.env import remember_stop, until


@pytest.fixture
def server() -> Iterator[LimitedHTTPServer]:
    yield LimitedHTTPServer(tornado.web.Application())


class Peers:
    """Streams of made-up addresses: each is one end of a socket pair that nobody writes to (the other end is kept so that the stream stays open)."""

    def __init__(self, server: LimitedHTTPServer) -> None:
        self.server = server
        self.ends: list[socket.socket] = []

    def come(self, ip: str) -> IOStream:
        a, b = socket.socketpair()
        self.ends += [a, b]
        stream = IOStream(a)
        self.server.handle_stream(stream, (ip, 50000 + len(self.ends)))
        return stream

    async def shutdown(self) -> None:
        for streams in list(self.server._streams.values()):
            for s in streams:
                s.close()
        await self.server.close_all_connections()
        for end in self.ends:
            end.close()
        await until(lambda: not [t for t in asyncio.all_tasks() if "_server_request_loop" in repr(t.get_coro())])


@pytest.fixture
def peers(server: LimitedHTTPServer) -> Peers:
    p = Peers(server)
    remember_stop(p.shutdown)                      # (stopped before the test's leak guard looks)
    return p


async def test_one_address_holds_at_most_so_many_connections_and_the_loopback_is_not_held_to_it(server: LimitedHTTPServer, peers: Peers, caplog: pytest.LogCaptureFixture) -> None:
    held = [peers.come("10.0.0.7") for _ in range(MAX_PER_ADDRESS)]
    assert not any(s.closed() for s in held)
    refused = peers.come("10.0.0.7")
    assert refused.closed() and server.open_connections() == MAX_PER_ADDRESS
    assert any("too many connections: one from 10.0.0.7 was refused" in r.getMessage() for r in caplog.records)
    assert not peers.come("10.0.0.8").closed(), "another address is not held up by it"
    loopback = [peers.come("127.0.0.1") for _ in range(MAX_PER_ADDRESS + 5)]
    assert not any(s.closed() for s in loopback)


async def test_when_all_the_places_are_taken_whoever_has_the_fewest_takes_the_place_of_the_oldest_of_the_address_that_has_the_most(
        server: LimitedHTTPServer, peers: Peers, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(connections, "MAX_CONNECTIONS", 5)
    greedy = [peers.come("10.0.0.1") for _ in range(3)]
    modest = [peers.come("10.0.0.2") for _ in range(2)]
    newcomer = peers.come("10.0.0.3")
    assert greedy[0].closed() and not newcomer.closed(), "the oldest of the address that held the most went"
    assert not any(s.closed() for s in greedy[1:] + modest)
    assert server.open_connections() == 5
    again = peers.come("10.0.0.1")
    assert again.closed(), "and now the address that holds two is not given a third by pushing out another's"


async def test_an_address_that_holds_as_many_as_the_newcomer_will_is_the_one_that_is_refused(server: LimitedHTTPServer, peers: Peers, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(connections, "MAX_CONNECTIONS", 4)
    first = [peers.come("10.0.0.1") for _ in range(2)]
    second = [peers.come("10.0.0.2") for _ in range(2)]
    refused = peers.come("10.0.0.1")
    assert refused.closed() and not any(s.closed() for s in first + second), "an address with as many as it has would hold afterwards cannot push another out"


async def test_a_connection_that_has_proved_a_token_is_never_closed_to_make_room(server: LimitedHTTPServer, peers: Peers, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(connections, "MAX_CONNECTIONS", 4)
    greedy = [peers.come("10.0.0.1") for _ in range(3)]
    other = peers.come("10.0.0.2")
    for stream in greedy:
        server.proved(stream)
    newcomer = peers.come("10.0.0.3")
    assert newcomer.closed() and not any(s.closed() for s in greedy + [other]), "every connection of the biggest address is a page that was let in: nobody goes"
    greedy[0].close()
    server.proved(other)                                              # (a proof also forgets the proved sockets that are closed)
    assert server._proved == {greedy[1], greedy[2], other}


async def test_the_book_of_addresses_forgets_the_ones_whose_connections_are_gone(server: LimitedHTTPServer, peers: Peers) -> None:
    gone = peers.come("10.9.9.9")
    for n in range(1001):
        server._streams[f"10.1.{n // 256}.{n % 256}"] = [gone]
    gone.close()
    assert len(server._streams) > 1000
    peers.come("10.0.0.1")
    assert set(server._streams) == {"10.0.0.1"}


async def test_stopping_to_listen_keeps_the_connections_and_listening_can_begin_again(server: LimitedHTTPServer, peers: Peers) -> None:
    server.listen(0, "127.0.0.1")
    held = peers.come("10.0.0.1")
    server.stop_listening()
    assert not server._sockets and not held.closed()
    server.listen(0, "127.0.0.1")
    assert server._sockets
    server.stop_listening()
