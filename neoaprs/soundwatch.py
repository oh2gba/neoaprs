"""The sound server's part in a modem of a Sound card or Mercury radio (a mixin of both).

Before a start the devices the setting names are looked up, and while the program runs its streams
must sit on them: a name the server does not know plays on the default device, the loudspeakers.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from .mercuryhelper import alsa_card_names
from .mercurycards import SoundCard, endpoints
from .soundserver import Node, alsa_setting, behind, list_nodes, misplaced, missing, plugin, plugin_dir
from .soundserver import server_cards, uses_server
from .tasks import TaskSet

# Often in the first seconds of a run, when a device gone in between would play on the default one.
FIRST_WATCH_SEC, FIRST_SEC, WATCH_SEC = 0.5, 10.0, 2.0
# Rounds in a row in which the server did not answer or no stream of the program was seen: 5 s at the
# start, 20 s later. A modem opens its streams within a second, and one slow answer of the server
# passes; a run whose streams cannot be found for so long cannot be shown to stay off the loudspeakers.
UNSEEN_ROUNDS = 10
UNSEEN = "its streams are not found on the sound server"
DEVICE_GONE = "the sound device is not among those the sound server lists: choose another one in the Sound card field"


class DeviceGone(Exception):
    """A device of the setting is not in the listing of the last look-up."""


def watch_pause(elapsed_sec: float) -> float:
    return FIRST_WATCH_SEC if elapsed_sec < FIRST_SEC else WATCH_SEC


class SoundServing:
    PROGRAM: str
    LOG: logging.Logger
    sound_card: str
    _tasks: TaskSet
    _program: Any  # the modem's childprogram.Program
    nodes: tuple[Node, ...] = ()  # the server's devices at the last start that named one
    _via = "pulse"

    @property
    def pid(self) -> int | None:
        raise NotImplementedError

    def _failed(self, problem: str, reason: str) -> None:
        raise NotImplementedError

    async def _server_ready(self, setting: str) -> bool:
        """Look up the server devices the setting names; False, in the sound card state, when one is gone."""
        if not uses_server(setting):
            return True
        nodes = await asyncio.to_thread(list_nodes)
        if why := missing(setting, nodes):
            self.LOG.warning("%s is not started: %s (%s)", self.PROGRAM, DEVICE_GONE, why)
            self._failed(DEVICE_GONE, "sound_card")
            return False
        self.nodes, self._via = tuple(nodes or ()), plugin(await asyncio.to_thread(plugin_dir))
        return True

    def _server_cards(self) -> list[SoundCard]:
        """Return the sound server's devices as rows of the sound card list. Blocks."""
        return server_cards(alsa_card_names())

    def _alsa(self) -> str:
        """Return the sound card setting as the ALSA names the program opens, and have the run take
        the system's ALSA library where they are a sound server's (childprogram.environment)."""
        self._program.system_sound = uses_server(self.sound_card)
        names = alsa_setting(self.sound_card, self.nodes, self._via)
        if self._program.system_sound and not all(endpoints(names)):
            raise DeviceGone(self.sound_card)
        return names

    def _behind(self) -> str:
        """Return the ALSA card the program's sound is on (its levels, its USB tie); "" for a device a user made."""
        return behind(self.sound_card, self.nodes, alsa_card_names())

    def _watch_server(self, on_fault: Callable[[str], None]) -> None:
        """Watch the streams of the run just started; `on_fault` gets why one strayed, once."""
        if uses_server(self.sound_card) and (pid := self.pid) is not None:
            self._tasks.spawn(self._watching(pid, self.sound_card, on_fault), f"{self.PROGRAM.lower()}-sound-server")

    async def _watching(self, pid: int, setting: str, on_fault: Callable[[str], None]) -> None:
        started, unseen = time.monotonic(), 0
        while self.pid == pid:
            why = await asyncio.to_thread(misplaced, setting, pid)
            unseen = unseen + 1 if why is None else 0
            if why or unseen >= UNSEEN_ROUNDS:
                on_fault(f"[sound server] {why or UNSEEN}")
                return
            await asyncio.sleep(watch_pause(time.monotonic() - started))
