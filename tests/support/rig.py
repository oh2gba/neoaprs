"""Rig: what the tests of a service that sends frames on a schedule build first: the station's
settings, a clock the test holds and a stub Tnc. A test module subclasses it and adds its service.
"""
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from neoaprs.ownlog import OwnLog
from neoaprs.services.sender import Sender
from tests.support.clock import FixedClock
from tests.support.env import ON_AIR
from tests.support.stubtnc import StubTnc


class ServiceRig:
    def __init__(self, clock: FixedClock | None = None, tnc: StubTnc | None = None, **changes: object) -> None:
        self.config = replace(ON_AIR, **changes)              # type: ignore[arg-type]
        # Or the one a test shares between two runs of the daemon
        self.clock = clock if clock is not None else FixedClock()
        self.tnc = tnc if tnc is not None else StubTnc()
        self.changed: list[Any] = []
        self.removed: list[Any] = []

    def set(self, **changes: object) -> None:
        self.config = replace(self.config, **changes)         # type: ignore[arg-type]

    def lines(self) -> list[str]:
        return self.tnc.lines()

    def record(self, service: Any) -> None:
        """Keeps what the service announces in `changed` and `removed` (the signals of the services
        that keep records)."""
        service.changed.connect(self.changed.append)
        service.removed.connect(self.removed.append)


class OwnRig(ServiceRig):
    """One run of the daemon's own objects or bulletins: made again on the same log and clock after
    a stop. `sent` is what the Tnc took, as (seconds since the rig was made, the information field).
    """

    def __init__(self, log: OwnLog, clock: FixedClock, **changes: object) -> None:
        super().__init__(clock, **changes)                        # type: ignore[arg-type]
        self.log, self.begin = log, clock()
        self.sender = Sender(self.tnc, lambda: self.config, clock, spacing_sec=10.0)
        self.sent: list[tuple[int, bytes]] = []

    def look(self, tick: Callable[[], None], seconds: int, step: int) -> None:
        """Looks at the clock (`tick`) every `step` seconds for this long, the first look now; the
        clock ends where the last look was."""
        for _ in range(0, seconds + 1, step):
            before = len(self.tnc.sent)
            tick()
            self.sent += [(round((self.clock() - self.begin).total_seconds()), frame.info) for frame in self.tnc.sent[before:]]
            self.clock.advance(step)
        self.clock.advance(-step)

    def offsets(self) -> list[int]:
        return [t for t, _ in self.sent]

    async def settled(self) -> None:
        assert self.log.db is not None
        await self.log.db.barrier()
