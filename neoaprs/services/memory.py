"""Daemon state kept across restarts, such as when the beacon and status last went out.

The state lives in rows of the settings table, outside `Config`. Writes run in a task so the
send path never waits for the database; without a `Memory` nothing is remembered."""
import asyncio
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Protocol

from neoaprs.clock import iso
from neoaprs.tasks import TaskSet

log = logging.getLogger("neoaprs.memory")


class Memory(Protocol):
    """The part of the Store used here."""
    async def setting(self, key: str) -> str | None: ...
    async def put_settings(self, data: dict[str, str]) -> bool: ...


def stamp(t: datetime) -> str:
    """Return the time as ISO 8601 UTC to the second, e.g. `2026-10-21T12:00:00Z`."""
    return iso(t) or ""


def unstamp(text: str | None) -> datetime | None:
    """Return the stored time, or None if absent or unparseable."""
    if not text:
        return None
    try:
        t = datetime.fromisoformat(text)
    except ValueError:
        return None
    return t.astimezone(UTC) if t.tzinfo is not None else None


class Remembered:
    def __init__(self, memory: Memory | None) -> None:
        self._memory = memory
        self._writes = TaskSet(self._failed)

    async def get(self, key: str) -> str | None:
        return None if self._memory is None else await self._memory.setting(key)

    async def get_time(self, key: str, now: datetime) -> datetime | None:
        """Return the stored time; None if absent or after `now`.

        A time in the future (clock set back) would otherwise hold things off for the whole jump."""
        t = unstamp(await self.get(key))
        return t if t is not None and t <= now else None

    def put(self, data: Mapping[str, str]) -> None:
        """Write the rows together in a task; the caller does not wait."""
        if self._memory is not None:
            self._writes.spawn(self._put(self._memory, dict(data)), "remember")

    @staticmethod
    async def _put(memory: Memory, data: dict[str, str]) -> None:
        await memory.put_settings(data)

    async def flush(self) -> None:
        """Wait for pending writes."""
        await asyncio.gather(*self._writes, return_exceptions=True)

    @staticmethod
    def _failed(task: "asyncio.Task[None]") -> None:
        log.error("remembering failed: %r", task.exception())
