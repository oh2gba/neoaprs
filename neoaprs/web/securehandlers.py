"""What the plain http port does while the secure page is served (neoaprs/web/secureside.py), and the authority's certificate for the devices that want to trust it.

A request that is not from this computer, and came over plain http, is sent to the same address on the secure port (`refuse_plain` of neoaprs/web/pagefiles.py answers it with this target): a page request with a redirect
(so that old bookmarks work), anything else (the socket, a login, the map) is refused with a line that says where the page is now. A request from this computer itself is left alone (on the loopback, http is a secure
context already, and the desktop app's window is there).
`GET /neoaprs-ca.crt` is on both ports and is never redirected: it is the way to a certificate that makes the warning go away. It is the public certificate only, in DER, for a download named NeoAPRS-CA.crt.
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
    """Where a request goes instead, `https://host:port` with the Host name the request had: for one that came over plain http from another device while the secure page is served on `port` (0: it is not); else None."""
    if port == 0 or request.protocol != "http" or is_local(request):
        return None
    name = host_name(request.headers.get("Host", ""))
    return f"https://{f'[{name}]' if ':' in name else name}:{port}"


class CaCertificate(SecurityHeaders):
    """The authority's certificate (public), on either port, for any device that asks; 404 while the secure connection is off."""

    def initialize(self, server: SecureServer) -> None:
        self.server = server

    def prepare(self) -> None:
        refuse_foreign_host(self, self.server)

    def get(self) -> None:
        der = self.server.secure_ca
        if der is None:
            raise tornado.web.HTTPError(404, reason="Not Found: the secure connection is off, turn it on in Settings, Web page")
        self.set_header("Content-Type", "application/x-x509-ca-cert")
        self.set_header("Content-Disposition", f'attachment; filename="{CA_FILE_NAME}"')
        self.set_header("Cache-Control", "no-cache")
        self.finish(der)

    head = get
