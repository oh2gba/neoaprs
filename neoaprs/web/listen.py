"""Where the web server listens: the port of the settings, or the next free one."""
import errno
import logging

from .connections import LimitedHTTPServer

log = logging.getLogger("neoaprs.web")

PORT_TRIES = 10                                           # ports after the wanted one that are tried when it is taken
PORT_TAKEN = {errno.EADDRINUSE, errno.EACCES, getattr(errno, "WSAEADDRINUSE", errno.EADDRINUSE), getattr(errno, "WSAEACCES", errno.EACCES)}     # in use, or not for us to take


def ports_near(wanted: int) -> list[int]:
    """`wanted` and the `PORT_TRIES` ports after it (up to 65535); port 0, a free one at once, is only itself."""
    return [wanted] if wanted == 0 else list(range(wanted, min(wanted + PORT_TRIES, 65535) + 1))


def listen_first(server: LimitedHTTPServer, address: str, ports: list[int]) -> tuple[int | None, OSError | None]:
    """Listens on the first of `ports` that is free (a port that is in use, or forbidden: Windows keeps ranges of ports for itself, is passed over; any other error ends the tries): (that port or None, the first
    error there was, None when the first try listened)."""
    first: OSError | None = None
    for port in ports:
        try:
            server.listen(port, address)
        except OSError as e:
            first = first or e
            if e.errno not in PORT_TAKEN:
                break
            continue
        return port, first
    return None, first


def listen_near(server: LimitedHTTPServer, address: str, wanted: int) -> OSError | None:
    """Listens on `wanted`, or, when it is taken, on the first of the next `PORT_TRIES` that is free. None when it listens, else the error of the first try."""
    port, first = listen_first(server, address, ports_near(wanted))
    if port is None:
        return first
    if port != wanted:
        log.warning("web/port %d is in use (%s): the page is on port %d", wanted, first, port)
    return None
