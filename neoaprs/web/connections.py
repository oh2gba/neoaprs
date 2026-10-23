"""The connections of the web server: a cap on the open ones, in all and from one address, that makes room for whoever has the fewest.

Tornado has no cap: a host that opens connections and says nothing holds a file descriptor for each until the header timeout, and the daemon needs descriptors for its database,
its radio and the log.
"""
import logging
from typing import Any

import tornado.httpserver
from tornado.iostream import IOStream

from .access import is_loopback

log = logging.getLogger("neoaprs.web")

MAX_CONNECTIONS = 256                     # open connections in all (a descriptor each: the process has 1 024 by default and needs some for the radio, the database and the log)
MAX_PER_ADDRESS = 32                      # and from one address; not for the loopback, where a proxy on this machine is every visitor at once


class LimitedHTTPServer(tornado.httpserver.HTTPServer):
    """The HTTP server with a cap on open connections, in all and from one address."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._streams: dict[str, list[IOStream]] = {}        # per address, in the order they came
        self._proved: set[IOStream] = set()                   # the sockets of pages that were let in (the token was right, or none is asked for): never closed to make room

    def stop_listening(self) -> None:
        """Closes the listening sockets and leaves the connections open; `listen` can be called again."""
        self.stop()
        self._sockets.clear()
        self._stopped = False

    def proved(self, stream: IOStream) -> None:
        self._proved = {s for s in self._proved if not s.closed()} | {stream}

    def _open_from(self, ip: str) -> list[IOStream]:
        live = [s for s in self._streams.get(ip, []) if not s.closed()]
        if live:
            self._streams[ip] = live
        else:
            self._streams.pop(ip, None)
        return live

    def open_connections(self) -> int:
        return sum(len(self._open_from(ip)) for ip in list(self._streams))

    def _make_room(self, ip: str) -> bool:
        """At the cap in all: the newcomer takes the place of the oldest connection that has proved nothing, of the address that holds the most of them, unless that address does
        not hold more than the newcomer's will (then the newcomer is the one refused). So whoever has fewer connections gets in (a few addresses with many silent connections
        each cannot hold every place), and a connection that has proved a token is never the one that goes."""
        held = {a: [s for s in self._open_from(a) if s not in self._proved] for a in list(self._streams)}
        biggest = max(held, key=lambda a: len(held[a]), default="")
        if not held.get(biggest) or len(held[biggest]) <= len(self._streams.get(ip, ())) + 1:
            return False
        held[biggest][0].close()
        return True

    def handle_stream(self, stream: IOStream, address: Any) -> Any:
        ip = str(address[0]) if isinstance(address, tuple) and address else ""
        loopback = is_loopback(ip)
        if len(self._streams) > 1000:                                # addresses that went away are not kept
            for gone in list(self._streams):
                self._open_from(gone)
        if (len(self._open_from(ip)) >= MAX_PER_ADDRESS and not loopback) or (self.open_connections() >= MAX_CONNECTIONS and not self._make_room(ip)):
            log.warning("too many connections: one from %s was refused", ip)
            stream.close()
            return None
        self._streams.setdefault(ip, []).append(stream)
        return super().handle_stream(stream, address)
