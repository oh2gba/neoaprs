"""The sound server's part in a modem of a Sound card or Mercury radio (a mixin of both).

Before a start the devices the setting names are looked up, and while the program runs its streams
must sit on them: a name the server does not know plays on the default device, the loudspeakers.
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from .mercuryhelper import alsa_card_names
from .mercurycards import SoundCard
from .soundserver import Node, alsa_setting, behind, list_nodes, misplaced, missing, plugin, plugin_dir
from .soundserver import server_cards, uses_server
from .tasks import TaskSet

WATCH_SEC = 2.0
DEVICE_GONE = "the sound device is not among those the sound server lists: choose another one in the Sound card field"


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
        return alsa_setting(self.sound_card, self.nodes, self._via)

    def _behind(self) -> str:
        """Return the ALSA card the program's sound is on (its levels, its USB tie); "" for a device a user made."""
        return behind(self.sound_card, self.nodes, alsa_card_names())

    def _watch_server(self, on_fault: Callable[[str], None]) -> None:
        """Watch the streams of the run just started; `on_fault` gets why one strayed, once."""
        if uses_server(self.sound_card) and (pid := self.pid) is not None:
            self._tasks.spawn(self._watching(pid, self.sound_card, on_fault), f"{self.PROGRAM.lower()}-sound-server")

    async def _watching(self, pid: int, setting: str, on_fault: Callable[[str], None]) -> None:
        while self.pid == pid:
            if why := await asyncio.to_thread(misplaced, setting, pid):
                on_fault(f"[sound server] {why}")
                return
            await asyncio.sleep(WATCH_SEC)
