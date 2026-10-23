"""The web server: the page's files and one WebSocket per browser tab. Tornado on the same asyncio loop as everything else. It listens on the loopback, where no key is asked for, and, while `web/network` is on, on every
interface, where a device logs in with the access key first (neoaprs/web/access.py); the switch is followed without a restart.

While `web/https` is on too, the page is also served over TLS on the port after the plain one (neoaprs/web/secureside.py), and the plain port sends a device other than this computer there (neoaprs/web/securehandlers.py).

Routes: `/ws` (the socket), `/access` and `/access/new` (the key screen's login and a new key), `/neoaprs-ca.crt` (the certificate authority's certificate, on both ports), `/basemap.pmtiles` and `/basemap-world.pmtiles` (the files of the data folder, with byte ranges), and everything else from the page's
folder (`neoaprs/page/`, made by scripts/build-page; the folder `neoaprs/web/placeholder/` with a line that says so while there is none). Every answer carries the security headers (neoaprs/web/headers.py) and none is given for a
Host name that is not ours (neoaprs/web/pagefiles.py); the socket and the map are refused to a device that has not logged in.
"""
import asyncio
import errno
import ipaddress
import logging
import re
import socket
import ssl
from dataclasses import replace
from pathlib import Path
from typing import Any, Sequence

import tornado.httpserver
import tornado.httputil
import tornado.web
import tornado.websocket
from tornado.iostream import IOStream, StreamBufferFullError

from neoaprs.config import Config
from neoaprs.controller import Controller

from .access import Access, Login, NewKey, new_key
from .addresses import lan_addresses
from .api import Api
from .connections import LimitedHTTPServer
from .headers import host_name, origin_is_host
from .outbound import MAX_WRITE_BUFFER
from .pagefiles import Basemap, Page, SecurityHeaders, refuse_foreign_host, refuse_plain, refuse_unless_logged_in
from .securehandlers import CA_PATH, CaCertificate, secure_target
from .secureside import SecureSide
from .tls import FOLDER

log = logging.getLogger("neoaprs.web")

PAGE_DIR = Path(__file__).resolve().parent.parent / "page"                # neoaprs/page/, what scripts/build-page makes: package data, so it is beside the code in a wheel too
PLACEHOLDER_DIR = Path(__file__).resolve().parent / "placeholder"
MAX_COMMAND = 64 * 1024                   # what the page may send in one message (the biggest legitimate one is the settings form, a few hundred bytes); a bigger one closes the socket
MAX_REQUEST_BODY = 64 * 1024              # the page takes no upload over HTTP at all
HEADER_TIMEOUT_SEC = 60.0                 # a connection that has sent no request line, or is idle between two requests
BODY_TIMEOUT_SEC = 30.0
LOOPBACK = "127.0.0.1"

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


def default_page_dir() -> Path:
    return PAGE_DIR if (PAGE_DIR / "index.html").is_file() else PLACEHOLDER_DIR


PORT_TRIES = 10                                           # ports after web/port that are tried when it is taken
PORT_TAKEN = {errno.EADDRINUSE, errno.EACCES, getattr(errno, "WSAEADDRINUSE", errno.EADDRINUSE), getattr(errno, "WSAEACCES", errno.EACCES)}     # in use, or not for us to take


