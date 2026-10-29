"""Where the web server listens (neoaprs/web/listen.py): the ports that are tried and the loop that tries them, which the plain port and the secure port share. A server that is a stand-in whose ports are
taken as the test says."""
import errno
import logging

import pytest

from neoaprs.web.listen import PORT_TAKEN, PORT_TRIES, listen_first, listen_near, ports_near
from neoaprs.web.secureside import ports_after


class Server:
    """Listens on a port unless the test has taken it, and says which with the error a real one raises."""

    def __init__(self, taken: set[int], error: int = errno.EADDRINUSE) -> None:
        self.taken, self.error = taken, error
        self.tried: list[int] = []

    def listen(self, port: int, address: str) -> None:
        self.tried.append(port)
        if port in self.taken:
            raise OSError(self.error, "taken")


def test_the_ports_tried_are_the_wanted_one_and_the_ten_after_it_and_a_free_port_is_only_itself() -> None:
    assert ports_near(7303) == list(range(7303, 7303 + PORT_TRIES + 1))
    assert ports_near(65534) == [65534, 65535] and ports_near(0) == [0]
    assert ports_after(7303) == list(range(7304, 7304 + PORT_TRIES)) and ports_after(65535) == [0]


def test_the_first_free_port_is_the_one_listened_on_and_the_first_error_is_told(caplog: pytest.LogCaptureFixture) -> None:
    server = Server({7303, 7304})
    port, first = listen_first(server, "127.0.0.1", ports_near(7303))  # type: ignore[arg-type]
    assert port == 7305 and server.tried == [7303, 7304, 7305] and first is not None and first.errno in PORT_TAKEN
    caplog.set_level(logging.WARNING, logger="neoaprs.web")
    assert listen_near(Server({7303}), "127.0.0.1", 7303) is None  # type: ignore[arg-type]
    assert "web/port 7303 is in use" in caplog.text and "the page is on port 7304" in caplog.text


def test_an_error_that_no_other_port_cures_ends_the_tries_and_all_ports_taken_gives_the_first_error() -> None:
    server = Server({7303}, errno.EADDRNOTAVAIL)
    port, first = listen_first(server, "10.9.9.9", ports_near(7303))  # type: ignore[arg-type]
    assert port is None and first is not None and first.errno == errno.EADDRNOTAVAIL and server.tried == [7303]
    everything = Server(set(range(7303, 7303 + PORT_TRIES + 1)))
    error = listen_near(everything, "127.0.0.1", 7303)  # type: ignore[arg-type]
    assert isinstance(error, OSError) and error.errno == errno.EADDRINUSE and len(everything.tried) == PORT_TRIES + 1
