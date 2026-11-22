"""The https side of the web server (`web/https`): a second port with the certificates of tls.py.

While `web/network` and `web/https` are on, the page is also served over TLS on the first free
port after the plain one; if that cannot start, `problem` and `reason` say why.
"""
import asyncio
import logging
import socket
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from neoaprs.clock import Clock

from .addresses import lan_addresses
from .configwire import HttpsReason
from .connections import LimitedHTTPServer
from .listen import listen_first, ports_near

if TYPE_CHECKING:
    from .tls import Certificates, CertificateStore

log = logging.getLogger("neoaprs.web")

# in the data folder: the authority and the computer's certificate
FOLDER = "tls"
RECHECK_SEC = 3600.0
RETRY_SEC = 300.0
ServerFactory = Callable[[ssl.SSLContext], LimitedHTTPServer]


@dataclass(frozen=True)
class SecureState:
    """Whether the secure page is served, its port and the CA fingerprint, and why not if asked."""
    on: bool = False
    port: int = 0
    fingerprint: str = ""
    problem: str = ""  # English text for the log
    reason: HttpsReason = ""  # the same as a code for the page

    def wire(self) -> dict[str, Any]:
        return {"on": self.on, "port": self.port, "fingerprint": self.fingerprint, "reason": self.reason}


def ports_after(plain: int) -> list[int]:
    """Return the ports to try after the plain port, or [0] (any free port) when none is left."""
    return ports_near(plain)[1:] or [0]


class SecureSide:
    """Manage the https listener; `names()` gives certificate names from `web/allowed_hosts`."""

    def __init__(self, folder: Path, clock: Clock, names: Callable[[], list[str]]) -> None:
        self._folder, self._clock = folder, clock
        # Made when first wanted: tls.py loads the cryptography library.
        self._store: CertificateStore | None = None
        self._names = names
        self.state = SecureState()
        self._certs: Certificates | None = None
        self.server: LimitedHTTPServer | None = None
        self._context: ssl.SSLContext | None = None
        self._loaded = ""  # which server certificate the context holds
        self._address: str | None = None  # what the server listens on; "" is every interface

    @property
    def port(self) -> int:
        """The secure port while it is served, else 0."""
        return self.state.port if self.state.on else 0

    @property
    def ca_der(self) -> bytes | None:
        """Return the CA certificate, or None while there are no certificates."""
        return self._certs.ca_der if self._certs is not None else None

    @property
    def retry_sec(self) -> float:
        return RETRY_SEC if self.state.problem else RECHECK_SEC

    async def follow(self, wanted: bool, address: str, plain_port: int, make_server: ServerFactory) -> bool:
        """Start, keep, move or stop the secure listener; return True if the state changed."""
        before = self.state
        if wanted:
            await self._ensure(address, plain_port, make_server)
        else:
            server = self.server
            self._stop()
            self._certs = None
            self.state = SecureState()
            if server is not None:
                await _close_connections(server)
        return before != self.state

    async def _ensure(self, address: str, plain_port: int, make_server: ServerFactory) -> None:
        try:
            from .tls import CertificateStore, TlsError
        except Exception:
            log.exception("the library of the secure connection cannot be loaded")
            self._fail("the secure connection cannot be had in this installation", "no_library")
            return
        if self._store is None:
            self._store = CertificateStore(self._folder, self._clock)
        try:
            self._certs = await asyncio.to_thread(self._store.ensure, socket.gethostname().lower(), lan_addresses(), self._names())
        except TlsError as e:
            self._fail(str(e), "clock" if e.clock else "certificates")
            return
        except Exception as e:  # any other library failure; http still works
            log.exception("the certificates of the secure connection could not be made")
            self._fail(f"the certificates could not be made: {e}", "certificates")
            return
        try:
            self._load(make_server)
        except (OSError, ssl.SSLError) as e:
            self._fail(f"the certificate cannot be loaded: {e}", "certificates")
            return
        if self._address != address:
            error = self._listen(address, plain_port)
            if error is not None:
                self._stop()
                self._fail(f"the secure page cannot listen on a port after {plain_port}: {error}", "no_port")
                return
        self.state = SecureState(True, self.state.port, self._certs.fingerprint, "")

    def _load(self, make_server: ServerFactory) -> None:
        assert self._certs is not None
        loaded = f"{self._certs.chain_file.stat().st_mtime_ns}"
        if self._context is None:
            self._context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            self._context.minimum_version = ssl.TLSVersion.TLSv1_2
        if loaded != self._loaded:
            self._context.load_cert_chain(self._certs.chain_file, self._certs.key_file)
            self._loaded = loaded
        if self.server is None:
            self.server = make_server(self._context)

    def _listen(self, address: str, plain_port: int) -> OSError | None:
        """Listen on the port held before, else the first free one after the plain port."""
        server = self.server
        assert server is not None
        server.stop_listening()
        port, first = listen_first(server, address, [self.state.port] if self.state.port else ports_after(plain_port))
        if port is None:
            return first
        self._address = address
        self.state = SecureState(False, port or _bound(server), "", "")
        return None

    def _fail(self, problem: str, reason: HttpsReason) -> None:
        log.error("the secure connection is not working: %s; the page goes on over http", problem)
        # A certificate that cannot be renewed: the one in use stays.
        serving = self.server is not None and self._address is not None
        self.state = SecureState(serving, self.state.port if serving else 0, self.state.fingerprint if serving else "", problem, reason)
        if not serving:
            self._stop()

    def _stop(self) -> None:
        server, self.server = self.server, None
        self._context, self._loaded, self._address = None, "", None
        self.state = SecureState(False, 0, "", self.state.problem, self.state.reason)
        if server is not None:
            server.stop()

    async def close(self) -> None:
        server = self.server
        self._stop()
        if server is not None:
            await _close_connections(server)


async def _close_connections(server: LimitedHTTPServer) -> None:
    try:
        await asyncio.wait_for(server.close_all_connections(), 2.0)
    except Exception as e:  # includes the timeout
        log.warning("the connections of the secure port did not end in time: %r", e)


def _bound(server: LimitedHTTPServer) -> int:
    for sock in server._sockets.values():  # no public accessor in Tornado
        return int(sock.getsockname()[1])
    return 0
