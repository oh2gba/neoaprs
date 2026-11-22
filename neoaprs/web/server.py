"""The web server: the page's files and one WebSocket per browser tab, on Tornado and asyncio.

It listens on loopback, and on every interface while `web/network` is on, where a device logs in
with the access key (access.py). The switch is followed without a restart.
"""

import asyncio
import logging
import re
import socket
import ssl
from dataclasses import replace
from pathlib import Path
from typing import Sequence

import tornado.httpserver
import tornado.httputil
import tornado.web
import tornado.websocket
from tornado.iostream import IOStream

from neoaprs.cli.logfile import PAGE_FORMAT, remove_page, write_network, write_page
from neoaprs.config import Config
from neoaprs.controller import Controller
from neoaprs.tasks import every
from neoaprs.worldmap import world_file

from .access import OWN_NAMES, Access, Login, NewKey, new_key, this_computer_target
from .addresses import as_address, is_loopback, lan_addresses
from .api import Api
from .connections import LimitedHTTPServer
from .headers import host_name
from .listen import listen_near
from .pagefiles import MAX_LOGGED_PATH, Basemap, Page
from .pageerrors import one_line
from .pagesnapshot import PageSnapshot
from .pagesocket import Socket
from .securehandlers import CA_PATH, CaCertificate, secure_target
from .secureside import FOLDER, SecureSide
from .supporthandler import Bundler, SupportBundle
from .supportsend import SupportSend

log = logging.getLogger("neoaprs.web")

# neoaprs/page/, built by scripts/build-page.
PAGE_DIR = Path(__file__).resolve().parent.parent / "page"
PLACEHOLDER_DIR = Path(__file__).resolve().parent / "placeholder"
# Largest message the page may send; a bigger one closes the socket.
MAX_COMMAND = 64 * 1024
MAX_REQUEST_BODY = 64 * 1024  # no uploads over HTTP
HEADER_TIMEOUT_SEC = 60.0  # no request line yet, or idle between two requests
BODY_TIMEOUT_SEC = 30.0
LOOPBACK = "127.0.0.1"
HOSTS_FILE = Path("/etc/hosts")


def name_loopbacks(hosts: Path = HOSTS_FILE) -> list[str]:
    """Return the extra loopback addresses the hosts file gives this computer's name.

    Debian uses 127.0.1.1. The file is read, not the name resolved, so no name server is asked.
    """
    own = socket.gethostname().lower()
    try:
        lines = hosts.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    found: set[str] = set()
    for line in lines:
        address, *names = line.split("#", 1)[0].split() or [""]
        if (
            is_loopback(address)
            and address != LOOPBACK
            and any(n.lower() == own or n.lower().startswith(f"{own}.") for n in names)
        ):
            found.add(address)
    return sorted(found)


def default_page_dir() -> Path:
    return PAGE_DIR if (PAGE_DIR / "index.html").is_file() else PLACEHOLDER_DIR


