"""Where the web server listens: the port of the settings, or the next free one."""
import errno
import logging

from .connections import LimitedHTTPServer

log = logging.getLogger("neoaprs.web")

PORT_TRIES = 10                                           # ports after web/port that are tried when it is taken
PORT_TAKEN = {errno.EADDRINUSE, errno.EACCES, getattr(errno, "WSAEADDRINUSE", errno.EADDRINUSE), getattr(errno, "WSAEACCES", errno.EACCES)}     # in use, or not for us to take


def listen_near(server: LimitedHTTPServer, address: str, wanted: int) -> OSError | None:
    """Listens on `wanted`, or, when it is taken (or forbidden: Windows keeps ranges of ports for itself), on the first of the next `PORT_TRIES` that is free; port 0 is a free one at once.
    None when it listens, else the error of the first try (or the first error that no other port would cure)."""
    first: OSError | None = None
    for port in range(wanted, min(wanted + (PORT_TRIES if wanted else 0), 65535) + 1):
        try:
            server.listen(port, address)
        except OSError as e:
            first = first or e
            if e.errno not in PORT_TAKEN:
                return first
            continue
        if port != wanted:
            log.warning("web/port %d is in use (%s): the page is on port %d", wanted, first, port)
        return None
    return first
