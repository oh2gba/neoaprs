"""The ports the tests' pages are served on (tests/support/webports.py): each worker has a block of its
own, below every system's ephemeral range and the tests' modems, and no real modem's port is in it."""

import pytest

from neoaprs import nodevices
from neoaprs.web.listen import PORT_TRIES
from tests.support import webports


def block(worker: int) -> set[int]:
    first = webports.FIRST + webports.WORKER_SPAN * worker
    return set(range(first, first + webports.WORKER_SPAN))


def test_the_blocks_of_the_workers_do_not_overlap_and_lie_where_nothing_else_is() -> None:
    blocks = [block(w) for w in range(webports.WORKERS)]
    assert sum(len(b) for b in blocks) == len(set().union(*blocks)), "one block per worker"
    every = set().union(*blocks)
    assert max(every) < 20000, (
        "below the tests' modems (tests/support/modemports.py) and 32768 (Linux), 49152 (Windows)"
    )
    assert not any(nodevices.modem_port(p) for p in every)


def test_a_test_takes_the_next_ports_of_its_workers_block(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw3")
    ports = [webports.next_web_port() for _ in range(webports.WORKER_SPAN // webports.TEST_SPAN + 1)]
    assert all(p in block(3) for p in ports) and ports[0] == ports[-1], "round the block again"
    assert all(b - a >= 2 * PORT_TRIES + 1 for a, b in zip(sorted(set(ports)), sorted(set(ports))[1:])), (
        "room for the page's tries and its secure side's"
    )
    assert max(ports) + 2 * PORT_TRIES + 1 < webports.FIRST + webports.WORKER_SPAN * 4