class WebServer:
    """`start()` listens on `web/port` (0: any free port; `kept_port` first) and returns success."""

    def __init__(
        self, controller: Controller, config: Config, page_dir: Path | None = None, kept_port: int = 0
    ) -> None:
        self.controller = controller
        self.config = config
        self.kept_port = kept_port
        self.page_dir = page_dir or default_page_dir()
        self.page = PageSnapshot.take(self.page_dir)
        log.info(
            "page %s: %d files, %.1f MB, kept in memory",
            self.page.build or "(none)",
            len(self.page.files),
            self.page.size / 1048576,
        )
        self.api = Api(controller, reach=self.reach, secure=lambda: self.secure.state.wire(), page=self.page.build)
        self.access = Access(lambda: controller.config, controller.clock)
        self.address = LOOPBACK  # what it listens on; "" is every interface
        self._by_name: list[str] = []
        self.port = 0
        self._server: LimitedHTTPServer | None = None
        self._switch = asyncio.Lock()  # one change of the listened address or the key at a time
        self._own_names: set[str] = set()
        self._foreign_seen: set[str] = set()  # refused names, so the log has each once
        self.secure = SecureSide(controller.data_dir / FOLDER, controller.clock, self._allowed_names)
        self.bundles = Bundler(self)
        self._app: tornado.web.Application | None = None

    def host_allowed(self, header: str) -> bool:
        """Return True if the Host header is ours (DNS rebinding defence).

        Any IP address is accepted; a name must be ours or listed in web/allowed_hosts.
        """
        name = host_name(header)
        if not name:
            return False
        if name in self._own_names:
            return True
        return as_address(name) is not None

    def page_proved(self, stream: IOStream) -> None:
        """Mark a socket as a logged-in page so the connection cap never closes it to make room."""
        for server in (self._server, self.secure.server):
            if server is not None:
                server.proved(stream)

    @property
    def secure_ca(self) -> bytes | None:
        return self.secure.ca_der

    def secure_target(self, request: tornado.httputil.HTTPServerRequest) -> str | None:
        """Return the secure URL for a plain-http request from another device, else None."""
        return secure_target(request, self.secure.port)

    def this_computer_target(self, request: tornado.httputil.HTTPServerRequest) -> str | None:
        """Return the 127.0.0.1 URL for a loopback request by another name, else None."""
        return this_computer_target(request, self.controller.config.web_network, self.bound_port())

    def _allowed_names(self) -> list[str]:
        return [host_name(n) for n in self.controller.config.web_allowed_hosts.replace(",", " ").split()]

    def note_foreign_host(self, shown: str) -> None:
        if shown not in self._foreign_seen and len(self._foreign_seen) < 20:
            self._foreign_seen.add(shown)
            log.warning(
                'a request for the host name %r was refused; if it is a name of this computer, neoaprs db set web/allowed_hosts "<name>"',
                shown,
            )

    def _names(self, allowed: Sequence[str]) -> set[str]:
        host = socket.gethostname().lower()
        return {
            *OWN_NAMES,
            "ip6-localhost",
            "ip6-loopback",
            host,
            f"{host}.local",
            *(host_name(n) for n in allowed),
        } - {""}

    def url(self) -> str:
        """Return the page's URL on this computer."""
        return f"http://{LOOPBACK}:{self.bound_port()}/"

    def reach(self) -> list[str]:
        """Return the URLs where another device opens the page.

        Empty while listening on loopback only.
        """
        if self.address != "" or self._server is None:
            return []
        hosts = [*lan_addresses(), f"{socket.gethostname().lower()}.local"]
        scheme, port = ("https", self.secure.port) if self.secure.port else ("http", self.bound_port())
        return [f"{scheme}://{host}:{port}/" for host in hosts]

    async def start(self) -> bool:
        c = self.config
        self._own_names = self._names(c.web_allowed_hosts.replace(",", " ").split())
        await self._ensure_key()
        self._by_name = name_loopbacks()
        self.address = "" if self.controller.config.web_network else LOOPBACK
        app = tornado.web.Application(
            [
                (r"/ws", Socket, {"server": self}),
                (r"/access", Login),
                (r"/access/new", NewKey),
                (r"/support/bundle", SupportBundle, {"server": self}),
                (r"/support/send", SupportSend, {"server": self}),
                (re.escape(CA_PATH), CaCertificate, {"server": self}),
                (
                    r"/(basemap\.pmtiles|basemap-world\.pmtiles)",
                    Basemap,
                    {"path": str(self.controller.data_dir), "world": lambda: world_file(self.controller.data_dir)},
                ),
                (r"/()", Page, {"path": str(self.page_dir), "snapshot": self.page, "default_filename": "index.html"}),
                (r"/(.*)", Page, {"path": str(self.page_dir), "snapshot": self.page}),
            ],
            websocket_ping_interval=30,
            websocket_ping_timeout=20,
            websocket_max_message_size=MAX_COMMAND,
            compress_response=True,
            log_function=self._log_request,
            neoaprs_server=self,
        )
        self._app = app
        await self.api.start()
        server = self._limited(None)
        remove_page(self.controller.data_dir)  # drop a stale address left by an earlier run
        failure = listen_near(server, self.address, c.web_port, self.kept_port)
        if failure is not None:
            log.error(
                "the web server cannot listen on %s:%d: %s; NeoAPRS goes on without the page",
                self.address or "every interface",
                c.web_port,
                failure,
                exc_info=failure,
            )
            self._server = None
            await self.api.stop()
            return False
        self._server = server
        self._listen_by_name(server)
        self.port = self.bound_port()
        log.info(PAGE_FORMAT, self.url())
        self._tell_the_page()
        await self._follow_secure(quiet=True)
        self.api.tasks.spawn(
            every(lambda: self.secure.retry_sec, self._recheck_secure, "the secure side check"), "web-https"
        )
        self._say_reach()
        return True

    def _tell_the_page(self) -> None:
        """Write the page's address into the data folder, where commands find it."""
        try:
            write_page(self.controller.data_dir, self.url())
        except OSError as e:
            log.warning(
                "the page's address could not be written into the data folder (%s); the commands look for it in the log",
                e,
            )
        self._tell_the_network()

    def _tell_the_network(self) -> None:
        """Write whether the page is served to the network into the data folder."""
        try:
            write_network(self.controller.data_dir, self.address == "")
        except OSError as e:
            log.info("the note that the page is served to the network could not be written (%s)", e)

    def _limited(self, context: ssl.SSLContext | None) -> LimitedHTTPServer:
        assert self._app is not None
        return LimitedHTTPServer(
            self._app,
            xheaders=False,
            max_body_size=MAX_REQUEST_BODY,
            idle_connection_timeout=HEADER_TIMEOUT_SEC,
            body_timeout=BODY_TIMEOUT_SEC,
            ssl_options=context,
        )

    def _say_reach(self) -> None:
        if urls := self.reach():
            log.info(
                "network access is on: other devices open the page at %s and log in with the access key of Settings, Web (on this computer: neoaprs db get web/key)",
                ", ".join(urls),
            )

    # the switch and the key
    def settings_changed(self, config: Config) -> None:
        """Follow a changed switch or key in a task."""
        if self._server is not None:
            self.api.tasks.spawn(self._follow_settings(), "web-network")

    async def _follow_settings(self) -> None:
        async with self._switch:
            await self._ensure_key()
            before = self.address
            self._relisten("" if self.controller.config.web_network else LOOPBACK)
            self._tell_the_network()
            await self._follow_secure()
            for client in list(self.api.clients):
                if isinstance(client, Socket) and not self.access.allowed(client.request):
                    client.close(1008, "logged out")
            if self.address != before:
                self.api.hub.changed("config")  # the URLs the page can be opened from changed
                self._say_reach()

    async def _follow_secure(self, quiet: bool = False) -> None:
        """Make the secure side match `web/https` and the network; cut off pages on a closed port."""
        c = self.controller.config
        changed = await self.secure.follow(
            c.web_https and c.web_network and self.address == "", self.address, self.bound_port(), self._limited
        )
        if not self.secure.state.on:
            for client in list(self.api.clients):
                if isinstance(client, Socket) and client.request.protocol == "https":
                    client.close(1001, "the secure connection was turned off")
        if changed:
            self.api.hub.changed("config")
            if not quiet:
                self._say_reach()

    async def _recheck_secure(self) -> None:
        """Periodic check: a new address or an expiring certificate gets a new certificate."""
        async with self._switch:
            await self._follow_secure()

    async def _ensure_key(self) -> None:
        """Make an access key when the network is on and there is none."""
        c = self.controller.config
        if (
            c.web_network
            and not c.web_key
            and not await self.controller.change_config(
                lambda base: replace(base, web_key=new_key()) if base.web_network and not base.web_key else base
            )
        ):
            log.error("the access key could not be stored; devices on the network cannot log in")

    async def renew_key(self) -> bool:
        """Make a new access key, ending every session.

        Return False if the settings could not be stored.
        """
        async with self._switch:
            return await self.controller.change_config(lambda base: replace(base, web_key=new_key()))

    def _relisten(self, address: str) -> None:
        """Listen on the new address on the current port; fall back to the old one if that fails."""
        server, before = self._server, self.address
        if server is None or address == before:
            return
        server.stop_listening()
        self.address = address
        failure = self._bind(server, self.port)
        if failure is not None:
            log.error(
                "the page cannot listen on %s:%d: %s; it stays on %s",
                address or "every interface",
                self.port,
                failure,
                before or "every interface",
            )
            self.address = before
            self._bind(server, self.port)

    def _bind(self, server: LimitedHTTPServer, port: int) -> OSError | None:
        try:
            server.listen(port, self.address)
        except OSError as e:
            return e
        self._listen_by_name(server)
        return None

    def _listen_by_name(self, server: LimitedHTTPServer) -> None:
        """On loopback, also listen on the loopback addresses of this computer's name."""
        if self.address != LOOPBACK:
            return
        port = self.bound_port()
        for address in self._by_name:
            try:
                server.listen(port, address)
            except OSError as e:
                log.info("the page is not on %s:%d, where this computer's own name leads: %s", address, port, e)

    @staticmethod
    def _log_request(handler: tornado.web.RequestHandler) -> None:
        r = handler.request
        # A 401 on /access is a device asking whether it is let in; not worth logging.
        if handler.get_status() >= 400 and not (handler.get_status() == 401 and r.path == "/access"):
            log.warning(
                "%d %s %s (%s) %.2fms",
                handler.get_status(),
                r.method,
                one_line(r.path, MAX_LOGGED_PATH),
                r.remote_ip,
                1000.0 * r.request_time(),
            )

    def bound_port(self) -> int:
        """Return the bound port (port 0 lets the system choose)."""
        if self._server is None:
            return 0
        for sock in self._server._sockets.values():  # no public accessor in Tornado
            return int(sock.getsockname()[1])
        return 0

    async def stop(self) -> None:
        remove_page(self.controller.data_dir)
        await self.api.stop()
        # Close tabs first, or close_all_connections waits out its timeout.
        for client in list(self.api.clients):
            if isinstance(client, Socket):
                client.close(1001, "NeoAPRS is stopping")
        await self.secure.close()
        if self._server:
            self._server.stop()
            try:
                await asyncio.wait_for(self._server.close_all_connections(), 2.0)
            except Exception as e:  # includes the timeout
                log.warning("the connections of the page did not end in time: %r", e)
            self._server = None