class WebServer:
    """`WebServer(controller, config)`; `start()` listens on `web/port` of the config (port 0: a free one), on the loopback or, while `web/network` is on, on every interface, and says whether it could; `settings_changed()` follows a
    new switch or key; `stop()`."""

    def __init__(self, controller: Controller, config: Config, page_dir: Path | None = None) -> None:
        self.controller = controller
        self.config = config
        self.page_dir = page_dir or default_page_dir()
        self.api = Api(controller, reach=self.reach, secure=lambda: self.secure.state.wire())
        self.access = Access(lambda: controller.config, controller.clock)
        self.address = LOOPBACK                           # what it listens on: "" is every interface
        self.port = 0
        self._server: LimitedHTTPServer | None = None
        self._switch = asyncio.Lock()                     # one change of what is listened on, or of the key, at a time
        self._own_names: set[str] = set()                 # lower case, no port: what the Host header may say besides an IP address
        self._foreign_seen: set[str] = set()              # the names refused so far, so that the log has each once
        self.secure = SecureSide(controller.data_dir / FOLDER, controller.clock, self._allowed_names)          # the https side: the certificates and the second port
        self._app: tornado.web.Application | None = None

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
        for server in (self._server, self.secure.server):
            if server is not None:
                server.proved(stream)

    @property
    def secure_ca(self) -> bytes | None:
        return self.secure.ca_der

    def secure_target(self, request: tornado.httputil.HTTPServerRequest) -> str | None:
        """Where a request that came over plain http from another device goes instead (neoaprs/web/securehandlers.py); None when it stays."""
        return secure_target(request, self.secure.port)

    def _allowed_names(self) -> list[str]:
        return [host_name(n) for n in self.controller.config.web_allowed_hosts.replace(",", " ").split()]

    def note_foreign_host(self, shown: str) -> None:
        if shown not in self._foreign_seen and len(self._foreign_seen) < 20:
            self._foreign_seen.add(shown)
            log.warning("a request for the host name %r was refused; if it is a name of this computer, neoaprs db set web/allowed_hosts \"<name>\"", shown)

    def _names(self, allowed: Sequence[str]) -> set[str]:
        host = socket.gethostname().lower()
        return {"localhost", "ip6-localhost", "ip6-loopback", host, f"{host}.local", *(host_name(n) for n in allowed)} - {""}

    def url(self) -> str:
        """Where the page is on this computer."""
        return f"http://{LOOPBACK}:{self.bound_port()}/"

    def reach(self) -> list[str]:
        """Where another device opens the page: this computer's address on the network and its name there; none while it listens on the loopback only."""
        if self.address != "" or self._server is None:
            return []
        hosts = [*lan_addresses(), f"{socket.gethostname().lower()}.local"]
        scheme, port = ("https", self.secure.port) if self.secure.port else ("http", self.bound_port())
        return [f"{scheme}://{host}:{port}/" for host in hosts]

    async def start(self) -> bool:
        c = self.config
        self._own_names = self._names(c.web_allowed_hosts.replace(",", " ").split())
        await self._ensure_key()
        self.address = "" if self.controller.config.web_network else LOOPBACK
        app = tornado.web.Application([
            (r"/ws", _Socket, {"server": self}),
            (r"/access", Login),
            (r"/access/new", NewKey),
            (re.escape(CA_PATH), CaCertificate, {"server": self}),
            (r"/(basemap\.pmtiles|basemap-world\.pmtiles)", Basemap, {"path": str(self.controller.data_dir)}),
            (r"/()", Page, {"path": str(self.page_dir), "default_filename": "index.html"}),
            (r"/(.*)", Page, {"path": str(self.page_dir)}),
        ], websocket_ping_interval=30, websocket_ping_timeout=20, websocket_max_message_size=MAX_COMMAND, compress_response=True, log_function=self._log_request, neoaprs_server=self)
        self._app = app
        await self.api.start()                      # (before the first page can come: the packets the database holds are in the window, the signals are connected)
        server = self._limited(None)
        failure = self._listen(server)
        if failure is not None:
            log.error("the web server cannot listen on %s:%d: %s; NeoAPRS goes on without the page", self.address or "every interface", c.web_port, failure)
            self._server = None
            await self.api.stop()
            return False
        self._server = server
        self.port = self.bound_port()
        log.info("web page at %s", self.url())
        await self._follow_secure(quiet=True)
        self.api.tasks.spawn(self._watch_secure(), "web-https")
        self._say_reach()
        return True

    def _limited(self, context: ssl.SSLContext | None) -> LimitedHTTPServer:
        assert self._app is not None
        return LimitedHTTPServer(self._app, xheaders=False, max_body_size=MAX_REQUEST_BODY, idle_connection_timeout=HEADER_TIMEOUT_SEC, body_timeout=BODY_TIMEOUT_SEC, ssl_options=context)

    def _say_reach(self) -> None:
        if urls := self.reach():
            log.info("network access is on: other devices open the page at %s and log in with the access key of Settings, Web (on this computer: neoaprs db get web/key)", ", ".join(urls))

    def _listen(self, server: LimitedHTTPServer) -> OSError | None:
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

    # ---- the switch and the key
    def settings_changed(self, config: Config) -> None:
        """The settings were saved: the switch and the key are followed, in a task."""
        if self._server is not None:
            self.api.tasks.spawn(self._follow_settings(), "web-network")

    async def _follow_settings(self) -> None:
        async with self._switch:
            await self._ensure_key()
            before = self.address
            self._relisten("" if self.controller.config.web_network else LOOPBACK)
            await self._follow_secure()
            for client in list(self.api.clients):                  # a device that is not let in any more (the key is new, or the network is off) is cut off
                if isinstance(client, _Socket) and not self.access.allowed(client.request):
                    client.close(1008, "logged out")
            if self.address != before:
                self.api.hub.changed("config")                     # (where the page can be opened from)
                self._say_reach()

    async def _follow_secure(self, quiet: bool = False) -> None:
        """The secure side is made to match `web/https` (and the network, without which it is meaningless), its certificate looked at; the page is told when it changed, and a page on the secure port that is not served any more is cut off."""
        c = self.controller.config
        changed = await self.secure.follow(c.web_https and c.web_network and self.address == "", self.address, self.bound_port(), self._limited)
        if not self.secure.state.on:
            for client in list(self.api.clients):
                if isinstance(client, _Socket) and client.request.protocol == "https":
                    client.close(1001, "the secure connection was turned off")
        if changed:
            self.api.hub.changed("config")
            if not quiet:
                self._say_reach()

    async def _watch_secure(self) -> None:
        """Now and then: a new address of this computer, or a certificate close to its end, is followed by a new certificate."""
        while True:
            await asyncio.sleep(self.secure.retry_sec)
            async with self._switch:
                await self._follow_secure()

    async def _ensure_key(self) -> None:
        """The network is on and there is no key (turned on, or on in a database made without one): a key is made."""
        c = self.controller.config
        if c.web_network and not c.web_key and not await self.controller.save_config(replace(c, web_key=new_key())):
            log.error("the access key could not be stored; devices on the network cannot log in")

    async def renew_key(self) -> bool:
        """A new access key: every session of the old one ends. False when the settings could not be stored."""
        async with self._switch:
            return await self.controller.save_config(replace(self.controller.config, web_key=new_key()))

    def _relisten(self, address: str) -> None:
        """Listens on the address instead of the one before, on the port the page is on. If it cannot, the old one is listened on again."""
        server, before = self._server, self.address
        if server is None or address == before:
            return
        server.stop_listening()
        self.address = address
        failure = self._bind(server, self.port)
        if failure is not None:
            log.error("the page cannot listen on %s:%d: %s; it stays on %s", address or "every interface", self.port, failure, before or "every interface")
            self.address = before
            self._bind(server, self.port)

    def _bind(self, server: LimitedHTTPServer, port: int) -> OSError | None:
        try:
            server.listen(port, self.address)
        except OSError as e:
            return e
        return None

    @staticmethod
    def _log_request(handler: tornado.web.RequestHandler) -> None:
        r = handler.request
        if handler.get_status() >= 400 and not (handler.get_status() == 401 and r.path == "/access"):      # (a device asking whether it is let in is told no, which is not news)
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
        await self.secure.close()
        if self._server:
            self._server.stop()
            try:
                await asyncio.wait_for(self._server.close_all_connections(), 2.0)
            except (asyncio.TimeoutError, Exception):
                pass
            self._server = None
