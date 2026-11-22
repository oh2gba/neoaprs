"""Host header parsing, the security headers of every response and the Origin check."""

import re

import tornado.httputil
import tornado.web


def host_name(header: str) -> str:
    """Return the lower-case name in a Host header, without port, IPv6 brackets or trailing dot.

    Return "" if there is no host.
    """
    if not header or len(header) > 255:
        return ""
    name = tornado.httputil.split_host_and_port(header.strip().lower())[0]
    if name.startswith("[") and name.endswith("]"):  # Tornado keeps the brackets of an IPv6 address
        name = name[1:-1]
    return name.rstrip(".")


# Content Security Policy: only the page's own script, style and socket, so an injected script
# cannot load another or send data out, and no other site can frame it.
_HOST_IN_CSP = re.compile(r"^[A-Za-z0-9.\-\[\]:%]{1,255}$")


def security_headers(host: str) -> dict[str, str]:
    """Return the headers for a response to a request with this Host.

    connect-src names the host because 'self' alone does not cover ws:// in every browser.
    """
    socket_hosts = f" ws://{host} wss://{host}" if _HOST_IN_CSP.match(host) else ""
    return {
        "Content-Security-Policy": (
            "default-src 'self'; script-src 'self'; worker-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; "
            f"connect-src 'self'{socket_hosts}; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
        ),
        "X-Frame-Options": "DENY",  # for browsers that ignore frame-ancestors
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "Cross-Origin-Resource-Policy": "same-origin",
    }


def origin_is_host(origin: str, host: str) -> bool:
    """Return True if the Origin names the host the request was sent to.

    Another origin is another site's script.
    """
    return bool(host) and origin.split("://", 1)[-1].lower() == host.lower()


def refuse_foreign_origin(request: tornado.httputil.HTTPServerRequest) -> None:
    """Raise a 403 when the request carries an Origin that is not the host it was sent to."""
    origin = request.headers.get("Origin")
    if origin is not None and not origin_is_host(origin, request.headers.get("Host", "")):
        raise tornado.web.HTTPError(403)
