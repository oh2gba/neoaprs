"""The line of the Dummy radio: where a real radio's serial line would be, the Tnc (tnc.py) gets the made-up traffic of a `Scene` (dummyscene.py) as KISS bytes, and what it writes is read by the scene and goes nowhere.

It is a `TncPort` that opens nothing: no serial port, no socket, no file, no other program. A task plays the scene once every half second: the frames that have come due are encoded as AX.25 and KISS and handed to
the Tnc as a line would hand them, so that the KISS decoder, the AX.25 decoder and the APRS parser do the same work as for a radio. The frames the Tnc writes are decoded and shown to the scene, which answers a
message and plays a digipeater's repeat of a position of ours; they are never sent on. The traffic is made round the station's position when there is one, else round Helsinki.

The Dummy HF radio is the same line with the HF scene (dummyhfscene.py: distant fixed stations, no digipeater) and, when a speaker is given, the frames the Tnc writes are also handed to it as the KISS bytes they
came as (the Mercury modem started on the computer's own sound output, mercurymodem.py), so that the operator hears what the modem sounds like; a speaker that is not there changes nothing. Each frame is handed
over with the reading the scene makes up for it (`take_reading`, neoaprs/reading.py: the HF scene an SNR for each station, the Dummy radio's scene none), as a modem says the reading of the frame it hands over."""
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

DUMMY_PATH = "the dummy radio"          # what the Tnc calls the port of the Dummy radio
TICK_SEC = 0.5                          # how often the scene is asked what has come due


class SceneLike(Protocol):
    """What a made-up world does (dummyscene.py, dummyhfscene.py): says what has come due and the reading of each frame, takes what we sent, and describes itself for the log."""
    @property
    def description(self) -> str: ...
    def due(self, now: datetime) -> list[ax25.Frame]: ...
    def react(self, frame: ax25.Frame, now: datetime) -> None: ...
    def reading_of(self, frame: ax25.Frame) -> Reading: ...


SceneFactory = Callable[[tuple[float, float] | None, datetime, int], SceneLike]


class Speaker(Protocol):
    """What plays the frames of the Dummy HF radio aloud: the Mercury modem on the speakers (mercurymodem.py)."""
    def play(self, data: bytes) -> None: ...


class DummyPort(TncPort):
    def __init__(self, on_data: Callable[[TncPort, bytes], None], on_lost: Callable[[TncPort, str], None], where: Callable[[], tuple[float, float] | None], clock: Clock, tick_sec: float | None = None,
                 seed: int = 1, scene_of: SceneFactory = Scene, speaker: Speaker | None = None) -> None:
        super().__init__(DUMMY_PATH, 0, on_data, on_lost)
        self._where, self._clock, self._tick_sec, self._seed = where, clock, TICK_SEC if tick_sec is None else tick_sec, seed
        self._scene_of, self._speaker = scene_of, speaker
        self.scene: SceneLike | None = None
        self._task: asyncio.Task[None] | None = None
        self._reading = NO_READING                                       # the reading of the frame being handed over

    @property
    def is_open(self) -> bool:
        return self._task is not None

    async def open(self) -> None:
        self.scene = self._scene_of(self._where(), self._clock(), self._seed)
        self._task = asyncio.get_running_loop().create_task(self._play(self.scene), name="dummy-radio")
        self._task.add_done_callback(self._ended)
        log.info("tnc: the dummy radio makes %s", self.scene.description)

    def close(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()

    def write(self, data: bytes) -> int:
        """What the Tnc sends: shown to the scene, played by the speaker when there is one, and swallowed."""
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
        """The scene's task ended by itself (a fault in the scene): the line is lost, as a serial line that dies is, so that the Tnc does not stay CONNECTED on a line that plays nothing."""
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
        """The reading of the frame the line is handing over now (the Tnc reads the frame as it is handed over), once."""
        reading, self._reading = self._reading, NO_READING
        return reading
