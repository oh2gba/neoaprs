"""Entry into KISS mode: write the steps of a TNC profile (tncprofile.py), each followed by a pause.

The first step is written at once and the others as the pauses pass, in a task, so that nothing
waits. The pause after the last step is the settle time, during which TNC output is discarded.
"""

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

from .tncprofile import Profile


class KissEntry:
    def __init__(
        self,
        spawn: Callable[[Coroutine[Any, Any, None]], "asyncio.Task[None]"],
        write: Callable[[bytes], bool],
        settle_sec: float | None = None,
        pace: float = 1.0,
    ) -> None:
        self._spawn = spawn
        # Writes to the Tnc's line; returns False on failure.
        self._write = write
        self.settle_sec, self.pace = settle_sec, pace

    def pauses(self, profile: Profile) -> list[float]:
        """Return the seconds to wait after each step, scaled by `pace`; last is `settle_sec`."""
        pauses = [pause * self.pace for _, pause in profile.enter]
        if self.settle_sec is not None and pauses:
            pauses[-1] = self.settle_sec
        return pauses

    def begin(self, profile: Profile, alive: Callable[[], bool]) -> float | None:
        """Write the first step now and the rest as their pauses pass, while `alive()` is true.

        Return the seconds the whole entry takes, or None if the first write failed.
        """
        pauses = self.pauses(profile)
        if not profile.enter or not self._write(profile.enter[0][0]):
            return None
        if len(profile.enter) > 1:
            self._spawn(self._rest([data for data, _ in profile.enter[1:]], pauses, alive))
        return sum(pauses)

    async def _rest(self, steps: list[bytes], pauses: list[float], alive: Callable[[], bool]) -> None:
        for data, pause in zip(steps, pauses):
            await asyncio.sleep(pause)
            if not alive() or not self._write(data):
                return
