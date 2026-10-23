"""What the daemon says about names and what it tells the browser: the host name of a Host header and the security headers of every answer."""
import re

import tornado.httputil


def host_name(header: str) -> str:
    """The name in a Host header, without the port and the brackets of an IPv6 address, in lower case and without the dot that ends a fully qualified name; "" for no host."""
    if not header or len(header) > 255:
        return ""
    name = tornado.httputil.split_host_and_port(header.strip().lower())[0]
    if name.startswith("[") and name.endswith("]"):         # Tornado leaves the brackets of an IPv6 address on
        name = name[1:-1]
    return name.rstrip(".")


# What the browser is told about every answer of the daemon. The page is one script and one style sheet of its own and talks to its own socket only; a script that got into it by some mistake of
# ours could not load another or send anything anywhere, and no other site can frame it. The map needs nothing more: its worker is a file the page ships (a worker is held to script-src, which
# `worker-src` names again so that it reads as intended), and the base map is read from this host (connect-src 'self').
_HOST_IN_CSP = re.compile(r"^[A-Za-z0-9.\-\[\]:%]{1,255}$")


def security_headers(host: str) -> dict[str, str]:
    """The headers for an answer to a request with this Host. connect-src names the socket's own host: 'self' alone does not cover ws:// and wss:// in every browser."""
    socket_hosts = f" ws://{host} wss://{host}" if _HOST_IN_CSP.match(host) else ""
    return {
        "Content-Security-Policy": ("default-src 'self'; script-src 'self'; worker-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; "
                                    f"connect-src 'self'{socket_hosts}; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"),
        "X-Frame-Options": "DENY",                                      # for the browsers that do not read frame-ancestors
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "Cross-Origin-Resource-Policy": "same-origin",
    }


def origin_is_host(origin: str, host: str) -> bool:
    """Does the Origin header of a request name the host it was sent to? The page is served from here, so a request from another origin is another site's script."""
    return bool(host) and origin.split("://", 1)[-1].lower() == host.lower()
