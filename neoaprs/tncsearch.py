"""The search for the radio: every port that matches the pattern is listened to at the same time, for as long as it takes, and the one whose bytes look like the radio's is the answer. It runs as a task
of the Tnc that asks (so that the Tnc's stop() ends it) and says which ports it has open while it runs. Where it may not run (not Linux: `serialprobe.can_search`) it answers with the reason, and the radio is the port
that was named or remembered."""
import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from . import serialprobe
from .serialport import SerialError

log = logging.getLogger("neoaprs.tnc")


class PortSearch:
    def __init__(self, spawn: Callable[[Coroutine[Any, Any, None]], "asyncio.Task[None]"], note: Callable[[str], None], nudge: bytes) -> None:
        self._spawn = spawn
        self._nudge = nudge                                              # written to every port that has been quiet for nudge_sec: a TNC in command mode answers
        self._note = note
        self.listening: list[str] = []                                   # the ports the search has open, while it runs
        self._searched: list[str] = []                                   # the ports the latest search opened

    @property
    def possible(self) -> bool:
        return serialprobe.can_search()

    async def find(self, pattern: str, baud: int, seconds: float, looks_valid: Callable[[bytes], bool], nudge: bool, nudge_sec: float, skip: tuple[str, ...], wanted: Callable[[], bool]) -> str:
        """The port of the radio. Raises SerialError with the reason when there is none; returns "" when `wanted()` turned false (the Tnc was stopped) meanwhile. `nudge`: whether a carriage return may be
        written to the quiet ports (a profile that cannot be asked is only listened to)."""
        if not self.possible:
            raise SerialError("no port is chosen: the radio is not looked for among the ports on this system, so choose its port in the settings")
        paths = serialprobe.candidate_ports(pattern)
        if not paths:
            raise SerialError(f"no port matches {pattern}")
        outcome: list[str | None] = []
        self._searched = []

        async def search() -> None:
            outcome.append(await serialprobe.probe(paths, baud, seconds, looks_valid, self._nudge if nudge else None, nudge_sec, self._opened, skip))

        task = self._spawn(search())
        try:
            await asyncio.wait([task])
        finally:
            self.listening = []
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        if not wanted():
            return ""
        if not outcome:
            raise SerialError("the search for the radio failed")
        if outcome[0] is None:
            if not self._searched:
                raise SerialError(f"no port could be listened to (skipped, held by another program or not openable: {', '.join(paths)})")
            raise SerialError(f"no port delivers KISS frames (tried {', '.join(self._searched)})")
        return outcome[0]

    def _opened(self, opened: list[str]) -> None:
        self.listening = self._searched = opened
        if opened:
            text = f"listening on {', '.join(opened)} for the radio"
            log.info("tnc: %s", text)
            self._note(text)
