"""The line of the Dummy radio: where a real radio's serial line would be, the Tnc (tnc.py) gets the made-up traffic of a `Scene` (dummyscene.py) as KISS bytes, and what it writes is read by the scene and goes nowhere.

It is a `TncPort` that opens nothing: no serial port, no socket, no file, no other program. A task plays the scene once every half second: the frames that have come due are encoded as AX.25 and KISS and handed to
the Tnc as a line would hand them, so that the KISS decoder, the AX.25 decoder and the APRS parser do the same work as for a radio. The frames the Tnc writes are decoded and shown to the scene, which answers a
message and plays a digipeater's repeat of a position of ours; they are never sent on. The traffic is made round the station's position when there is one, else round Helsinki."""
import asyncio
import logging
from collections.abc import Callable

from . import ax25, kiss
from .clock import Clock
from .dummyscene import Scene
from .serialport import SerialError
from .tncport import TncPort

log = logging.getLogger("neoaprs.tnc")

DUMMY_PATH = "the dummy radio"          # what the Tnc calls the port of the Dummy radio
TICK_SEC = 0.5                          # how often the scene is asked what has come due


class DummyPort(TncPort):
    def __init__(self, on_data: Callable[[TncPort, bytes], None], on_lost: Callable[[TncPort, str], None], where: Callable[[], tuple[float, float] | None], clock: Clock, tick_sec: float | None = None,
                 seed: int = 1) -> None:
        super().__init__(DUMMY_PATH, 0, on_data, on_lost)
        self._where, self._clock, self._tick_sec, self._seed = where, clock, TICK_SEC if tick_sec is None else tick_sec, seed
        self.scene: Scene | None = None
        self._task: asyncio.Task[None] | None = None

    @property
    def is_open(self) -> bool:
        return self._task is not None

    async def open(self) -> None:
        self.scene = Scene(self._where(), self._clock(), self._seed)
        self._task = asyncio.get_running_loop().create_task(self._play(self.scene), name="dummy-radio")
        log.info("tnc: the dummy radio makes traffic round %.4f, %.4f", *self.scene.centre)

    def close(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()

    def write(self, data: bytes) -> int:
        """What the Tnc sends: shown to the scene and swallowed."""
        if self._task is None or self.scene is None:
            raise SerialError(f"{DUMMY_PATH}: not open")
        for kiss_frame in kiss.KissDecoder().feed(data):
            try:
                self.scene.react(ax25.decode(kiss_frame.payload), self._clock())
            except ax25.Ax25Error:
                continue
        return len(data)

    async def _play(self, scene: Scene) -> None:
        while True:
            await asyncio.sleep(self._tick_sec)
            for frame in scene.due(self._clock()):
                self._deliver(kiss.encode(ax25.encode(frame)))
