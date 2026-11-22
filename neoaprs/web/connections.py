"""A cap on open web connections, in all and per address, that makes room for whoever has fewest.

Tornado has no cap: a silent host holds a file descriptor per connection until the header timeout,
and the daemon needs descriptors for its database, its radio and the log.
"""
import logging
from typing import Any

import tornado.httpserver
from tornado.iostream import IOStream

from .addresses import is_loopback

log = logging.getLogger("neoaprs.web")

# Open connections in all; each takes a descriptor and the default limit is 1024.
MAX_CONNECTIONS = 256
# Per address, except loopback, where a local proxy stands for every visitor.
MAX_PER_ADDRESS = 32


class LimitedHTTPServer(tornado.httpserver.HTTPServer):
    """The HTTP server with a cap on open connections, in all and per address."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._streams: dict[str, list[IOStream]] = {}  # per address, oldest first
        # Sockets of pages that were let in (right token, or none required); never closed to make
        # room.
        self._proved: set[IOStream] = set()

    def stop_listening(self) -> None:
        """Close the listening sockets, keep the connections open; `listen` may be called again."""
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
        """At the cap, close the oldest unproved connection of the busiest address.

        Return False, refusing the newcomer, if that address holds no more than the newcomer's would.
        """
        held = {a: [s for s in self._open_from(a) if s not in self._proved] for a in list(self._streams)}
        biggest = max(held, key=lambda a: len(held[a]), default="")
        if not held.get(biggest) or len(held[biggest]) <= len(self._streams.get(ip, ())) + 1:
            return False
        held[biggest][0].close()
        return True

    def handle_stream(self, stream: IOStream, address: Any) -> Any:
        ip = str(address[0]) if isinstance(address, tuple) and address else ""
        loopback = is_loopback(ip)
        if len(self._streams) > 1000:  # drop addresses that went away
            for gone in list(self._streams):
                self._open_from(gone)
        if (len(self._open_from(ip)) >= MAX_PER_ADDRESS and not loopback) or (self.open_connections() >= MAX_CONNECTIONS and not self._make_room(ip)):
            log.warning("too many connections: one from %s was refused", ip)
            stream.close()
            return None
        self._streams.setdefault(ip, []).append(stream)
        return super().handle_stream(stream, address)
