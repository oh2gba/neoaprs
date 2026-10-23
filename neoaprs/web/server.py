"""The web server: the page's files and one WebSocket per browser tab. Tornado on the same asyncio loop as everything else. Bound to the loopback by default, where no token is asked for.

Routes: `/ws` (the socket), `/basemap.pmtiles` and `/basemap-world.pmtiles` (the files of the data folder, with byte ranges), and everything else from the page's folder (`neoaprs/page/`, made by scripts/build-page; the folder
`neoaprs/web/placeholder/` with a line that says so while there is none). Every answer carries the security headers (neoaprs/web/headers.py) and none is given for a Host name that is not ours (neoaprs/web/pagefiles.py).
"""
import asyncio
import errno
import ipaddress
import logging
import socket
from pathlib import Path
from typing import Any, Sequence

import tornado.httpserver
import tornado.web
import tornado.websocket
from tornado.iostream import IOStream, StreamBufferFullError

from neoaprs.config import Config
from neoaprs.controller import Controller

from .api import Api
from .connections import LimitedHTTPServer
from .headers import host_name
from .outbound import MAX_WRITE_BUFFER
from .pagefiles import Basemap, Page, SecurityHeaders, refuse_foreign_host

log = logging.getLogger("neoaprs.web")

PAGE_DIR = Path(__file__).resolve().parent.parent / "page"                # neoaprs/page/, what scripts/build-page makes: package data, so it is beside the code in a wheel too
PLACEHOLDER_DIR = Path(__file__).resolve().parent / "placeholder"
MAX_COMMAND = 64 * 1024                   # what the page may send in one message (the biggest legitimate one is the settings form, a few hundred bytes); a bigger one closes the socket
MAX_REQUEST_BODY = 64 * 1024              # the page takes no upload over HTTP at all
HEADER_TIMEOUT_SEC = 60.0                 # a connection that has sent no request line, or is idle between two requests
BODY_TIMEOUT_SEC = 30.0
LOOPBACK = ("127.0.0.1", "localhost", "::1")

# The socket is compressed when the browser offers permessage-deflate (RFC 7692; every browser does): the table of the stations is large JSON with much repetition. Tornado keeps one deflate state
# for each direction of each socket, a few hundred kilobytes, and the connections are capped (neoaprs/web/connections.py).
COMPRESSION = {"compression_level": 5, "mem_level": 6}


def _looked_at(future: "asyncio.Future[None]") -> None:
    if not future.cancelled():
        future.exception()


class _Socket(SecurityHeaders, tornado.websocket.WebSocketHandler):
    def initialize(self, server: "WebServer") -> None:
        self.server = server

    def prepare(self) -> None:
        refuse_foreign_host(self, self.server)

    def get_compression_options(self) -> dict[str, Any]:
        return COMPRESSION

    def check_origin(self, origin: str) -> bool:
        # the page is served from here, so a socket from anywhere else is another site's script. That the Host is one of ours is checked in prepare():
        # an Origin that agrees with the Host proves nothing when both are the attacker's (DNS rebinding)
        host = self.request.headers.get("Host", "")
        return origin.split("://", 1)[-1].lower() == host.lower() if host else False

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


def default_page_dir() -> Path:
    return PAGE_DIR if (PAGE_DIR / "index.html").is_file() else PLACEHOLDER_DIR


PORT_TRIES = 10                                           # ports after web/port that are tried when it is taken
PORT_TAKEN = {errno.EADDRINUSE, errno.EACCES, getattr(errno, "WSAEADDRINUSE", errno.EADDRINUSE), getattr(errno, "WSAEACCES", errno.EACCES)}     # in use, or not for us to take


