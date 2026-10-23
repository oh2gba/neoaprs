"""The entry into KISS: the steps of a TNC profile (tncprofile.py) written to the line one after the other, each followed by its pause. The first step goes at once and the others as the pauses pass, in a task of
the Tnc that asks, so that nothing waits for them; the pause after the last step is the settle time, in which what the TNC says is thrown away."""
import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

from .tncprofile import Profile


class KissEntry:
    def __init__(self, spawn: Callable[[Coroutine[Any, Any, None]], "asyncio.Task[None]"], write: Callable[[bytes], bool], settle_sec: float | None = None, pace: float = 1.0) -> None:
        self._spawn = spawn
        self._write = write                      # writes to the line of the Tnc, False when that failed
        self.settle_sec, self.pace = settle_sec, pace

    def pauses(self, profile: Profile) -> list[float]:
        """The wait after each step, in seconds: scaled by `pace`, the last one (the settle time) `settle_sec` when that is given."""
        pauses = [pause * self.pace for _, pause in profile.enter]
        if self.settle_sec is not None and pauses:
            pauses[-1] = self.settle_sec
        return pauses

    def begin(self, profile: Profile, alive: Callable[[], bool]) -> float | None:
        """Writes the first step now and the rest as their pauses pass (while `alive()`: the line is still the one this was started for). The seconds the whole entry takes, or None when the first write failed."""
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
