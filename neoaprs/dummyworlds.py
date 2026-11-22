"""The line of each Dummy type by its profile (`dummy_line`) and the world it plays.

The Dummy and Dummy HF radios use the KISS lines of dummyline.py; the Dummy LoRa radio uses
`DummyLoraPort`, a board of made-up stations that speaks TNC2 text.
"""

import asyncio
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from . import ax25, kiss
from .clock import Clock
from .dummyhfscene import STATIONS as CITIES, HfScene
from .dummyline import DummyPort, SceneLike, Speaker
from .dummylorascene import LoraScene, board_air, board_line, calls as lora_calls
from .dummyscene import Scene
from .reading import NO_READING
from .serialport import SerialError
from .tnc2line import LineReader, Tnc2Error, from_air
from .tncport import TncPort
from .tncprofile import DUMMY, DUMMY_HF, DUMMY_LORA, Profile

KEPT_SENT = 50  # sent packets kept for inspection


class DummyLoraPort(DummyPort):
    def __init__(
        self,
        on_data: Callable[[TncPort, bytes], None],
        on_lost: Callable[[TncPort, str], None],
        where: Callable[[], tuple[float, float] | None],
        clock: Clock,
        tick_sec: float | None = None,
        seed: int = 1,
    ) -> None:
        super().__init__(on_data, on_lost, where, clock, tick_sec, seed, LoraScene)
        self._lines = LineReader()  # reads the board's text lines into frames
        # packets of ours on the made-up air, the latest last
        self.transmitted: deque[bytes] = deque(maxlen=KEPT_SENT)

    async def _play(self, scene: SceneLike) -> None:
        while True:
            await asyncio.sleep(self._tick_sec)
            for frame in scene.due(self._clock()):
                reading = scene.reading_of(frame)
                for line in self._lines.feed(board_line(board_air(frame) or b"")):
                    if line.frame is not None:
                        self._reading = reading
                        self._deliver(kiss.encode(ax25.encode(line.frame)))
                        self._reading = NO_READING

    def write(self, data: bytes) -> int:
        """Put each KISS data frame on the made-up air as text, for the scene to hear."""
        if self._task is None or self.scene is None:
            raise SerialError("the dummy LoRa radio: not open")
        for kiss_frame in kiss.KissDecoder().feed(data):
            try:
                packet = board_air(ax25.decode(kiss_frame.payload)) if kiss_frame.command == 0 else None
                if packet is not None:
                    self.transmitted.append(packet)
                    self.scene.react(from_air(packet), self._clock())
            except (ax25.Ax25Error, Tnc2Error):
                continue
        return len(data)


class LineOwner(Protocol):
    """What a Dummy line needs of the Tnc it is the line of (tnc.py)."""

    profile: Profile
    radio_id: int
    clock: Clock
    where: Callable[[], tuple[float, float] | None]

    def _on_data(self, port: TncPort, chunk: bytes) -> None: ...
    def _on_lost(self, port: TncPort, reason: str) -> None: ...
    @property
    def modem(self) -> Speaker | None: ...


@dataclass(frozen=True)
class World:
    """A Dummy type's world: its line, its status-line name and the calls it makes up by seed."""

    line: Callable[[LineOwner], DummyPort]
    words: str
    calls: Callable[[int], frozenset[str]]


# the Dummy HF radio's stations are the same in every world
_CITY_CALLS = frozenset(station.call for station in CITIES)
# the world of each Dummy type, by the key of its profile
WORLDS: dict[str, World] = {
    DUMMY.key: World(
        lambda tnc: DummyPort(tnc._on_data, tnc._on_lost, tnc.where, tnc.clock, seed=tnc.radio_id, scene_of=Scene),
        "dummy radio",
        lambda _seed: frozenset(),
    ),
    DUMMY_HF.key: World(
        lambda tnc: DummyPort(
            tnc._on_data, tnc._on_lost, tnc.where, tnc.clock, seed=tnc.radio_id, scene_of=HfScene, speaker=tnc.modem
        ),
        "dummy Mercury radio",
        lambda _seed: _CITY_CALLS,
    ),
    DUMMY_LORA.key: World(
        lambda tnc: DummyLoraPort(tnc._on_data, tnc._on_lost, tnc.where, tnc.clock, seed=tnc.radio_id),
        "dummy LoRa radio",
        lora_calls,
    ),
}


def dummy_line(tnc: LineOwner) -> DummyPort:
    """Return the Tnc's Dummy line, not yet open."""
    return WORLDS[tnc.profile.key].line(tnc)


def dummy_words(profile: str) -> str:
    """Return what the status line calls a radio of this profile: "dummy LoRa radio"."""
    return WORLDS[profile].words


def made_up_calls(profile: str, seed: int) -> frozenset[str]:
    """Return the calls the world makes up for radio `seed`; none if not a Dummy."""
    world = WORLDS.get(profile)
    return frozenset() if world is None else world.calls(seed)
