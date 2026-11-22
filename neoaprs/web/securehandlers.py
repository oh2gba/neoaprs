"""Plain-http handling while the secure page is served, and the CA certificate download.

Plain http from another device is redirected to the secure port or refused; loopback is left
alone. `GET /neoaprs-ca.crt` serves the public CA certificate (DER) on both ports.
"""

from typing import Protocol

import tornado.httputil
import tornado.web

from .access import is_local
from .headers import host_name
from .pagefiles import HostGate, SecurityHeaders, refuse_foreign_host

CA_PATH = "/neoaprs-ca.crt"
CA_FILE_NAME = "NeoAPRS-CA.crt"


class SecureServer(HostGate, Protocol):
    @property
    def secure_ca(self) -> bytes | None: ...


def secure_target(request: tornado.httputil.HTTPServerRequest, port: int) -> str | None:
    """Return `https://host:port` for a plain-http request from another device, else None.

    `port` is the secure port, 0 when it is not served.
    """
    if port == 0 or request.protocol != "http" or is_local(request):
        return None
    name = host_name(request.headers.get("Host", ""))
    return f"https://{f'[{name}]' if ':' in name else name}:{port}"


class CaCertificate(SecurityHeaders):
    """The public CA certificate; 404 while the secure connection is off."""

    def initialize(self, server: SecureServer) -> None:
        self.server = server

    def prepare(self) -> None:
        refuse_foreign_host(self, self.server)

    def get(self) -> None:
        der = self.server.secure_ca
        if der is None:
            raise tornado.web.HTTPError(
                404, reason="Not Found: the secure connection is off, turn it on in Settings, Web page"
            )
        self.set_header("Content-Type", "application/x-x509-ca-cert")
        self.set_header("Content-Disposition", f'attachment; filename="{CA_FILE_NAME}"')
        self.set_header("Cache-Control", "no-cache")
        self.finish(der)

    head = get
