"""What the beacon and the status report remember across a restart: when each last went out (and what the status said), as rows of the settings table (`STATE_KEYS` of config.py). They are state
of the daemon, not settings the operator edits, so they are not in `Config` (the settings form does not list them and `Config.from_data` leaves them alone).

`Memory` is the part of the Store that is used (the Store itself fits). `Remembered` reads a row at the start and writes in a task after a send, so that the send path never waits for the
database; `flush()` waits for the writes in flight (the stop of the part), and a Remembered without a Memory remembers nothing.
"""
import asyncio
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Protocol

from neoaprs.clock import iso
from neoaprs.tasks import TaskSet

log = logging.getLogger("neoaprs.memory")


class Memory(Protocol):
    """What is used of the Store: one row read, rows written together."""
    async def setting(self, key: str) -> str | None: ...
    async def put_settings(self, data: dict[str, str]) -> bool: ...


def stamp(t: datetime) -> str:
    """The time as it is kept: ISO 8601, UTC, to the second (`2026-10-21T12:00:00Z`)."""
    return iso(t) or ""


def unstamp(text: str | None) -> datetime | None:
    """The time of a kept row; None when there is none or it is not a time (a row someone edited by hand is as good as none)."""
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
        """The time kept in the row; None when there is none or it is later than `now` (the clock was set back: such a time would hold things off for as long as the jump)."""
        t = unstamp(await self.get(key))
        return t if t is not None and t <= now else None

    def put(self, data: Mapping[str, str]) -> None:
        """The rows, written in a task (all of them or none); the caller does not wait."""
        if self._memory is not None:
            self._writes.spawn(self._put(self._memory, dict(data)), "remember")

    @staticmethod
    async def _put(memory: Memory, data: dict[str, str]) -> None:
        await memory.put_settings(data)

    async def flush(self) -> None:
        """Waits until the writes in flight are done."""
        await asyncio.gather(*self._writes, return_exceptions=True)

    @staticmethod
    def _failed(task: "asyncio.Task[None]") -> None:
        log.error("remembering failed: %r", task.exception())
