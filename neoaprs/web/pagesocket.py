"""The page's WebSocket (`/ws`), one handler per browser tab."""
import asyncio
import logging
from typing import Any, Protocol

import tornado.websocket
from tornado.iostream import IOStream, StreamBufferFullError

from .access import is_local
from .api import Api
from .browser import browser_of
from .headers import origin_is_host
from .outbound import MAX_WRITE_BUFFER
from .pagefiles import HostGate, SecurityHeaders, refuse_foreign_host, refuse_plain, refuse_unless_logged_in

log = logging.getLogger("neoaprs.web")


class SocketHost(HostGate, Protocol):
    @property
    def api(self) -> Api: ...

    def page_proved(self, stream: IOStream) -> None: ...


# Compress with permessage-deflate (RFC 7692): the station table is large, repetitive JSON.
COMPRESSION = {"compression_level": 5, "mem_level": 6}


def _looked_at(future: "asyncio.Future[None]") -> None:
    if not future.cancelled():
        future.exception()


class Socket(SecurityHeaders, tornado.websocket.WebSocketHandler):
    def initialize(self, server: SocketHost) -> None:
        self.server = server

    def prepare(self) -> None:
        if not refuse_foreign_host(self, self.server) and not refuse_plain(self, self.server):
            refuse_unless_logged_in(self, self.server)

    def get_compression_options(self) -> dict[str, Any]:
        return COMPRESSION

    def check_origin(self, origin: str) -> bool:
        # The Host is checked in prepare(): a matching Origin proves nothing under DNS rebinding.
        return origin_is_host(origin, self.request.headers.get("Host", ""))

    def open(self, *args: Any, **kwargs: Any) -> None:
        self.set_nodelay(True)
        stream = getattr(self.ws_connection, "stream", None)
        if stream is not None:
            # Cut off a page that stops reading now, not when the ping times out 50 s later.
            stream.max_write_buffer_size = MAX_WRITE_BUFFER
            self.server.page_proved(stream)
        ip = self.request.remote_ip or ""
        self.server.api.attach(self, ip, is_local(self.request))
        log.info("page connected from %s: %s", ip, browser_of(self.request.headers.get("User-Agent", "")))

    def on_message(self, message: str | bytes) -> None:
        try:
            text = message.decode() if isinstance(message, bytes) else message
        except UnicodeDecodeError:
            return  # the page sends no binary frames
        self.server.api.on_command(self, text)

    def on_close(self) -> None:
        self.server.api.detach(self)

    def buffered(self) -> int:
        """Return the bytes written to the socket that the page has not read."""
        stream = getattr(self.ws_connection, "stream", None)
        # Tornado has no public count of this.
        held = getattr(stream, "_write_buffer", None)
        return 0 if held is None else len(held)

    def send_json(self, text: str) -> None:
        self._write(text, False)

    def send_binary(self, data: bytes) -> None:
        self._write(data, True)

    def _write(self, payload: str | bytes, binary: bool) -> None:
        try:
            written = self.write_message(payload, binary=binary)
            # Retrieve a later failure, or asyncio logs "exception was never retrieved".
            written.add_done_callback(_looked_at)
        except tornado.websocket.WebSocketClosedError:
            self._gone()
        except StreamBufferFullError:
            self._cut_off()

    def _gone(self) -> None:
        """Drop a push to a closed socket and detach the page (`on_close` may detach again)."""
        log.debug("a push to the closed page %s was dropped", self.request.remote_ip)
        self.server.api.detach(self)

    def _cut_off(self) -> None:
        """Close only this page: it does not read (a sleeping phone) and its buffer is full."""
        log.warning("a page that does not read was cut off (%s)", self.request.remote_ip)
        stream = getattr(self.ws_connection, "stream", None)
        if stream is not None:
            stream.close()
