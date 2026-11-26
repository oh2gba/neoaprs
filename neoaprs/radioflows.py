"""One flow at a time for each radio: a (re)start, a repoint of its line, or a hold for Find my radio.

A new flow waits for the one under way to end: a restart or repoint is cancelled first, a hold's stop
is not cut short. A repoint asked while a restart runs is owed to the end of that restart.
"""

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, Literal

from .radiotype import RadioId
from .tasks import cancel_all

Kind = Literal["restart", "repoint", "hold"]
Spawn = Callable[[Coroutine[Any, Any, None], str], "asyncio.Task[None]"]


class RadioFlows:
    def __init__(self, spawn: Spawn) -> None:
        self._spawn = spawn
        self._flows: dict[RadioId, tuple[Kind, asyncio.Task[None]]] = {}
        self._owed: set[RadioId] = set()
        # radios Find my radio holds: none is started meanwhile
        self.held: set[RadioId] = set()

    def running(self, id: RadioId) -> Kind | None:
        """Return the kind of the radio's flow under way, or None."""
        flow = self._flows.get(id)
        return None if flow is None or flow[1].done() else flow[0]

    def begin(self, id: RadioId, kind: Kind, work: Callable[[], Awaitable[None]], name: str) -> "asyncio.Task[None]":
        """Run `work` as the radio's flow once the flow under way has ended; return its task."""
        task = self._spawn(self._after(self._flows.get(id), work), name)
        self._flows[id] = (kind, task)
        return task

    async def _after(
        self, previous: tuple[Kind, "asyncio.Task[None]"] | None, work: Callable[[], Awaitable[None]]
    ) -> None:
        if previous is not None:
            kind, task = previous
            if kind == "hold":
                await asyncio.wait([task])
            else:
                await cancel_all([task])
        await work()

    def owe_repoint(self, id: RadioId) -> bool:
        """Return True, and remember the repoint, if a restart of the radio is under way."""
        if self.running(id) != "restart":
            return False
        self._owed.add(id)
        return True

    def take_owed(self, id: RadioId) -> bool:
        """Return whether a repoint was owed to the radio's restart, and forget it."""
        owed = id in self._owed
        self._owed.discard(id)
        return owed

    async def hold(self, id: RadioId, stop: Callable[[], Awaitable[None]], name: str) -> None:
        """Hold the radio (no start until `release`) and stop it, after the flow under way."""
        self.held.add(id)
        self._owed.discard(id)
        await asyncio.shield(self.begin(id, "hold", stop, name))

    def release(self, id: RadioId) -> None:
        self.held.discard(id)

    async def end_all(self) -> None:
        """Cancel every flow and wait for each."""
        tasks, self._flows = [task for _, task in self._flows.values()], {}
        self._owed.clear()
        await cancel_all(tasks)
