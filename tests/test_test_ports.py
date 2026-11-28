"""The ports the tests' pages are served on (tests/support/webports.py): each worker has a block of its
own, below every system's ephemeral range and the tests' modems, and no real modem's port is in it; a
port is taken only when it and the ports after it that the page and its secure side try are free."""

import socket
import sys
from pathlib import Path

import pytest

from neoaprs import nodevices
from neoaprs.web.listen import PORT_TRIES
from tests.support import modemports, webports


def block(worker: int) -> set[int]:
    first = webports.FIRST + webports.WORKER_SPAN * worker
    return set(range(first, first + webports.WORKER_SPAN))


def test_the_blocks_of_the_workers_do_not_overlap_and_lie_where_nothing_else_is() -> None:
    blocks = [block(w) for w in range(webports.WORKERS)]
    assert sum(len(b) for b in blocks) == len(set().union(*blocks)), "one block per worker, -n 32 and less"
    every = set().union(*blocks)
    assert max(every) < 20000, (
        "below the tests' modems (tests/support/modemports.py) and 32768 (Linux), 49152 (Windows)"
    )
    assert not any(nodevices.modem_port(p) for p in every)
    assert webports.TEST_SPAN >= 2 * PORT_TRIES + 1, "room for the page's tries and its secure side's"


def test_a_worker_past_the_last_block_gets_a_port_the_system_picks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTEST_XDIST_WORKER", f"gw{webports.WORKERS}")
    assert webports.next_web_port() == 0, "never another worker's block"


def test_a_slot_with_one_taken_port_is_passed_over_and_a_full_block_falls_back_to_the_system(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw3")
    taken = set(range(webports.FIRST + webports.WORKER_SPAN * 3, webports.FIRST + webports.WORKER_SPAN * 3 + 230))
    taken.discard(webports.FIRST + webports.WORKER_SPAN * 3 + 9 * webports.TEST_SPAN)  # one port of slot 9 free
    port = webports.next_web_port(lambda p: p not in taken)
    assert port == 0, "no slot is free whole"
    free_slot = webports.FIRST + webports.WORKER_SPAN * 3 + 5 * webports.TEST_SPAN
    taken -= set(range(free_slot, free_slot + webports.TEST_SPAN))
    assert webports.next_web_port(lambda p: p not in taken) == free_slot


def test_a_port_another_run_listens_on_is_not_handed_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw5")
    first = webports.FIRST + webports.WORKER_SPAN * 5
    held = []
    try:
        for slot in range(webports.SLOTS - 1):  # every slot but the last has a listener of "another run"
            s = socket.socket()
            try:
                s.bind(("127.0.0.1", first + slot * webports.TEST_SPAN + 3))
            except OSError:
                s.close()
                pytest.skip("a port of the block is in use on this machine")
            s.listen()
            held.append(s)
        assert webports.next_web_port() in (first + (webports.SLOTS - 1) * webports.TEST_SPAN, 0)
    finally:
        for s in held:
            s.close()


@pytest.mark.skipif(sys.platform == "win32", reason="locks of the lanes: POSIX")
def test_two_runs_of_the_suite_on_one_machine_take_two_lanes_of_ports_for_the_same_worker(tmp_path: Path) -> None:
    """The stop/start flake of round 20: another run's worker of the same number had the same ports."""
    first, held = modemports.claim_lane(3, tmp_path)
    second, other = modemports.claim_lane(3, tmp_path)
    assert (first, second) == (3, 4) and held is not None and other is not None
    held.close()
    third, again = modemports.claim_lane(3, tmp_path)
    assert third == 3, "a lane is free again once its run is gone"
    for lock in (other, again):
        assert lock is not None
        lock.close()
