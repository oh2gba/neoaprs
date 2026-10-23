"""The https side of the web server (`web/https`): a second listening port with the certificates of neoaprs/web/tls.py, on the same application as the plain one.

While `web/network` and `web/https` are both on, the page and its socket are served over TLS on the port after the plain one that is bound (7304 for 7303; if that is taken, the next free one of the ten after it). The plain
port stays open: it sends a device other than this computer to the secure port, and the loopback keeps its http (neoaprs/web/securehandlers.py). If the secure side cannot start, `problem` says why, the plain port goes on as it
was, and the page is told.

The certificate is looked at when the settings change and every hour (every five minutes while it is wanted and not working): a new address of the computer, or a certificate close to its end, makes a new one, and the
listening context takes it for the connections that come after.
"""
import asyncio
import logging
import socket
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from neoaprs.clock import Clock

from .addresses import lan_addresses
from .connections import LimitedHTTPServer
from .tls import Certificates, CertificateStore, TlsError

log = logging.getLogger("neoaprs.web")

PORT_TRIES = 10
RECHECK_SEC = 3600.0
RETRY_SEC = 300.0
ServerFactory = Callable[[ssl.SSLContext], LimitedHTTPServer]


@dataclass(frozen=True)
class SecureState:
    """What the page is told: whether the secure page is served and on which port, the fingerprint of the authority's certificate, and why it is not when it was asked for."""
    on: bool = False
    port: int = 0
    fingerprint: str = ""
    problem: str = ""

    def wire(self) -> dict[str, Any]:
        return {"on": self.on, "port": self.port, "fingerprint": self.fingerprint, "problem": self.problem}


def ports_after(plain: int) -> list[int]:
    """The ports to try for the secure listener, in order, after the plain port; a free one (0) when there is no port left to try."""
    return list(range(plain + 1, min(plain + PORT_TRIES, 65535) + 1)) or [0]


class SecureSide:
    """`SecureSide(folder, clock, names)`: `names()` gives the extra names of `web/allowed_hosts` for the certificate. `follow` is told what is wanted and where the plain server listens."""

    def __init__(self, folder: Path, clock: Clock, names: Callable[[], list[str]]) -> None:
        self._store = CertificateStore(folder, clock)
        self._names = names
        self.state = SecureState()
        self._certs: Certificates | None = None
        self.server: LimitedHTTPServer | None = None
        self._context: ssl.SSLContext | None = None
        self._loaded = ""                                           # which server certificate the context holds
        self._address: str | None = None                            # what the server listens on ("" is every interface)

    @property
    def port(self) -> int:
        """The secure port while it is served, else 0."""
        return self.state.port if self.state.on else 0

    @property
    def ca_der(self) -> bytes | None:
        """The authority's certificate for a device to trust; none while the secure connection is not wanted or has no certificates."""
        return self._certs.ca_der if self._certs is not None else None

    @property
    def retry_sec(self) -> float:
        return RETRY_SEC if self.state.problem else RECHECK_SEC

    async def follow(self, wanted: bool, address: str, plain_port: int, make_server: ServerFactory) -> bool:
        """Starts, keeps, moves or stops the secure listener to match what is wanted; True when something the page shows has changed."""
        before = self.state
        if wanted:
            await self._ensure(address, plain_port, make_server)
        else:
            self._stop()
            self._certs = None
            self.state = SecureState()
        return before != self.state

    async def _ensure(self, address: str, plain_port: int, make_server: ServerFactory) -> None:
        try:
            self._certs = await asyncio.to_thread(self._store.ensure, socket.gethostname().lower(), lan_addresses(), self._names())
        except TlsError as e:
            self._fail(str(e))
            return
        except Exception as e:                                       # (a library that fails in a way nobody listed: the plain page still works)
            log.exception("the certificates of the secure connection could not be made")
            self._fail(f"the certificates could not be made: {e}")
            return
        try:
            self._load(make_server)
        except (OSError, ssl.SSLError) as e:
            self._fail(f"the certificate cannot be loaded: {e}")
            return
        if self._address != address:
            error = self._listen(address, plain_port)
            if error is not None:
                self._stop()
                self._fail(f"the secure page cannot listen on a port after {plain_port}: {error}")
                return
        self.state = SecureState(True, self.state.port, self._certs.fingerprint, "")

    def _load(self, make_server: ServerFactory) -> None:
        assert self._certs is not None
        loaded = f"{self._certs.chain_file.stat().st_mtime_ns}"
        if self._context is None:
            self._context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            self._context.minimum_version = ssl.TLSVersion.TLSv1_2
        if loaded != self._loaded:
            self._context.load_cert_chain(self._certs.chain_file, self._certs.key_file)           # (the connections that come from now on have the new certificate)
            self._loaded = loaded
        if self.server is None:
            self.server = make_server(self._context)

    def _listen(self, address: str, plain_port: int) -> OSError | None:
        """Listens on the address, on the port it had or, for the first time, on the first free one after the plain port. None when it listens, else the first error."""
        server = self.server
        assert server is not None
        server.stop_listening()
        first: OSError | None = None
        for port in [self.state.port] if self.state.port else ports_after(plain_port):
            try:
                server.listen(port, address)
            except OSError as e:
                first = first or e
                continue
            self._address = address
            self.state = SecureState(False, port or _bound(server), "", "")
            return None
        return first

    def _fail(self, problem: str) -> None:
        log.error("the secure connection is not working: %s; the page goes on over http", problem)
        serving = self.server is not None and self._address is not None            # (a certificate that cannot be renewed in time: the one in use stays in use)
        self.state = SecureState(serving, self.state.port if serving else 0, self.state.fingerprint if serving else "", problem)
        if not serving:
            self._stop()

    def _stop(self) -> None:
        server, self.server = self.server, None
        self._context, self._loaded, self._address = None, "", None
        self.state = SecureState(False, 0, "", self.state.problem)
        if server is not None:
            server.stop()

    async def close(self) -> None:
        server = self.server
        self._stop()
        if server is not None:
            try:
                await asyncio.wait_for(server.close_all_connections(), 2.0)
            except (asyncio.TimeoutError, Exception):
                pass


def _bound(server: LimitedHTTPServer) -> int:
    for sock in server._sockets.values():                     # Tornado keeps them here; there is no public accessor
        return int(sock.getsockname()[1])
    return 0
