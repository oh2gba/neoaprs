"""The page's WebSocket (`/ws`): one handler for each browser tab. It checks the Host, the scheme and the login before it opens, hands the commands of the page to the Api and writes the daemon's messages to the tab,
cutting off a tab that does not read."""
import asyncio
import logging
from typing import Any, Protocol

import tornado.websocket
from tornado.iostream import IOStream, StreamBufferFullError

from .api import Api
from .headers import origin_is_host
from .outbound import MAX_WRITE_BUFFER
from .pagefiles import HostGate, SecurityHeaders, refuse_foreign_host, refuse_plain, refuse_unless_logged_in

log = logging.getLogger("neoaprs.web")


class SocketHost(HostGate, Protocol):
    """What a socket needs of the WebServer."""
    @property
    def api(self) -> Api: ...

    def page_proved(self, stream: IOStream) -> None: ...


# The socket is compressed when the browser offers permessage-deflate (RFC 7692; every browser does): the table of the stations is large JSON with much repetition. Tornado keeps one deflate state
# for each direction of each socket, a few hundred kilobytes, and the connections are capped (neoaprs/web/connections.py).
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
        # the page is served from here, so a socket from anywhere else is another site's script. That the Host is one of ours is checked in prepare():
        # an Origin that agrees with the Host proves nothing when both are the attacker's (DNS rebinding)
        return origin_is_host(origin, self.request.headers.get("Host", ""))

    def open(self, *args: Any, **kwargs: Any) -> None:
        self.set_nodelay(True)
        stream = getattr(self.ws_connection, "stream", None)
        if stream is not None:
            stream.max_write_buffer_size = MAX_WRITE_BUFFER          # a page that stops reading is cut off here, not when the ping times out 50 s later
            self.server.page_proved(stream)
        ip = self.request.remote_ip or ""
        self.server.api.attach(self, ip)
        log.info("page connected from %s", ip)

    def on_message(self, message: str | bytes) -> None:
        try:
            text = message.decode() if isinstance(message, bytes) else message
        except UnicodeDecodeError:
            return                                   # a binary frame that is no text: the page sends none, so it is ignored
        try:
            self.server.api.on_command(self, text)
        except RecursionError:
            return                                   # JSON nested deeper than the parser can follow

    def on_close(self) -> None:
        self.server.api.detach(self)

    def buffered(self) -> int:
        """What the socket holds that the page has not read: the number the write limit is held against (neoaprs/web/hub.py calls a page behind when it is a share of it)."""
        stream = getattr(self.ws_connection, "stream", None)
        held = getattr(stream, "_write_buffer", None)          # Tornado has no public count; this is what it compares max_write_buffer_size with
        return 0 if held is None else len(held)

    def send_json(self, text: str) -> None:
        try:
            written = self.write_message(text)
            # the future of a write that fails later (the page left, or was cut off) is looked at, or asyncio logs "exception was never retrieved" for each message in flight
            written.add_done_callback(_looked_at)
        except tornado.websocket.WebSocketClosedError:
            self._gone()
        except StreamBufferFullError:
            self._cut_off()

    def _gone(self) -> None:
        """The page's socket is closed (it hung up, or its closing has begun and Tornado has not yet told the daemon): the push is dropped and the page is forgotten now, so that the pushes
        that follow do not look for it. `Api.detach` can be asked again by `on_close`."""
        log.debug("a push to the closed page %s was dropped", self.request.remote_ip)
        self.server.api.detach(self)

    def _cut_off(self) -> None:
        """This page is the only one that is closed: a page that does not read (a phone gone to sleep with the socket open) has a buffer that is full and no frame can be written to it."""
        log.warning("a page that does not read was cut off (%s)", self.request.remote_ip)
        stream = getattr(self.ws_connection, "stream", None)
        if stream is not None:
            stream.close()