class WebServer:
    """`WebServer(controller, config)`; `start()` listens on `web/bind` and `web/port` of the config (port 0: a free one) and says whether it could; `stop()`."""

    def __init__(self, controller: Controller, config: Config, page_dir: Path | None = None) -> None:
        self.controller = controller
        self.config = config
        self.page_dir = page_dir or default_page_dir()
        self.api = Api(controller)
        self.address = "127.0.0.1"
        self.port = 0
        self._server: tornado.httpserver.HTTPServer | None = None
        self._own_names: set[str] = set()                 # lower case, no port: what the Host header may say besides an IP address
        self._foreign_seen: set[str] = set()              # the names refused so far, so that the log has each once

    def host_allowed(self, header: str) -> bool:
        """Is this Host header one of ours? Browsers send the name they were given, and a name is the one thing an attacker's page controls: after it has moved its name to this address the page
        is "same origin" with the daemon (DNS rebinding). An address cannot be moved, so any IP address is accepted (the phone at http://192.168.1.20:7303, a VPN address); a name has to be ours or
        listed in web/allowed_hosts."""
        name = host_name(header)
        if not name:
            return False
        if name in self._own_names:
            return True
        try:
            ipaddress.ip_address(name.split("%", 1)[0])
        except ValueError:
            return False
        return True

    def page_proved(self, stream: IOStream) -> None:
        """A socket that was let in as a page: the connection cap does not close it to make room for another."""
        if isinstance(self._server, LimitedHTTPServer):
            self._server.proved(stream)

    def note_foreign_host(self, shown: str) -> None:
        if shown not in self._foreign_seen and len(self._foreign_seen) < 20:
            self._foreign_seen.add(shown)
            log.warning("a request for the host name %r was refused; if it is a name of this computer, neoaprs db set web/allowed_hosts \"<name>\"", shown)

    def _names(self, allowed: Sequence[str]) -> set[str]:
        host = socket.gethostname().lower()
        return {"localhost", "ip6-localhost", "ip6-loopback", host, f"{host}.local", host_name(self.address), *(host_name(n) for n in allowed)} - {""}

    def url(self) -> str:
        """Where the page is: the address it listens on (the name of this computer when it listens on every interface) and the port."""
        host = self.address or socket.gethostname()
        return f"http://{'[' + host + ']' if ':' in host else host}:{self.bound_port()}/"

    async def start(self) -> bool:
        c = self.config
        self.address = "" if c.web_bind in ("*", "0.0.0.0", "::") else c.web_bind
        self._own_names = self._names([n for n in c.web_allowed_hosts.replace(",", " ").split()])
        if self.address not in LOOPBACK:
            log.warning("web/bind is %s: the page is open to everyone who can reach this computer on the network, and anyone who can open it can change the settings (there is no token)", c.web_bind)
        app = tornado.web.Application([
            (r"/ws", _Socket, {"server": self}),
            (r"/(basemap\.pmtiles|basemap-world\.pmtiles)", Basemap, {"path": str(self.controller.data_dir)}),
            (r"/()", Page, {"path": str(self.page_dir), "default_filename": "index.html"}),
            (r"/(.*)", Page, {"path": str(self.page_dir)}),
        ], websocket_ping_interval=30, websocket_ping_timeout=20, websocket_max_message_size=MAX_COMMAND, compress_response=True, log_function=self._log_request, neoaprs_server=self)
        await self.api.start()                      # (before the first page can come: the packets the database holds are in the window, the signals are connected)
        server = LimitedHTTPServer(app, xheaders=False, max_body_size=MAX_REQUEST_BODY, idle_connection_timeout=HEADER_TIMEOUT_SEC, body_timeout=BODY_TIMEOUT_SEC)
        failure = self._listen(server)
        if failure is not None:
            log.error("the web server cannot listen on %s:%d: %s; NeoAPRS goes on without the page", c.web_bind, c.web_port, failure)
            self._server = None
            await self.api.stop()
            return False
        self._server = server
        self.port = self.bound_port()
        log.info("web page at %s", self.url())
        return True

    def _listen(self, server: tornado.httpserver.HTTPServer) -> OSError | None:
        """Listens on `web/port`, or, when it is taken (or forbidden: Windows keeps ranges of ports for itself), on the first of the next `PORT_TRIES` that is free; port 0 is a free one at once.
        None when it listens, else the error of the first try (or the first error that no other port would cure)."""
        first: OSError | None = None
        wanted = self.config.web_port
        for port in range(wanted, min(wanted + (PORT_TRIES if wanted else 0), 65535) + 1):
            try:
                server.listen(port, self.address)
            except OSError as e:
                first = first or e
                if e.errno not in PORT_TAKEN:
                    return first
                continue
            if port != wanted:
                log.warning("web/port %d is in use (%s): the page is on port %d", wanted, first, port)
            return None
        return first

    @staticmethod
    def _log_request(handler: tornado.web.RequestHandler) -> None:
        if handler.get_status() >= 400:
            r = handler.request
            log.warning("%d %s %s (%s) %.2fms", handler.get_status(), r.method, r.path, r.remote_ip, 1000.0 * r.request_time())

    def bound_port(self) -> int:
        """The port actually bound (port 0 asks the system for one)."""
        if self._server is None:
            return 0
        for sock in self._server._sockets.values():   # Tornado keeps them here; there is no public accessor
            return int(sock.getsockname()[1])
        return 0

    async def stop(self) -> None:
        await self.api.stop()
        # the sockets of the open tabs are closed with a reason; otherwise close_all_connections waits out its timeout
        for client in list(self.api.clients):
            if isinstance(client, _Socket):
                client.close(1001, "NeoAPRS is stopping")
        if self._server:
            self._server.stop()
            try:
                await asyncio.wait_for(self._server.close_all_connections(), 2.0)
            except (asyncio.TimeoutError, Exception):
                pass
            self._server = None
