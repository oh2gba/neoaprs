"""The search for the radio: every port that matches the pattern is listened to at the same time, for as long as it takes, and the one whose bytes look like the radio's is the answer. It runs as a task
of the Tnc that asks (so that the Tnc's stop() ends it) and says which ports it has open while it runs. Where it may not run (not Linux: `serialprobe.can_search`) it answers with the reason, and the radio is the port
that was named or remembered."""
import asyncio
import logging
import os
from collections.abc import Callable, Coroutine
from typing import Any

from . import serialprobe
from .serialport import SerialError, is_url

log = logging.getLogger("neoaprs.tnc")


class PortSearch:
    def __init__(self, spawn: Callable[[Coroutine[Any, Any, None]], "asyncio.Task[None]"], note: Callable[[str], None], nudge: bytes) -> None:
        self._spawn = spawn
        self._nudge = nudge                                              # written to every port that has been quiet for nudge_sec: a TNC in command mode answers
        self._note = note
        self.listening: list[str] = []                                   # the ports the search has open, while it runs
        self._searched: list[str] = []                                   # the ports the latest search opened
        self._told: set[str] = set()                                     # the boards that were logged as skipped (once each, however often the search runs)

    @property
    def possible(self) -> bool:
        return serialprobe.can_search()

    async def find(self, pattern: str, baud: int, seconds: float, looks_valid: Callable[[bytes], bool], nudge: bool, nudge_sec: float, skip: tuple[str, ...], wanted: Callable[[], bool], also: str = "") -> tuple[str, bytes]:
        """The port of the radio and what it was heard to say (the Tnc tells from it whether the TNC it found is in command mode). Raises SerialError with the reason when there is none; returns ("", b"")
        when `wanted()` turned false (the Tnc was stopped) meanwhile. `nudge`: whether a carriage return may be written to the quiet ports (a profile that cannot be asked is only listened to). `also`: a
        port listened to as well whenever it exists, whether or not it matches the pattern (the named port the search stands in for while that cannot be opened). The ports are listed again every
        `serialprobe.RELIST_SEC` while the search listens, so a radio plugged back in is found while another port keeps talking."""
        if not self.possible:
            raise SerialError("no port is chosen: the radio is not looked for among the ports on this system, so choose its port in the settings")
        paths, boards = await self._listing(pattern, also)
        if not paths:
            if boards:
                raise SerialError(f"no port to listen to: {'; '.join(f'{path} is {what}' for path, what in boards.items())}, which the search leaves alone; choose the port by its name in the settings to use it")
            raise SerialError(f"no port matches {pattern}")
        outcome: list[tuple[str, bytes] | None] = []
        self._searched = []

        async def relist() -> list[str]:
            return (await self._listing(pattern, also))[0]

        async def search() -> None:
            outcome.append(await serialprobe.probe_heard(paths, baud, seconds, looks_valid, self._nudge if nudge else None, nudge_sec, self._opened, skip, relist))

        task = self._spawn(search())
        try:
            await asyncio.wait([task])
        finally:
            self.listening = []
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        if not wanted():
            return "", b""
        if not outcome:
            raise SerialError("the search for the radio failed")
        if outcome[0] is None:
            if not self._searched:
                raise SerialError(f"no port could be listened to (skipped, held by another program or not openable: {', '.join(paths)})")
            raise SerialError(f"no port delivers KISS frames (tried {', '.join(self._searched)})")
        return outcome[0]

    async def _listing(self, pattern: str, also: str) -> tuple[list[str], dict[str, str]]:
        """The ports the search listens to now and the boards it leaves out (told once each); `also` is added when it is a device file that exists. The system's list is read from files: not on the loop."""
        paths, boards = await asyncio.to_thread(serialprobe.searchable_ports, pattern)
        self._tell_boards(boards)
        if also and not is_url(also) and also not in paths and os.path.exists(also):
            paths.append(also)
        return paths, boards

    def _tell_boards(self, boards: dict[str, str]) -> None:
        for path, what in boards.items():
            if path not in self._told:
                self._told.add(path)
                log.info("tnc: skipping %s: %s", path, what)

    def _opened(self, opened: list[str]) -> None:
        self.listening = opened
        self._searched = sorted(set(self._searched) | set(opened))
        if opened:
            text = f"listening on {', '.join(opened)} for the radio"
            log.info("tnc: %s", text)
            self._note(text)
