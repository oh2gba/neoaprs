"""The line of the Dummy radio: the Tnc gets a `Scene`'s traffic as KISS bytes.

A `TncPort` that opens nothing: a task hands the scene's due frames to the Tnc as KISS, and
frames the Tnc writes are shown to the scene and never sent on.
"""
import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from . import ax25, kiss
from .clock import Clock
from .dummyscene import Scene
from .reading import NO_READING, Reading
from .serialport import SerialError
from .tncport import TncPort

log = logging.getLogger("neoaprs.tnc")

DUMMY_PATH = "the dummy radio"  # the Tnc's name for this port
TICK_SEC = 0.5  # how often the scene is asked what is due


class SceneLike(Protocol):
    """A made-up world: what is due, the reading of each frame, a reaction to what we sent."""
    @property
    def description(self) -> str: ...
    def due(self, now: datetime) -> list[ax25.Frame]: ...
    def react(self, frame: ax25.Frame, now: datetime) -> None: ...
    def reading_of(self, frame: ax25.Frame) -> Reading: ...


SceneFactory = Callable[[tuple[float, float] | None, datetime, int], SceneLike]


class Speaker(Protocol):
    """Plays the frames of the Dummy HF radio aloud (the Mercury modem, mercurymodem.py)."""
    def play(self, data: bytes) -> None: ...


class DummyPort(TncPort):
    def __init__(self, on_data: Callable[[TncPort, bytes], None], on_lost: Callable[[TncPort, str], None], where: Callable[[], tuple[float, float] | None], clock: Clock, tick_sec: float | None = None,
                 seed: int = 1, scene_of: SceneFactory = Scene, speaker: Speaker | None = None) -> None:
        super().__init__(DUMMY_PATH, 0, on_data, on_lost)
        self._where, self._clock, self._tick_sec, self._seed = where, clock, TICK_SEC if tick_sec is None else tick_sec, seed
        # `seed` picks the world: the radio's id.
        self._scene_of, self._speaker = scene_of, speaker
        self.scene: SceneLike | None = None
        self.label = "tnc"  # the log's name for the radio (set by the Tnc)
        self._task: asyncio.Task[None] | None = None
        self._reading = NO_READING  # the reading of the frame being handed over

    @property
    def is_open(self) -> bool:
        return self._task is not None

    async def open(self) -> None:
        self.scene = self._scene_of(self._where(), self._clock(), self._seed)
        self._task = asyncio.get_running_loop().create_task(self._play(self.scene), name="dummy-radio")
        self._task.add_done_callback(self._ended)
        log.info("%s: the dummy radio makes %s", self.label, self.scene.description)

    def close(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()

    def write(self, data: bytes) -> int:
        """Show what the Tnc sends to the scene, play it if a speaker is set, drop it."""
        if self._task is None or self.scene is None:
            raise SerialError(f"{DUMMY_PATH}: not open")
        if self._speaker is not None:
            self._speaker.play(data)
        for kiss_frame in kiss.KissDecoder().feed(data):
            try:
                self.scene.react(ax25.decode(kiss_frame.payload), self._clock())
            except ax25.Ax25Error:
                continue
        return len(data)

    def _ended(self, task: "asyncio.Task[None]") -> None:
        """Treat the scene task's own failure as a lost line, so the Tnc does not stay CONNECTED."""
        if self._task is task and not task.cancelled() and task.exception() is not None:
            self._task = None
            self._lost(f"the dummy radio stopped: {task.exception()!r}")

    async def _play(self, scene: SceneLike) -> None:
        while True:
            await asyncio.sleep(self._tick_sec)
            for frame in scene.due(self._clock()):
                self._reading = scene.reading_of(frame)
                self._deliver(kiss.encode(ax25.encode(frame)))
                self._reading = NO_READING

    def take_reading(self) -> Reading:
        """Return the reading of the frame being handed over, once."""
        reading, self._reading = self._reading, NO_READING
        return reading
