"""Choose the port the web server listens on: the configured one, else the next free one."""
import errno
import logging

from .connections import LimitedHTTPServer

log = logging.getLogger("neoaprs.web")

# Ports tried after the wanted one when it is taken.
PORT_TRIES = 10
# Port in use, or not ours to take (Windows reserves some ranges).
PORT_TAKEN = {errno.EADDRINUSE, errno.EACCES, getattr(errno, "WSAEADDRINUSE", errno.EADDRINUSE), getattr(errno, "WSAEACCES", errno.EACCES)}


def ports_near(wanted: int) -> list[int]:
    """Return `wanted` and the `PORT_TRIES` ports after it (up to 65535); port 0 stands alone."""
    return [wanted] if wanted == 0 else list(range(wanted, min(wanted + PORT_TRIES, 65535) + 1))


def listen_first(server: LimitedHTTPServer, address: str, ports: list[int]) -> tuple[int | None, OSError | None]:
    """Listen on the first free port; return (port or None, first error or None).

    A port in `PORT_TAKEN` is skipped; any other error ends the tries.
    """
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


def listen_near(server: LimitedHTTPServer, address: str, wanted: int, kept: int = 0) -> OSError | None:
    """Listen on `wanted`, else on the next free port; return None on success, else the first error.

    `kept` is the port used before a restart (0 for none), tried first because open pages reconnect.
    """
    if kept and kept != wanted:
        port, error = listen_first(server, address, [kept])
        if port is not None:
            log.info("the page stays on port %d, where it was before the restart", kept)
            return None
        log.warning("port %d, where the page was before the restart, cannot be had (%s): a page that is open there in a browser does not find NeoAPRS again (the app's window follows)", kept, error)
    port, first = listen_first(server, address, ports_near(wanted))
    if port is None:
        return first
    if port != wanted:
        log.warning("web/port %d is in use (%s): the page is on port %d", wanted, first, port)
    return None
