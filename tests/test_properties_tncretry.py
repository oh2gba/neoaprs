"""Stateful properties of a radio's line (neoaprs/tnc.py on tests/support/fakeport.py, on a loop whose time is
skipped) through starts, stops, refused opens, lost lines and the passing of time: a stopped line stays stopped and
opens nothing, whatever retry was due; a started one is never left stopped by itself and is open after the longest
back-off once opens are no longer refused; at most one port is open.
"""

import asyncio
from collections.abc import Coroutine
from typing import Any

import pytest
from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule

from neoaprs.serialport import SerialError
from neoaprs.source import Backoff, Source
from neoaprs.tnc import Tnc
from neoaprs.tncprofile import KISS
from tests.support.fakeport import FakePorts
from tests.support.virtualtime import virtual_time

PATH = "socket://fake-tnc:1"
DELAYS_SEC = (5.0, 30.0)


class Line(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.patch = pytest.MonkeyPatch()
        self.ports = FakePorts().install(self.patch)
        self.loop = asyncio.new_event_loop()
        self.time = virtual_time()
        self.run(self.time.__aenter__())
        self.tnc = Tnc(
            PATH, profile=KISS, check_sec=0.0, settle_sec=0.1, backoff=Backoff(list(DELAYS_SEC)), fallback_probe=False
        )
        self.started = False
        self.opens_at_stop = 0

    def run(self, coro: Coroutine[Any, Any, Any]) -> Any:
        return self.loop.run_until_complete(coro)

    @rule()
    def start(self) -> None:
        self.run(self.tnc.start())
        self.started = True

    @rule()
    def stop(self) -> None:
        self.run(self.tnc.stop())
        self.started = False
        self.opens_at_stop = len(self.ports.opened)

    @rule(refused=st.booleans())
    def the_open_is_refused_or_not(self, refused: bool) -> None:
        self.ports.open_error = SerialError(f"{PATH}: connection refused") if refused else None

    @precondition(lambda self: self.ports.opened and self.ports.port.is_open)
    @rule()
    def the_line_is_lost(self) -> None:
        async def lose() -> None:  # as the line's reader does it, on the loop
            self.ports.port.lose()

        self.run(lose())

    @rule(seconds=st.sampled_from([0.0, 0.05, 1.0, 5.0, 31.0, 300.0]))
    def time_passes(self, seconds: float) -> None:
        self.run(asyncio.sleep(seconds))  # the loop's clock moves on: the retries due meanwhile run
        if self.started and self.ports.open_error is None and seconds > max(DELAYS_SEC):
            assert self.tnc.state is Source.State.CONNECTED, "a line that can open is open after the longest back-off"

    @invariant()
    def a_stopped_line_stays_stopped_and_opens_nothing(self) -> None:
        if not self.started:
            assert self.tnc.state is Source.State.STOPPED
            assert len(self.ports.opened) == self.opens_at_stop
            assert not any(p.is_open for p in self.ports.opened)

    @invariant()
    def a_started_line_is_never_stopped_by_itself(self) -> None:
        if self.started:
            assert self.tnc.state is not Source.State.STOPPED

    @invariant()
    def at_most_one_port_is_open(self) -> None:
        assert sum(p.is_open for p in self.ports.opened) <= 1

    def teardown(self) -> None:
        try:
            self.run(self.tnc.stop())
            self.run(self.time.__aexit__(None, None, None))
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
        finally:
            self.loop.close()
            self.patch.undo()


Line.TestCase.settings = settings(max_examples=60, stateful_step_count=20)
test_a_radios_line_keeps_its_promises = Line.TestCase
