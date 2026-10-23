"""Rig: what the tests of a service that sends frames by a schedule (the beacon, the status, the queries, the digipeater, messaging, the own objects and bulletins) all build first: the station's settings, a clock the
test holds and a Tnc that is a stub. A test module subclasses it and adds its service.

    class Rig(ServiceRig):
        def __init__(self, **changes: object) -> None:
            super().__init__(**changes)                    # self.config (ON_AIR with the changes), self.clock, self.tnc
            self.beacon = Beacon(self.tnc, lambda: self.config, self.clock)

    rig.set(station_call="OH2XYZ")                         # the settings change under the running service (its `lambda: self.config` sees it)
    rig.lines()                                            # the frames the stub Tnc took, as TNC-2 lines
    rig.record(service)                                    # rig.changed / rig.removed: what the service's `changed` / `removed` signals gave

A rig whose parts are not these (a service with no Tnc, a desktop shell, a Tnc on a fake radio) stays local to its test module."""
from dataclasses import replace
from typing import Any

from tests.support.clock import FixedClock
from tests.support.env import ON_AIR
from tests.support.stubtnc import StubTnc


class ServiceRig:
    def __init__(self, clock: FixedClock | None = None, tnc: StubTnc | None = None, **changes: object) -> None:
        self.config = replace(ON_AIR, **changes)              # type: ignore[arg-type]
        self.clock = clock if clock is not None else FixedClock()      # (or the one a test shares between two runs of the daemon)
        self.tnc = tnc if tnc is not None else StubTnc()
        self.changed: list[Any] = []
        self.removed: list[Any] = []

    def set(self, **changes: object) -> None:
        self.config = replace(self.config, **changes)         # type: ignore[arg-type]

    def lines(self) -> list[str]:
        return self.tnc.lines()

    def record(self, service: Any) -> None:
        """Keeps what the service announces in `changed` and `removed` (the signals of the services that keep records)."""
        service.changed.connect(self.changed.append)
        service.removed.connect(self.removed.append)
